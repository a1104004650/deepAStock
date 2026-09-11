<template>
  <div ref="el" class="hqminute" :style="{ height }"></div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
  height: { type: String, default: '260px' },
  title: { type: String, default: '' },
  preClose: { type: Number, default: 0 },
})

const el = ref(null)
let chart = null

function render() {
  if (!chart || !Array.isArray(props.data) || !props.data.length) return
  const d = props.data
  const times = d.map(x => x.time)
  const prices = d.map(x => x.price)
  const avgs = d.map(x => x.avg)
  const volumes = d.map(x => x.volume || 0)
  const preClose = props.preClose || prices[0] || 0

  const series = [
    {
      name: '价格', type: 'line', data: prices, symbol: 'none', smooth: true,
      lineStyle: { width: 1.5, color: '#2f7ef9' },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(47,126,249,0.15)' },
        { offset: 1, color: 'rgba(47,126,249,0.01)' }
      ]) }
    },
    {
      name: '均价', type: 'line', data: avgs, symbol: 'none', smooth: true,
      lineStyle: { width: 1, color: '#f59e0b', type: 'dashed' }
    },
    {
      name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volumes,
      itemStyle: { color: 'rgba(47,126,249,0.35)' }
    }
  ]

  const option = {
    backgroundColor: '#fff', animation: false,
    title: props.title ? { text: props.title, left: 8, top: 4, textStyle: { fontSize: 14 } } : undefined,
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        const i = params[0]?.dataIndex ?? 0
        const p = prices[i]
        const chg = preClose ? (((p - preClose) / preClose) * 100).toFixed(2) : '0'
        return `<b>${times[i]}</b><br/>价格 ${p}<br/>涨幅 ${Number(chg) >= 0 ? '+' : ''}${chg}%<br/>均价 ${avgs[i]}`
      }
    },
    legend: { top: 4, right: 12, data: ['价格', '均价'], textStyle: { fontSize: 10 } },
    grid: [
      { left: 55, right: 16, top: 30, height: '55%' },
      { left: 55, right: 16, top: '75%', height: '12%' },
    ],
    xAxis: [
      { type: 'category', data: times, boundaryGap: false, axisLine: { lineStyle: { color: '#ddd' } }, axisLabel: { fontSize: 10 } },
      { type: 'category', gridIndex: 1, data: times, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#ddd' } } },
    ],
    yAxis: [
      { scale: true, splitLine: { lineStyle: { color: '#f0f0f0' } }, axisLabel: { fontSize: 10 } },
      { gridIndex: 1, splitNumber: 2, splitLine: { show: false }, axisLabel: { fontSize: 9, formatter: v => v >= 1e4 ? (v / 1e4).toFixed(0) + '万' : v } },
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1] }],
    series,
  }
  if (preClose > 0) {
    option.markLine = {
      silent: true, symbol: 'none',
      data: [{ yAxis: preClose, lineStyle: { color: '#999', type: 'dashed', width: 1 }, label: { show: true, formatter: `昨收 ${preClose}`, position: 'insideEndTop', fontSize: 9 } }]
    }
  }
  chart.setOption(option, true)
}

function resize() { chart && chart.resize() }
onMounted(() => { chart = echarts.init(el.value); render(); window.addEventListener('resize', resize) })
onBeforeUnmount(() => { window.removeEventListener('resize', resize); chart && chart.dispose() })
watch(() => [props.data, props.preClose], render, { deep: true })
</script>

<style scoped>
.hqminute { width: 100%; }
</style>
