<template>
  <div class="hqkline-wrap">
    <div class="hqkline-toolbar">
      <el-checkbox-group v-model="indicators" size="small" @change="render">
        <el-checkbox-button label="ma">MA</el-checkbox-button>
        <el-checkbox-button label="boll">BOLL</el-checkbox-button>
      </el-checkbox-group>
      <el-checkbox-group v-model="overlays" size="small" class="ml8" @change="render">
        <el-checkbox-button label="czsc">缠论</el-checkbox-button>
        <el-checkbox-button label="signals">买卖点</el-checkbox-button>
      </el-checkbox-group>
    </div>
    <div ref="el" class="hqkline-chart" :style="{ height }"></div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
  height: { type: String, default: '460px' },
  title: { type: String, default: '' },
  fx: { type: Array, default: () => [] },
  bi: { type: Array, default: () => [] },
  zs: { type: Array, default: () => [] },
  signals: { type: Array, default: () => [] },
  stagePoints: { type: Array, default: () => [] },
})

const STAGE_COLORS = {
  '吸筹': '#409eff', '洗盘': '#e6a23c', '拉升': '#ef232a', '出货': '#8b5cf6'
}

const el = ref(null)
let chart = null
const indicators = ref(['ma'])
const overlays = ref(['czsc', 'signals'])

function calcMa(d, n) {
  return d.map((_, i) => {
    if (i < n - 1) return '-'
    let s = 0
    for (let j = i - n + 1; j <= i; j++) s += d[j].close
    return +(s / n).toFixed(2)
  })
}

function calcBoll(d, n = 20) {
  const mid = calcMa(d, n)
  const upper = [], lower = []
  for (let i = 0; i < d.length; i++) {
    if (i < n - 1) { upper.push('-'); lower.push('-'); continue }
    let sum = 0
    for (let j = i - n + 1; j <= i; j++) sum += Math.pow(d[j].close - mid[i], 2)
    const std = Math.sqrt(sum / n)
    upper.push(+(mid[i] + 2 * std).toFixed(2))
    lower.push(+(mid[i] - 2 * std).toFixed(2))
  }
  return { mid, upper, lower }
}

function calcMacd(d, short = 12, long = 26, mid = 9) {
  const closes = d.map(x => x.close)
  function ema(arr, n) {
    const r = [arr[0]]
    const k = 2 / (n + 1)
    for (let i = 1; i < arr.length; i++) r.push(arr[i] * k + r[i - 1] * (1 - k))
    return r
  }
  const emaS = ema(closes, short)
  const emaL = ema(closes, long)
  const dif = emaS.map((v, i) => +(v - emaL[i]).toFixed(3))
  const dea = ema(dif, mid).map(v => +v.toFixed(3))
  const macd = dif.map((v, i) => +((v - dea[i]) * 2).toFixed(3))
  return { dif, dea, macd }
}

