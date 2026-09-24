<template>
  <MainLayout>
    <div class="page fund-page">
      <PageHeader eyebrow="FUND / ETF MONITOR" title="基金与ETF" subtitle="免费行情源提供的ETF资金流与主题观察，不构成基金投资建议">
        <template #actions><el-button type="primary" size="small" :loading="loading" @click="load">刷新数据</el-button></template>
      </PageHeader>
      <div class="fund-note"><el-icon><InfoFilled /></el-icon>当前数据重点覆盖ETF资金流向，暂不伪造主动基金净值和估值；适合用来观察主题资金偏好。</div>
      <div class="fund-grid">
        <section class="fund-panel">
          <div class="panel-title"><span>资金流入 TOP</span><el-tag type="danger" size="small">近1日</el-tag></div>
          <FundTable :rows="data.in_top" positive />
        </section>
        <section class="fund-panel">
          <div class="panel-title"><span>资金流出 TOP</span><el-tag type="success" size="small">近1日</el-tag></div>
          <FundTable :rows="data.out_top" />
        </section>
      </div>
      <section class="fund-panel mt12">
        <div class="panel-title"><span>ETF资金流全景</span><span class="panel-hint">单位：亿元 · 1日 / 5日 / 20日</span></div>
        <el-table :data="data.all" size="small" stripe empty-text="暂无ETF资金流数据">
          <el-table-column prop="symbol" label="代码" width="100" />
          <el-table-column prop="name" label="名称" min-width="150" />
          <el-table-column label="1日净流" align="right"><template #default="{ row }"><span :class="flowCls(row.net_1d)">{{ signed(row.net_1d) }}</span></template></el-table-column>
          <el-table-column label="5日净流" align="right"><template #default="{ row }"><span :class="flowCls(row.net_5d)">{{ signed(row.net_5d) }}</span></template></el-table-column>
          <el-table-column label="20日净流" align="right"><template #default="{ row }"><span :class="flowCls(row.net_20d)">{{ signed(row.net_20d) }}</span></template></el-table-column>
          <el-table-column prop="flow_date" label="数据日期" width="110" />
        </el-table>
      </section>
    </div>
  </MainLayout>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import MainLayout from '../layout/MainLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import { marketApi } from '../api'

const loading = ref(false)
const data = reactive({ in_top: [], out_top: [], all: [] })
const signed = (v) => `${Number(v || 0) >= 0 ? '+' : ''}${Number(v || 0).toFixed(2)}`
const flowCls = (v) => Number(v || 0) >= 0 ? 'up' : 'down'
async function load() {
  loading.value = true
  try {
    const r = await marketApi.etfFlow()
    data.in_top = r?.in_top || []; data.out_top = r?.out_top || []; data.all = r?.all || []
  } finally { loading.value = false }
}
onMounted(load)
</script>

<script>
export default {
  components: {
    FundTable: {
      props: { rows: { type: Array, default: () => [] }, positive: Boolean },
      template: `<el-table :data="rows" size="small" stripe empty-text="暂无数据">
        <el-table-column prop="symbol" label="代码" width="100" />
        <el-table-column prop="name" label="名称" min-width="130" />
        <el-table-column label="1日净流" align="right"><template #default="{ row }"><span :class="Number(row.net_1d || 0) >= 0 ? 'up' : 'down'">{{ Number(row.net_1d || 0) >= 0 ? '+' : '' }}{{ Number(row.net_1d || 0).toFixed(2) }}</span></template></el-table-column>
        <el-table-column label="5日净流" align="right"><template #default="{ row }">{{ Number(row.net_5d || 0).toFixed(2) }}</template></el-table-column>
      </el-table>`
    }
  }
}
</script>

<style scoped>
.fund-note { display:flex; align-items:center; gap:7px; color:#7d8390; background:#fffaf0; border:1px solid #f3dfb5; border-radius:6px; padding:9px 11px; font-size:12px; }
.fund-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:12px; }
.fund-panel { background:#fff; border:1px solid var(--c-border); border-radius:7px; padding:12px; box-shadow:var(--shadow-card); }
.panel-title { display:flex; align-items:center; justify-content:space-between; gap:8px; font-size:14px; font-weight:700; color:var(--c-ink); margin-bottom:9px; }
.panel-hint { color:#9aa3af; font-size:11px; font-weight:400; }
.mt12 { margin-top:12px; }
@media (max-width:820px) { .fund-grid { grid-template-columns:1fr; } }
</style>
