<template>
  <div ref="el" class="chart" :style="{ height }"></div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const SIGNAL_COLORS = {
  '吸筹': '#e6a23c',
  '洗盘': '#909399',
  '诱多': '#f56c6c',
  '诱空': '#67c23a',
  '出货': '#e74c3c',
  '真拉升': '#409eff',
  'T买': '#14b143',
  'T卖': '#ef232a',
}

const props = defineProps({
  data: { type: Array, default: () => [] },
  height: { type: String, default: '260px' },
  area: { type: Boolean, default: true },
  colors: { type: Array, default: () => ['#409eff'] },
  showAvg: { type: Boolean, default: true },
  volume: { type: Boolean, default: false },
  multi: { type: Array, default: () => [] },
  signals: { type: Array, default: () => [] },
  showVwap: { type: Boolean, default: false },
  preClose: { type: Number, default: 0 },
  showT: { type: Boolean, default: false },
})

const el = ref(null)
let chart = null
let rendering = false

function minuteAxis() {
  const labels = []
  for (let mt = 9 * 60 + 15; mt <= 15 * 60; mt++) {
    if (mt >= 11 * 60 + 31 && mt <= 12 * 60 + 59) continue
    const hh = String(Math.floor(mt / 60)).padStart(2, '0')
    const mm = String(mt % 60).padStart(2, '0')
    labels.push(`${hh}:${mm}`)
  }
  return labels
}

function render() {
  if (rendering) return
  rendering = true
  try {
    _doRender()
  } finally {
    rendering = false
  }
}

