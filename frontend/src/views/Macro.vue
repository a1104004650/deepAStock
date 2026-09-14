<template>
  <MainLayout>
    <div class="page">
      <div class="flex gap" style="align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h2 style="font-size:18px">宏观数据</h2>
        <el-tag size="small" type="info">{{ todayStr }}</el-tag>
        <el-button size="small" type="primary" :loading="loading" @click="loadAll(false)">刷新</el-button>
        <el-button size="small" type="warning" :loading="loading" @click="loadAll(true)">强制重新抓取</el-button>
        <span class="fs12" style="color:#909399">每日自动更新一次 · 数据来自 akshare（金十/统计局）</span>
      </div>

      <div v-if="lastFetched" class="fs12 mb8" style="color:#909399">
        上次更新：{{ lastFetched }} · 共 {{ indicators.length }} 项指标 ·
        <span :class="hasError ? 'down' : 'up'">{{ hasError ? '部分指标获取失败' : '全部正常' }}</span>
      </div>

      <!-- 按类别分组展示 -->
      <div v-for="grp in groups" :key="grp" class="mb16">
        <div class="fs14 bold mb8" style="color:#303133;border-left:3px solid #409eff;padding-left:8px">{{ grp }}</div>
        <el-row :gutter="10">
          <el-col v-for="ind in byGroup[grp]" :key="ind.key" :xs="24" :sm="12" :md="8" class="mb10">
            <div class="card indicator-card" :class="{ 'card-error': ind.error }">
              <div class="flex between" style="align-items:center">
                <span class="fs13 bold">{{ ind.name }}</span>
                <el-tag v-if="ind.error" size="small" type="info" effect="plain">暂不可用</el-tag>
                <el-tag v-else size="small" type="info" effect="plain">{{ ind.unit }}</el-tag>
              </div>
              <div v-if="!ind.error && ind.latest_value != null" class="mt8">
                <div class="flex gap" style="align-items:baseline">
                  <span class="mono fs22 bold" :class="pctCls(ind)">{{ fmtVal(ind) }}</span>
                  <span v-if="ind.delta != null" class="mono fs12" :class="pctCls(ind)">
                    {{ ind.delta > 0 ? '+' : '' }}{{ ind.delta }}
                  </span>
                </div>
                <div class="fs11 mt4" style="color:#909399">{{ ind.latest_date }}</div>
              </div>
              <div v-else-if="ind.error" class="mt8 fs12" style="color:#c0c4cc">数据源暂不可用：{{ ind.error }}</div>
              <div v-else class="mt8 fs12" style="color:#c0c4cc">暂无数据</div>
              <div v-if="ind.history?.length > 2" class="mt8">
                <div class="fs11 mb4" style="color:#c0c4cc">近 12 期走势</div>
                <LineChart :data="sparkData(ind)" :height="'80px'" :area="true" :show-avg="false" :colors="pctCls(ind) === 'up' ? ['#f56c6c'] : ['#67c23a']" />
              </div>
            </div>
          </el-col>
        </el-row>
      </div>

      <div class="fs11 mt16" style="color:#c0c4cc">
        数据来源：akshare（金十数据 / 国家统计局 / 中国人民银行） · 宏观指标按日更新一次 · 仅供参考，不构成投资建议
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import MainLayout from '../layout/MainLayout.vue'
import LineChart from '../components/LineChart.vue'
import { marketApi } from '../api'

const loading = ref(false)
const indicators = ref([])
const lastFetched = ref('')
const hasError = ref(false)

const GROUP_ORDER = ['价格', '景气', '增长', '消费', '贸易', '就业', '房价', '货币', '存款']
const groups = GROUP_ORDER
const byGroup = computed(() => {
  const m = {}
  for (const ind of indicators.value) {
    const g = ind.group || '其他'
    if (!m[g]) m[g] = []
    m[g].push(ind)
  }
  return m
})

function todayStr() {
  const d = new Date()
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function fmtVal(ind) {
  const v = ind.latest_value
  if (v == null) return '-'
  return Number(v).toFixed(2)
}

function pctCls(ind) {
  const v = Number(ind.latest_value)
  if (isNaN(v)) return 'flat'
  // Some indicators: higher is worse (unemployment); we keep neutral color
  // PMI: above 50 = expansion
  if (ind.key === 'pmi') return v >= 50 ? 'up' : 'down'
  return v >= 0 ? 'up' : 'down'
}

function sparkData(ind) {
  if (!ind.history?.length) return []
  const last12 = ind.history.slice(-12)
  return last12.map(h => ({ name: h.date.slice(5), value: h.value }))
}

async function loadAll(force = false) {
  loading.value = true
  try {
    const r = await marketApi.macro(force ? 1 : 0)
    indicators.value = r.indicators || []
    lastFetched.value = r.fetched_at || r.fetched_date || ''
    hasError.value = indicators.value.some(i => i.error)
  } catch (e) {
    indicators.value = []
    lastFetched.value = ''
    hasError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => loadAll(false))
</script>

<style scoped>
.mb16 { margin-bottom: 16px; }
.mb10 { margin-bottom: 10px; }
.fs22 { font-size: 22px; }
.indicator-card { min-height: 180px; }
.card-error { border-left: 3px solid #e6a23c; }
</style>
