<template>
  <MainLayout>
    <div class="page screening-page">
      <PageHeader eyebrow="SCREENER / SHORT TERM" title="智能选股" subtitle="免费实时行情初筛，不替代基本面与风险判断">
        <template #actions>
          <span v-if="result.source" class="source-note">数据：{{ result.source }}</span>
          <el-button type="primary" :loading="loading" @click="runScreening">重新扫描</el-button>
        </template>
      </PageHeader>

      <el-card shadow="never" class="filter-card">
        <div class="filter-grid">
          <label>涨跌幅下限<el-input-number v-model="filters.min_change" :min="-20" :max="20" :step="0.5" controls-position="right" /></label>
          <label>涨跌幅上限<el-input-number v-model="filters.max_change" :min="-20" :max="20" :step="0.5" controls-position="right" /></label>
          <label>成交额下限（万元）<el-input-number v-model="filters.min_turnover" :min="0" :step="1000" controls-position="right" /></label>
          <label>热度下限<el-input-number v-model="filters.min_heat" :min="0" :max="100" :step="5" controls-position="right" /></label>
          <label>返回数量<el-select v-model="filters.limit"><el-option v-for="n in [20, 50, 100, 200]" :key="n" :label="`${n} 条`" :value="n" /></el-select></label>
        </div>
      </el-card>

      <div class="summary-row">
        <div class="summary-item"><span>命中标的</span><strong>{{ result.items.length }}</strong></div>
        <div class="summary-item"><span>平均热度</span><strong>{{ averageHeat }}</strong></div>
        <div class="summary-item"><span>上涨/下跌</span><strong><i class="up">{{ risingCount }}</i> / <i class="down">{{ fallingCount }}</i></strong></div>
        <div class="summary-item note">筛选结果按热度降序排列，点击代码进入个股研究</div>
      </div>

      <el-card shadow="never" class="table-card">
        <el-table v-loading="loading" :data="result.items" stripe size="small" empty-text="没有满足条件的标的，放宽筛选条件后重试">
          <el-table-column label="标的" min-width="180">
            <template #default="{ row }">
              <button class="stock-link" @click="openStock(row)">{{ row.name || '-' }} <small>{{ row.symbol }}</small></button>
            </template>
          </el-table-column>
          <el-table-column prop="price" label="现价" width="100" align="right" />
          <el-table-column label="涨跌幅" width="110" align="right">
            <template #default="{ row }"><span :class="row.change_pct >= 0 ? 'up' : 'down'">{{ signed(row.change_pct) }}%</span></template>
          </el-table-column>
          <el-table-column prop="turnover" label="成交额(万)" width="130" align="right" />
          <el-table-column prop="hsl" label="换手率" width="100" align="right" />
          <el-table-column prop="lb" label="量比" width="90" align="right" />
          <el-table-column label="热度" width="110" align="right">
            <template #default="{ row }"><el-progress :percentage="Math.min(100, Number(row.heat || 0))" :stroke-width="7" :show-text="false" /><span class="heat-value">{{ row.heat }}</span></template>
          </el-table-column>
          <el-table-column prop="screen_reason" label="命中原因" min-width="190" />
        </el-table>
      </el-card>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import MainLayout from '../layout/MainLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import { marketApi } from '../api'

const router = useRouter()
const loading = ref(false)
const filters = reactive({ min_change: -10, max_change: 10, min_turnover: 0, min_heat: 0, limit: 50 })
const result = reactive({ items: [], source: '' })

const risingCount = computed(() => result.items.filter((x) => Number(x.change_pct || 0) >= 0).length)
const fallingCount = computed(() => result.items.length - risingCount.value)
const averageHeat = computed(() => result.items.length ? (result.items.reduce((s, x) => s + Number(x.heat || 0), 0) / result.items.length).toFixed(1) : '-')

function signed(value) {
  const n = Number(value || 0)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

function openStock(row) {
  router.push({ path: '/watchlist', query: { symbol: row.symbol } })
}

async function runScreening() {
  if (filters.min_change > filters.max_change) {
    ElMessage.warning('涨跌幅下限不能大于上限')
    return
  }
  loading.value = true
  try {
    const data = await marketApi.screening({ ...filters })
    result.items = data.items || []
    result.source = data.source || ''
  } catch {
    result.items = []
  } finally {
    loading.value = false
  }
}

onMounted(runScreening)
</script>

<style scoped>
.screening-page { max-width: 1500px; }
.screening-head { display:flex; justify-content:space-between; align-items:flex-end; gap:20px; margin-bottom:14px; }
.eyebrow { color:var(--c-primary); font:600 11px var(--font-mono); letter-spacing:.08em; text-transform:uppercase; }
h1 { margin:5px 0; font-size:24px; color:var(--c-text-1); }
.screening-head p { color:var(--c-text-3); font-size:12px; }
.head-actions { display:flex; align-items:center; gap:12px; }
.source-note { color:var(--c-text-3); font-size:11px; }
.filter-card, .table-card { border-color:var(--c-border); margin-bottom:12px; }
.filter-grid { display:grid; grid-template-columns:repeat(5, minmax(140px, 1fr)); gap:12px; }
.filter-grid label { display:flex; flex-direction:column; gap:6px; color:var(--c-text-2); font-size:12px; }
.filter-grid .el-input-number, .filter-grid .el-select { width:100%; }
.summary-row { display:grid; grid-template-columns:repeat(3, minmax(130px, 1fr)) 2fr; gap:10px; margin-bottom:12px; }
.summary-item { background:var(--c-bg-card); border:1px solid var(--c-border); padding:10px 12px; border-radius:var(--radius-sm); color:var(--c-text-3); font-size:11px; }
.summary-item strong { display:block; color:var(--c-text-1); font:600 18px var(--font-mono); margin-top:4px; }
.summary-item strong i { font-style:normal; }
.summary-item.note { display:flex; align-items:center; color:var(--c-text-3); }
.stock-link { border:0; background:none; color:var(--c-primary); cursor:pointer; padding:0; text-align:left; font-weight:600; }
.stock-link small { display:block; color:var(--c-text-3); font:normal 11px var(--font-mono); margin-top:2px; }
.heat-value { display:inline-block; margin-left:8px; font:11px var(--font-mono); color:var(--c-text-2); vertical-align:top; }
@media (max-width:820px) {
  .screening-head { align-items:flex-start; flex-direction:column; }
  .head-actions { width:100%; justify-content:space-between; }
  .filter-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .summary-row { grid-template-columns:repeat(2, 1fr); }
  .summary-item.note { grid-column:1 / -1; min-height:42px; }
}
</style>
