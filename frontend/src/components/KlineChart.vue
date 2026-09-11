<template>
  <div ref="el" class="chart" :style="{ height }"></div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
  height: { type: String, default: '320px' },
  title: { type: String, default: '' },
  fx: { type: Array, default: () => [] },
  bi: { type: Array, default: () => [] },
  zs: { type: Array, default: () => [] },
  signals: { type: Array, default: () => [] },
  stagePoints: { type: Array, default: () => [] }
})

const STAGE_COLORS = {
  '吸筹': '#409eff', '洗盘': '#e6a23c', '拉升': '#ef232a', '出货': '#8b5cf6'
}

const el = ref(null)
let chart = null

function render() {
  if (!chart || !Array.isArray(props.data) || !props.data.length) return
  const d = props.data
  const dates = d.map((x) => x.dt || x.date || x.time)
  const idxByDt = {}
  dates.forEach((dt, i) => { idxByDt[dt] = i })
  const kdata = d.map((x) => [x.open, x.close, x.low, x.high])
  const vols = d.map((x) => x.volume || 0)
  const ma5 = calcMa(d, 5)
  const ma10 = calcMa(d, 10)
  const ma20 = calcMa(d, 20)

  const series = [
    {
      name: 'K线',
      type: 'candlestick',
      data: kdata,
      itemStyle: { color: '#ef232a', color0: '#14b143', borderColor: '#ef232a', borderColor0: '#14b143' }
    },
    { name: 'MA5', type: 'line', data: ma5, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#f7b32b' } },
    { name: 'MA10', type: 'line', data: ma10, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#2f7ef9' } },
    { name: 'MA20', type: 'line', data: ma20, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#8b5cf6' } },
    {
      name: '成交量',
      type: 'bar',
      xAxisIndex: 1,
      yAxisIndex: 1,
      data: vols,
      itemStyle: { color: (p) => (d[p.dataIndex].close >= d[p.dataIndex].open ? '#ef232a' : '#14b143') }
    }
  ]

  // 缠论：笔（连续折线）
  if (Array.isArray(props.bi) && props.bi.length) {
    const line = new Array(dates.length).fill(null)
    for (const b of props.bi) {
      const s = idxByDt[b.start]
      const e = idxByDt[b.end]
      if (s == null || e == null) continue
      const up = b.direction === 'up'
      line[s] = up ? b.low : b.high
      line[e] = up ? b.high : b.low
    }
    series.push({
      name: '笔',
      type: 'line',
      data: line,
      smooth: true,
      symbol: 'none',
      connectNulls: false,
      lineStyle: { width: 1.2, color: '#00b8d4' },
      z: 3
    })
  }

  // 缠论：分型（顶/底）
  if (Array.isArray(props.fx) && props.fx.length) {
    const pts = []
    for (const f of props.fx) {
      const i = idxByDt[f.dt]
      if (i == null) continue
      const top = f.mark === 'g'
      pts.push({
        value: [i, f.price],
        symbol: 'triangle',
        symbolRotate: top ? 180 : 0,
        symbolSize: 11,
        itemStyle: { color: top ? '#ef232a' : '#14b143' },
        label: { show: true, formatter: f.type || '', position: top ? 'top' : 'bottom', fontSize: 9, color: top ? '#ef232a' : '#14b143' }
      })
    }
    if (pts.length) {
      series.push({ name: '分型', type: 'scatter', data: pts, z: 4, tooltip: { formatter: (p) => `${dates[p.data[0]]} ${p.data[1]}` } })
    }
  }

  // 缠论：中枢（矩形区域）
  if (Array.isArray(props.zs) && props.zs.length) {
    const areas = []
    for (const z of props.zs) {
      const s = idxByDt[z.start]
      const e = idxByDt[z.end]
      if (s == null || e == null) continue
      areas.push({
        name: '中枢',
        xAxis: s,
        yAxis: z.low,
        itemStyle: { color: 'rgba(64,158,255,0.12)', borderColor: '#409eff', borderWidth: 1, borderType: 'dashed' },
        label: { show: true, formatter: '中枢', position: 'insideTop', fontSize: 9, color: '#409eff' }
      })
      areas.push({ xAxis: e, yAxis: z.high })
    }
    series.push({ name: '中枢', type: 'scatter', data: [], silent: true, markArea: { data: areas, z: 1 } })
  }

  // 缠论信号（买卖点）
  if (Array.isArray(props.signals) && props.signals.length) {
    const pts = []
    for (const sg of props.signals) {
      const i = idxByDt[sg.time]
      if (i == null) continue
      const buy = sg.type === 'buy'
      const base = buy ? d[i].low : d[i].high
      pts.push({
        value: [i, base],
        symbol: buy ? 'arrow' : 'arrow',
        symbolRotate: buy ? 0 : 180,
        symbolSize: 11,
        itemStyle: { color: buy ? '#14b143' : '#ef232a' },
        label: { show: true, formatter: buy ? 'B' : 'S', position: buy ? 'bottom' : 'top', fontSize: 10, color: buy ? '#14b143' : '#ef232a' }
      })
    }
    if (pts.length) {
      series.push({ name: '信号', type: 'scatter', data: pts, z: 5, tooltip: { formatter: (p) => { const it = d[p.data[0]]; return `${dates[p.data[0]]}<br/>${p.data[1]}<br/>${p.data[2] || ''}` } } })
    }
  }

  // 情绪阶段色带（吸筹/洗盘/拉升/出货）
  if (Array.isArray(props.stagePoints) && props.stagePoints.length) {
    const strip = []
    let curStage = null, curStart = null
    const run = (stage, s, e) => {
      const color = STAGE_COLORS[stage]
      if (!color || s == null || e == null) return
      strip.push({
        xAxis: s,
        itemStyle: { color },
        label: { show: (e - s) > 3, formatter: stage.replace('阶段', ''), position: 'insideBottom', fontSize: 9, color: '#333' },
        tooltip: { formatter: () => `${stage}` }
      })
      strip.push({ xAxis: e })
    }
    for (let i = 0; i < props.stagePoints.length; i++) {
      const sp = props.stagePoints[i]
      const di = idxByDt[sp.dt]
      if (di == null) continue
      if (sp.stage !== curStage) {
        if (curStage) run(curStage, curStart, di)
        curStage = sp.stage
        curStart = di
      }
    }
    if (curStage) run(curStage, curStart, dates.length - 1)
    if (strip.length) {
      series.push({ name: '情绪', type: 'scatter', data: [], xAxisIndex: 2, yAxisIndex: 2, silent: true, markArea: { data: strip } })
    }
  }

  const option = {
    backgroundColor: '#fff',
    animation: false,
    title: props.title ? { text: props.title, left: 8, top: 6, textStyle: { fontSize: 14 } } : undefined,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        const i = params[0] && params[0].dataIndex != null ? params[0].dataIndex : (params[0] && params[0].data && params[0].data[0]) || 0
        const it = d[i]
        if (!it) return ''
        const pct = it.open ? (((it.close - it.open) / it.open) * 100).toFixed(2) : '0'
        return `<b>${dates[i]}</b><br/>开 ${it.open}　收 ${it.close}（${pct}%）<br/>高 ${it.high}　低 ${it.low}<br/>量 ${vols[i]}`
      }
    },
    legend: {
      top: 4,
      right: 12,
      data: ['K线', 'MA5', 'MA10', 'MA20', '笔', '分型', '信号', '情绪']
    },
    grid: [
      { left: 60, right: 20, top: 30, height: '54%' },
      { left: 60, right: 20, top: '67%', height: '14%' },
      { left: 60, right: 20, top: '83%', height: '8%' }
    ],
    xAxis: [
      { type: 'category', data: dates, boundaryGap: true, axisLine: { lineStyle: { color: '#ccc' } } },
      { type: 'category', gridIndex: 1, data: dates, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#ccc' } } },
      { type: 'category', gridIndex: 2, data: dates, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false } }
    ],
    yAxis: [
      { scale: true, splitLine: { lineStyle: { color: '#f0f0f0' } } },
      { gridIndex: 1, splitNumber: 2, axisLabel: { formatter: (v) => (v >= 1e8 ? (v / 1e8).toFixed(0) + '亿' : v >= 1e4 ? (v / 1e4).toFixed(0) + '万' : v) }, splitLine: { show: false } },
      { gridIndex: 2, show: false, min: 0, max: 1, splitLine: { show: false } }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2], start: 40, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1, 2], top: '93%', height: 14 }
    ],
    series
  }
  chart.setOption(option)
}

function calcMa(d, n) {
  return d.map((_, i) => {
    if (i < n - 1) return '-'
    let s = 0
    for (let j = i - n + 1; j <= i; j++) s += d[j].close
    return +(s / n).toFixed(2)
  })
}

function resize() {
  chart && chart.resize()
}

onMounted(() => {
  chart = echarts.init(el.value)
  render()
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart && chart.dispose()
})

watch(() => props.data, render, { deep: true })
watch(() => props.title, render)
watch(() => [props.fx, props.bi, props.zs, props.signals, props.stagePoints], render, { deep: true })
</script>