function render() {
  if (!chart || !Array.isArray(props.data) || !props.data.length) return
  const d = props.data
  const dates = d.map(x => x.dt || x.date || x.time)
  const idxByDt = {}
  dates.forEach((dt, i) => { idxByDt[dt] = i })

  const kdata = d.map(x => [x.open, x.close, x.low, x.high])
  const vols = d.map(x => x.volume || 0)

  const series = [
    {
      name: 'K线', type: 'candlestick', data: kdata, xAxisIndex: 0, yAxisIndex: 0,
      itemStyle: { color: '#ef232a', color0: '#14b143', borderColor: '#ef232a', borderColor0: '#14b143' }
    },
    {
      name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: vols,
      itemStyle: { color: p => d[p.dataIndex]?.close >= d[p.dataIndex]?.open ? '#ef232a' : '#14b143' }
    }
  ]

  const legendData = ['K线', '成交量']

  if (indicators.value.includes('ma')) {
    const ma5 = calcMa(d, 5), ma10 = calcMa(d, 10), ma20 = calcMa(d, 20), ma60 = calcMa(d, 60), ma250 = calcMa(d, 250)
    series.push(
      { name: 'MA5', type: 'line', data: ma5, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#f7b32b' } },
      { name: 'MA10', type: 'line', data: ma10, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#2f7ef9' } },
      { name: 'MA20', type: 'line', data: ma20, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#8b5cf6' } },
      { name: 'MA60', type: 'line', data: ma60, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#ec4899' } },
    )
    legendData.push('MA5', 'MA10', 'MA20', 'MA60')
    if (d.length >= 250) {
      series.push({ name: 'MA250', type: 'line', data: ma250, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#909399' } })
      legendData.push('MA250')
    }
  }

  if (indicators.value.includes('boll')) {
    const { mid, upper, lower } = calcBoll(d)
    series.push(
      { name: 'BOLL-MID', type: 'line', data: mid, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#f59e0b', type: 'dashed' } },
      { name: 'BOLL-UP', type: 'line', data: upper, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#ef4444', type: 'dotted' } },
      { name: 'BOLL-DN', type: 'line', data: lower, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#22c55e', type: 'dotted' } },
    )
    legendData.push('BOLL-MID', 'BOLL-UP', 'BOLL-DN')
  }

  if (overlays.value.includes('czsc') && Array.isArray(props.bi) && props.bi.length) {
    const biLine = new Array(dates.length).fill(null)
    for (const b of props.bi) {
      const s = idxByDt[b.start], e = idxByDt[b.end]
      if (s == null || e == null) continue
      const up = b.direction === 'up'
      biLine[s] = up ? b.low : b.high
      biLine[e] = up ? b.high : b.low
    }
    series.push({ name: '笔', type: 'line', data: biLine, smooth: false, symbol: 'none', connectNulls: false, lineStyle: { width: 1.5, color: '#00b8d4' }, z: 3 })
    legendData.push('笔')
  }

  if (overlays.value.includes('czsc') && Array.isArray(props.zs) && props.zs.length) {
    const areas = []
    for (const z of props.zs) {
      const s = idxByDt[z.start], e = idxByDt[z.end]
      if (s == null || e == null) continue
      areas.push([
        { xAxis: s, yAxis: z.low, itemStyle: { color: 'rgba(64,158,255,0.1)' } },
        { xAxis: e, yAxis: z.high }
      ])
    }
    if (areas.length) {
      series.push({ name: '中枢', type: 'scatter', data: [], silent: true, markArea: { data: areas, z: 1, label: { show: true, formatter: '中枢', position: 'insideTop', fontSize: 9, color: '#409eff' } } })
    }
  }

  if (overlays.value.includes('czsc') && Array.isArray(props.fx) && props.fx.length) {
    const pts = []
    for (const f of props.fx) {
      const i = idxByDt[f.dt]
      if (i == null) continue
      const top = f.mark === 'g'
      pts.push({
        value: [i, f.price],
        symbol: 'triangle', symbolRotate: top ? 180 : 0, symbolSize: 10,
        itemStyle: { color: top ? '#ef232a' : '#14b143' },
        label: { show: true, formatter: f.type || (top ? '顶' : '底'), position: top ? 'top' : 'bottom', fontSize: 9, color: top ? '#ef232a' : '#14b143' }
      })
    }
    if (pts.length) series.push({ name: '分型', type: 'scatter', data: pts, z: 4, xAxisIndex: 0, yAxisIndex: 0 })
  }

  if (overlays.value.includes('signals') && Array.isArray(props.signals) && props.signals.length) {
    const pts = []
    for (const sg of props.signals) {
      const i = idxByDt[sg.time]
      if (i == null) continue
      const buy = sg.type === 'buy'
      const price = buy ? d[i].low : d[i].high
      const label = sg.signal_type || (buy ? 'B' : 'S')
      pts.push({
        value: [i, price * (buy ? 0.98 : 1.02)],
        symbol: 'pin', symbolSize: buy ? 36 : 36,
        itemStyle: { color: buy ? '#14b143' : '#ef232a' },
        label: { show: true, formatter: label, position: buy ? 'bottom' : 'top', fontSize: 10, fontWeight: 'bold', color: '#fff', offset: [0, buy ? 4 : -4] }
      })
    }
    if (pts.length) series.push({ name: '信号', type: 'scatter', data: pts, z: 5, xAxisIndex: 0, yAxisIndex: 0 })
  }

  const hasMacd = indicators.value.includes('macd')

  // 情绪阶段色带（吸筹/洗盘/拉升/出货）
  const stageSeries = []
  if (Array.isArray(props.stagePoints) && props.stagePoints.length) {
    const strip = []
    let cur = null, curStart = null
    const push = (st, s, e) => {
      const c = STAGE_COLORS[st]
      if (!c || s == null || e == null) return
      strip.push([
        { xAxis: s, itemStyle: { color: c }, label: { show: (e - s) > 4, formatter: st.replace('阶段', ''), position: 'insideBottom', fontSize: 9, color: '#333' }, tooltip: { formatter: () => st } },
        { xAxis: e }
      ])
    }
    for (const sp of props.stagePoints) {
      const i = idxByDt[sp.dt]
      if (i == null) continue
      if (sp.stage !== cur) { if (cur) push(cur, curStart, i); cur = sp.stage; curStart = i }
    }
    if (cur) push(cur, curStart, dates.length - 1)
    if (strip.length) {
      stageSeries.push({ name: '情绪', type: 'scatter', data: [], xAxisIndex: 2, yAxisIndex: 2, silent: true, markArea: { data: strip } })
      legendData.push('情绪')
    }
  }

  const grids = [
    { left: 55, right: 16, top: 30, height: hasMacd ? '46%' : '58%' },
    { left: 55, right: 16, top: hasMacd ? '80%' : '74%', height: '8%' },
    { left: 55, right: 16, top: '90%', height: '5%' },
  ]
  const xAxes = [
    { type: 'category', data: dates, boundaryGap: true, axisLine: { lineStyle: { color: '#ddd' } }, axisLabel: { fontSize: 10 } },
    { type: 'category', gridIndex: 1, data: dates, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#ddd' } } },
    { type: 'category', gridIndex: 2, data: dates, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false } },
  ]
  const yAxes = [
    { scale: true, splitLine: { lineStyle: { color: '#f0f0f0' } }, axisLabel: { fontSize: 10 } },
    { gridIndex: 1, splitNumber: 2, splitLine: { show: false }, axisLabel: { fontSize: 9, formatter: v => v >= 1e8 ? (v / 1e8).toFixed(0) + '亿' : v >= 1e4 ? (v / 1e4).toFixed(0) + '万' : v } },
    { gridIndex: 2, show: false, min: 0, max: 1, splitLine: { show: false } },
  ]
  const dataZoom = [
    { type: 'inside', xAxisIndex: [0, 1, 2], start: Math.max(0, 100 - Math.min(100, 20000 / d.length * 100)), end: 100 },
    { type: 'slider', xAxisIndex: [0, 1, 2], top: '96%', height: 12 },
  ]

  if (hasMacd) {
    const { dif, dea, macd } = calcMacd(d)
    grids.push({ left: 55, right: 16, top: '66%', height: '12%' })
    xAxes.push({ type: 'category', gridIndex: 3, data: dates, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#ddd' } } })
    yAxes.push({ gridIndex: 3, splitNumber: 2, splitLine: { show: false }, axisLabel: { fontSize: 9 } })
    dataZoom[0].xAxisIndex.push(3)
    dataZoom[1].xAxisIndex.push(3)
    series.push(
      { name: 'DIF', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: dif, symbol: 'none', lineStyle: { width: 1, color: '#2f7ef9' } },
      { name: 'DEA', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: dea, symbol: 'none', lineStyle: { width: 1, color: '#f7b32b' } },
      {
        name: 'MACD', type: 'bar', xAxisIndex: 3, yAxisIndex: 3, data: macd,
        itemStyle: { color: p => macd[p.dataIndex] >= 0 ? '#ef232a' : '#14b143' }
      },
    )
    legendData.push('DIF', 'DEA', 'MACD')
  }

  if (stageSeries.length) series.push(...stageSeries)

  const option = {
    backgroundColor: '#fff', animation: false,
    title: props.title ? { text: props.title, left: 8, top: 4, textStyle: { fontSize: 14 } } : undefined,
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross' },
      formatter(params) {
        const i = params[0]?.dataIndex ?? 0
        const it = d[i]; if (!it) return ''
        const pct = it.open ? (((it.close - it.open) / it.open) * 100).toFixed(2) : '0'
        return `<b style="color:${Number(pct) >= 0 ? '#ef232a' : '#14b143'}">${dates[i]}</b><br/>开 ${it.open} 收 ${it.close}（${Number(pct) >= 0 ? '+' : ''}${pct}%）<br/>高 ${it.high} 低 ${it.low}<br/>量 ${vols[i]?.toLocaleString()}`
      }
    },
    legend: { top: 4, right: 12, data: legendData, textStyle: { fontSize: 10 } },
    grid: grids, xAxis: xAxes, yAxis: yAxes, dataZoom, series,
  }
  chart.setOption(option, true)
}

function resize() { chart && chart.resize() }

onMounted(() => {
  chart = echarts.init(el.value)
  render()
  window.addEventListener('resize', resize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart && chart.dispose()
})

watch(() => [props.data, props.fx, props.bi, props.zs, props.signals], render, { deep: true })
</script>

<style scoped>
.hqkline-wrap { display: flex; flex-direction: column; }
.hqkline-toolbar { padding: 4px 8px; display: flex; align-items: center; gap: 4px; }
.hqkline-chart { flex: 1; }
</style>
