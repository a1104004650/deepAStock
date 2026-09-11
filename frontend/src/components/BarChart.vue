<template>
  <div ref="el" class="chart" :style="{ height }"></div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
  height: { type: String, default: '220px' }
})

const el = ref(null)
let chart = null

function render() {
  if (!chart) return
  const rows = Array.isArray(props.data) ? props.data : []
  const labels = rows.map((r) => r.label ?? r.name ?? r.time ?? r.date ?? '')
  const values = rows.map((r) => r.count ?? r.value ?? 0)
  chart.setOption({
    animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 16, bottom: 28 },
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { fontSize: 10 }
    },
    series: [{
      type: 'bar',
      data: values,
      barWidth: '62%',
      itemStyle: {
        borderRadius: [3, 3, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#409eff' },
          { offset: 1, color: '#a0cfff' }
        ])
      }
    }]
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