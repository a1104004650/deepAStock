<template>
  <div ref="el" class="chart" :style="{ height }"></div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
  height: { type: String, default: '260px' },
  area: { type: Boolean, default: true },
  colors: { type: Array, default: () => ['#409eff'] },
  showAvg: { type: Boolean, default: true },
  volume: { type: Boolean, default: false },
  multi: { type: Array, default: () => [] }
})

const el = ref(null)
let chart = null

function minuteAxis() {
  const labels = []
  for (let mt = 9 * 60 + 15; mt <= 15 * 60; mt++) {
    // 去除午间休市(11:31-12:59)，分时线跨午休直连，不预留白
    if (mt >= 11 * 60 + 31 && mt <= 12 * 60 + 59) continue
    const hh = String(Math.floor(mt / 60)).padStart(2, '0')
    const mm = String(mt % 60).padStart(2, '0')
    labels.push(`${hh}:${mm}`)
  }
  return labels
}

function render() {
  if (!chart || !Array.isArray(props.data) || !props.data.length) return
  const labels = []
  let series = []

  const first = props.data[0]
  const isMinute = first && typeof first === 'object' &&
    typeof first.time === 'string' && /^\d{1,2}:\d{2}$/.test(first.time) &&
    first.avg !== undefined

  if (isMinute) {
    // 分时图：09:15(竞价)~15:00，跳过午休(11:31-12:59)，未到时刻留白，同步均价线
    const minutes = minuteAxis()
    const timeIdx = {}
    minutes.forEach((t, i) => { timeIdx[t] = i })
    labels.push(...minutes)
    const price = new Array(minutes.length).fill(null)
    const avg = new Array(minutes.length).fill(null)
    const volDelta = new Array(minutes.length).fill(null)
    let prevPrice = null
    let found = 0
    for (const row of props.data) {
      const idx = timeIdx[row.time]
      if (idx === undefined) continue
      const p = row.price ?? null
      price[idx] = p
      // 均价线：与价格偏差过大(指数分时单位异常)则视为无效丢弃，避免y轴被压平
      if (props.showAvg && row.avg !== undefined && row.avg !== null && p &&
        Math.abs(row.avg - p) / p <= 0.3) avg[idx] = row.avg
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
    series = [
      {
        name: '价格',
        type: 'line',
        data: price,
        smooth: true,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { width: 1.5, color: props.colors[0] || '#409eff' },
        areaStyle: props.area ? { opacity: 0.15, color: props.colors[0] || '#409eff' } : undefined
      }
    ]
    if (props.showAvg) {
      series.push({
        name: '均价',
        type: 'line',
        data: avg,
        smooth: true,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { width: 1.2, color: props.colors[1] || '#e6a23c', type: 'dashed' }
      })
    }
    if (props.volume) {
      series.push({
        name: '成交量',
        type: 'bar',
        data: volDelta,
        xAxisIndex: 1,
        yAxisIndex: 1,
        barWidth: '70%'
      })
    }
    const valid = price.filter((x) => x != null)
    let minV = Math.min(...valid); let maxV = Math.max(...valid)
    const pad = Math.max((maxV - minV) * 0.08, maxV * 0.0005)
    if (maxV - minV < pad) { minV -= pad; maxV += pad }
    chart.setOption({
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: series.length > 1 ? { top: 0, right: 10, textStyle: { fontSize: 12 } } : undefined,
      grid: props.volume
        ? [
            { left: 50, right: 20, top: series.length > 1 ? 30 : 16, height: '64%' },
            { left: 50, right: 20, top: '82%', height: '10%' }
          ]
        : { left: 50, right: 20, top: series.length > 1 ? 30 : 16, bottom: 24 },
      xAxis: props.volume
        ? [
            { type: 'category', data: labels, boundaryGap: false, axisLabel: { fontSize: 10 } },
            { type: 'category', gridIndex: 1, data: labels, show: false }
          ]
        : { type: 'category', data: labels, boundaryGap: false, axisLabel: { fontSize: 10 } },
      yAxis: props.volume
        ? [
            { scale: true, min: minV, max: maxV, splitLine: { lineStyle: { color: '#f0f0f0' } }, axisLabel: { fontSize: 10 } },
            { gridIndex: 1, scale: true, splitLine: { show: false }, axisLabel: { show: false } }
          ]
        : { scale: true, min: minV, max: maxV, splitLine: { lineStyle: { color: '#f0f0f0' } } },
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
    // 多序列对比图（如 主力/超大/大/中/小 净流入），labels 取首个数据点的 date/time
    const keys = props.multi.map((m) => m.key)
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
</script>