function _doRender() {
  if (!chart || !Array.isArray(props.data) || !props.data.length) return
  const labels = []
  let series = []

  const first = props.data[0]
  const isMinute = first && typeof first === 'object' &&
    typeof first.time === 'string' && /^\d{1,2}:\d{2}$/.test(first.time) &&
    first.avg !== undefined

  if (isMinute) {
    const minutes = minuteAxis()
    const timeIdx = {}
    minutes.forEach((t, i) => { timeIdx[t] = i })
    labels.push(...minutes)
    const price = new Array(minutes.length).fill(null)
    const avg = new Array(minutes.length).fill(null)
    const vwapArr = new Array(minutes.length).fill(null)
    const volDelta = new Array(minutes.length).fill(null)
    let prevPrice = null
    let found = 0
    for (const row of props.data) {
      const idx = timeIdx[row.time]
      if (idx === undefined) continue
      const p = row.price ?? null
      price[idx] = p
      if (props.showAvg && row.avg !== undefined && row.avg !== null && p &&
        Math.abs(row.avg - p) / p <= 0.3) avg[idx] = row.avg
      if (props.showVwap && row.vwap) vwapArr[idx] = row.vwap
      if (props.volume && typeof row.volume === 'number' && row.volume > 0) {
        const prevCum = found === 0 ? 0 : (props.data[found - 1]?.volume ?? 0)
        const d = Math.max(row.volume - prevCum, 0)
        const up = (p ?? 0) >= (prevPrice ?? p ?? 0)
        volDelta[idx] = {
          value: d,
          itemStyle: { color: up ? 'rgba(230,80,80,0.65)' : 'rgba(55,170,90,0.65)' }
        }
        prevPrice = p
      }
      found++
    }

    // --- sigIdx 必须在最外层定义，tooltip formatter 闭包需要引用 ---
    const sigIdx = {}
    if (props.signals && props.signals.length) {
      props.signals.forEach(s => {
        // 做T信号需要 showT 开启才显示
        const isT = s.type === 't_buy' || s.type === 't_sell'
        if (isT && !props.showT) return
        sigIdx[s.time] = s
      })
    }

    // --- 信号标记点 ---
    const markPoints = []
    for (let i = 0; i < minutes.length; i++) {
      const sig = sigIdx[minutes[i]]
      if (sig && price[i] != null) {
        markPoints.push({
          coord: [i, price[i]],
          value: sig.signal,
          symbol: sig.signal === '真拉升' ? 'triangle' : sig.signal === '诱多' ? 'diamond' :
            sig.signal === '诱空' ? 'triangle' : sig.signal === '洗盘' ? 'circle' :
            sig.signal === '出货' ? 'rect' : 'pin',
          symbolSize: sig.confidence > 70 ? 10 : sig.confidence > 50 ? 8 : 6,
          itemStyle: { color: SIGNAL_COLORS[sig.signal] || '#409eff' },
          label: {
            show: true,
            formatter: sig.signal,
            fontSize: 8,
            color: '#fff',
            backgroundColor: SIGNAL_COLORS[sig.signal] || '#409eff',
            borderRadius: 3,
            padding: [1, 3],
            position: 'top',
          }
        })
      }
    }

    // --- 昨收参考线 ---
    const markLines = []
    if (props.preClose > 0) {
      markLines.push({
        yAxis: props.preClose,
        lineStyle: { color: '#aaa', type: 'dashed', width: 1 },
        label: { show: true, formatter: '昨收 ' + props.preClose.toFixed(2), fontSize: 9, color: '#999' }
      })
    }

    const useDualAxis = props.preClose > 0
    series = [
      {
        name: '价格',
        type: 'line',
        data: price,
        yAxisIndex: useDualAxis ? 1 : 0,
        smooth: true,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { width: 1.5, color: props.colors[0] || '#409eff' },
        areaStyle: props.area ? { opacity: 0.15, color: props.colors[0] || '#409eff' } : undefined,
        markPoint: markPoints.length ? { data: markPoints, animation: false } : undefined,
        markLine: markLines.length ? { data: markLines, animation: false, silent: true } : undefined,
      }
    ]
    if (props.showAvg) {
      series.push({
        name: '均价',
        type: 'line',
        data: avg,
        yAxisIndex: useDualAxis ? 1 : 0,
        smooth: true,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { width: 1.2, color: props.colors[1] || '#e6a23c', type: 'dashed' }
      })
    }
    if (props.showVwap) {
      series.push({
        name: 'VWAP',
        type: 'line',
        data: vwapArr,
        yAxisIndex: useDualAxis ? 1 : 0,
        smooth: true,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { width: 1.2, color: '#9b59b6', type: 'dotted' }
      })
    }
    if (props.volume) {
      series.push({
        name: '成交量',
        type: 'bar',
        data: volDelta,
        xAxisIndex: 1,
        yAxisIndex: 2,
        barWidth: '70%'
      })
    }
    const valid = price.filter((x) => x != null)
    let minV = Math.min(...valid); let maxV = Math.max(...valid)
    const pad = Math.max((maxV - minV) * 0.08, maxV * 0.0005)
    if (maxV - minV < pad) { minV -= pad; maxV += pad }

    // 信号区域着色（markArea）
    const markAreas = []
    if (Object.keys(sigIdx).length) {
      let zone = null
      for (let i = 0; i < minutes.length; i++) {
        const sig = sigIdx[minutes[i]]
        if (sig && price[i] != null) {
          if (!zone || zone.signal !== sig.signal) {
            if (zone && zone.end - zone.start >= 1) {
              markAreas.push([
                { xAxis: zone.start, itemStyle: { color: (SIGNAL_COLORS[zone.signal] || '#409eff') + '12' } },
                { xAxis: zone.end }
              ])
            }
            zone = { signal: sig.signal, start: i, end: i }
          } else {
            zone.end = i
          }
        }
      }
      if (zone && zone.end - zone.start >= 1) {
        markAreas.push([
          { xAxis: zone.start, itemStyle: { color: (SIGNAL_COLORS[zone.signal] || '#409eff') + '12' } },
          { xAxis: zone.end }
        ])
      }
    }
    if (markAreas.length) {
      series[0].markArea = { data: markAreas, silent: true, animation: false }
    }

    chart.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          if (!params || !params.length) return ''
          const idx = params[0].dataIndex
          const t = minutes[idx]
          const p = price[idx]
          const v = vwapArr[idx]
          let tip = `<b>${t}</b><br/>`
          if (p != null) {
            tip += `价格: ${p.toFixed(2)}`
            if (props.preClose > 0) {
              const chg = ((p - props.preClose) / props.preClose * 100).toFixed(2)
              tip += ` <span style="color:${Number(chg) >= 0 ? '#ef232a' : '#14b143'}">(${chg >= 0 ? '+' : ''}${chg}%)</span>`
            }
          }
          if (v) tip += `<br/>VWAP: ${v.toFixed(2)}`
          const sig = sigIdx[t]
          if (sig) tip += `<br/><span style="color:${SIGNAL_COLORS[sig.signal]}">● ${sig.signal} (${sig.confidence}%)</span><br/>${sig.desc}`
          return tip
        }
      },
      legend: series.length > 1 ? { top: 0, right: 10, textStyle: { fontSize: 12 } } : undefined,
      grid: (() => {
        const rPad = useDualAxis ? 55 : 20
        if (props.volume) {
          return [
            { left: 50, right: rPad, top: series.length > 1 ? 30 : 16, height: '64%' },
            { left: 50, right: rPad, top: '82%', height: '10%' }
          ]
        }
        return { left: 50, right: rPad, top: series.length > 1 ? 30 : 16, bottom: 24 }
      })(),
      xAxis: props.volume
        ? [
            { type: 'category', data: labels, boundaryGap: false, axisLabel: { fontSize: 10 } },
            { type: 'category', gridIndex: 1, data: labels, show: false }
          ]
        : { type: 'category', data: labels, boundaryGap: false, axisLabel: { fontSize: 10 } },
      yAxis: (() => {
        const hasPreClose = props.preClose > 0
        const priceAxis = {
          scale: true, min: minV, max: maxV, position: 'left',
          splitLine: { lineStyle: { color: '#f0f0f0' } },
          axisLabel: { fontSize: 10 }
        }
        if (props.volume) {
          return [
            hasPreClose ? {
              scale: true, min: minV, max: maxV, position: 'right',
              splitLine: { show: false },
              axisLabel: { fontSize: 10, formatter: (v) => ((v - props.preClose) / props.preClose * 100).toFixed(2) + '%' }
            } : { scale: true, min: minV, max: maxV, position: 'left', splitLine: { lineStyle: { color: '#f0f0f0' } }, axisLabel: { fontSize: 10 } },
            priceAxis,
            { gridIndex: 1, scale: true, splitLine: { show: false }, axisLabel: { show: false } }
          ]
        }
        return [
          hasPreClose ? {
            scale: true, min: minV, max: maxV, position: 'right',
            splitLine: { show: false },
            axisLabel: { fontSize: 10, formatter: (v) => ((v - props.preClose) / props.preClose * 100).toFixed(2) + '%' }
          } : { scale: true, min: minV, max: maxV, position: 'left', splitLine: { lineStyle: { color: '#f0f0f0' } }, axisLabel: { fontSize: 10 } },
          priceAxis
        ]
      })(),
      series
    })
    return
  }

  const sets = typeof first === 'object'
    ? [{ name: '', values: props.data }]
    : [{ name: '', values: props.data.map((v, i) => ({ name: i, value: v })) }]
  labels.push(...(sets[0].values.map((x) => x.name ?? x.label ?? x.time ?? x.date ?? x.dt) || []))
  sets.forEach((set, si) => {
    series.push({
      name: set.name,
      type: 'line',
      data: set.values.map((x) => x.value ?? x.close ?? x.price ?? x.equity ?? x),
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 1.5, color: props.colors[si % props.colors.length] },
      areaStyle: props.area ? { opacity: 0.15, color: props.colors[si % props.colors.length] } : undefined
    })
  })

  if (props.multi && props.multi.length) {
    series = props.multi.map((m, si) => {
      const color = m.color || props.colors[si % props.colors.length]
      return {
        name: m.name,
        type: 'line',
        data: props.data.map((row) => {
          const v = row[m.key]
          return v == null ? null : Number(v)
        }),
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color },
        areaStyle: m.area === false ? undefined : { opacity: 0.12, color }
      }
    })
    chart.setOption({
      animation: false,
      tooltip: { trigger: 'axis', valueFormatter: (v) => v == null ? '-' : v >= 0 ? '+' + (v / 1e8).toFixed(2) + '亿' : (v / 1e8).toFixed(2) + '亿' },
      legend: { top: 0, right: 10, textStyle: { fontSize: 12 } },
      grid: { left: 50, right: 20, top: 30, bottom: 24 },
      xAxis: { type: 'category', data: labels, boundaryGap: false, axisLabel: { fontSize: 10 } },
      yAxis: {
        scale: true,
        splitLine: { lineStyle: { color: '#f0f0f0' } },
        axisLabel: { fontSize: 10, formatter: (v) => Math.abs(v) >= 1e8 ? (v / 1e8) + '亿' : v }
      },
      series
    })
    return
  }

  chart.setOption({
    animation: false,
    tooltip: { trigger: 'axis' },
    legend: series.length > 1 ? { top: 0, right: 10, textStyle: { fontSize: 12 } } : undefined,
    grid: { left: 50, right: 20, top: series.length > 1 ? 30 : 16, bottom: 24 },
    xAxis: { type: 'category', data: labels, boundaryGap: false, axisLabel: { fontSize: 10 } },
    yAxis: { scale: true, splitLine: { lineStyle: { color: '#f0f0f0' } } },
    series
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
watch(() => props.signals, render, { deep: true })
watch(() => props.showVwap, render)
watch(() => props.showT, render)
watch(() => props.preClose, render)
</script>
