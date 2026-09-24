<template>
  <MainLayout>
    <div class="page regime-page">
      <PageHeader
        eyebrow="MARKET REGIME"
        title="市场周期"
        subtitle="用市场宽度、涨停结构、接力连续性和板块轮动判断所处阶段，不用单日涨跌硬贴标签"
      >
        <template #badge><span class="method-tag">六阶段 · 可解释</span></template>
        <template #actions>
          <el-select v-model="historyDays" size="small" style="width:110px" @change="loadHistory">
            <el-option label="近10日" :value="10" />
            <el-option label="近20日" :value="20" />
            <el-option label="近30日" :value="30" />
          </el-select>
          <el-button size="small" :loading="loading" @click="loadAll">刷新</el-button>
        </template>
      </PageHeader>

      <div v-if="error" class="data-alert">{{ error }}</div>
      <div v-if="regime && !regime.data_available" class="data-alert">核心行情不可用，暂不生成周期结论，避免把缺失数据当成市场中性。</div>

      <section class="regime-command" :class="`tone-${regime?.stage?.tone || 'neutral'}`">
        <div class="stage-block">
          <div class="stage-kicker">CURRENT PHASE · {{ regime?.trade_date || '-' }}</div>
          <div class="stage-line">
            <strong>{{ regime?.stage?.label || '数据加载中' }}</strong>
            <span class="stage-score mono">{{ regime?.score == null ? '--' : regime.score }}</span>
          </div>
          <div class="stage-scale"><i :style="{ width: `${regime?.score || 0}%` }"></i></div>
          <div class="stage-meta">
            <span>可信度 {{ pct(regime?.confidence) }}</span>
            <span v-if="regime?.previous_score != null">前值 {{ regime.previous_score }} · {{ regime.previous_date }}</span>
          </div>
        </div>
        <div class="stage-map" aria-label="情绪周期六阶段">
          <div v-for="step in stages" :key="step.code" :class="{ active: regime?.stage?.code === step.code }">
            <span>{{ step.label }}</span><small>{{ step.hint }}</small>
          </div>
        </div>
      </section>

      <section class="component-grid">
        <article v-for="item in componentCards" :key="item.key" class="regime-card" :class="{ unavailable: !item.available }">
          <header><span>{{ item.index }}</span><h2>{{ item.title }}</h2><b>{{ item.available ? item.score : '--' }}</b></header>
          <p>{{ item.description }}</p>
          <div class="evidence-grid">
            <div v-for="metric in item.metrics" :key="metric.label"><small>{{ metric.label }}</small><strong class="mono">{{ metric.value }}</strong></div>
          </div>
          <footer>{{ item.basis }}</footer>
        </article>
      </section>

      <section class="regime-lower">
        <article class="card trend-panel">
          <div class="panel-head">
            <div><h2>阶段轨迹</h2><p>历史分数按交易日排列，接力指标必须有前一日快照才参与计算</p></div>
            <div class="legend"><span class="score-dot"></span>周期分<span class="up-dot"></span>上涨占比<span class="risk-dot"></span>断板率</div>
          </div>
          <div ref="chartEl" class="regime-chart"></div>
          <el-empty v-if="!history.length && !loading" description="暂无历史复盘快照" :image-size="54" />
        </article>

        <aside class="side-stack">
          <article class="card signal-panel">
            <div class="panel-head"><div><h2>今日证据</h2><p>结论只来自下列可核验字段</p></div></div>
            <div v-if="regime?.signals?.length" class="signal-list">
              <div v-for="(signal, i) in regime.signals" :key="signal"><b class="mono">{{ String(i + 1).padStart(2, '0') }}</b><span>{{ signal }}</span></div>
            </div>
            <el-empty v-else description="暂无有效证据" :image-size="42" />
          </article>
          <article class="card leaders-panel">
            <div class="panel-head"><div><h2>资金主线</h2><p>按板块净流入排序，仅作轮动强弱证据</p></div></div>
            <div v-for="(s, i) in leaders" :key="s.name" class="leader-row">
              <b>{{ i + 1 }}</b><span>{{ s.name }}</span><em :class="Number(s.change_pct || 0) >= 0 ? 'up' : 'down'">{{ signed(s.change_pct) }}</em><strong class="mono" :class="Number(s.net_inflow || 0) >= 0 ? 'up' : 'down'">{{ money(s.net_inflow) }}</strong>
            </div>
            <el-empty v-if="!leaders.length" description="板块资金数据不可用" :image-size="42" />
          </article>
        </aside>
      </section>

      <section class="method-note">
        <strong>口径说明</strong>
        <span>{{ regime?.methodology || '等待数据' }}</span>
        <span>“断板率”是跨日集合代理，不是盘中触板后开板的炸板率；缺失分项会降低可信度，不会按0分惩罚。</span>
      </section>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import MainLayout from '../layout/MainLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import { marketApi } from '../api'

const regime = ref(null)
const history = ref([])
const historyDays = ref(20)
const loading = ref(false)
const error = ref('')
const chartEl = ref(null)
let chart = null

const stages = [
  { code: 'ice', label: '冰点', hint: '风险释放' },
  { code: 'start', label: '启动', hint: '增量改善' },
  { code: 'markup', label: '主升', hint: '扩散接力' },
  { code: 'climax', label: '高潮', hint: '拥挤过热' },
  { code: 'decline', label: '退潮', hint: '负反馈' },
  { code: 'repair', label: '修复', hint: '分歧收敛' },
]

const c = computed(() => regime.value?.components || {})
const leaders = computed(() => c.value.rotation?.leaders || [])
const componentCards = computed(() => [
  { key: 'breadth', index: '01', title: '市场宽度', score: fmtScore(c.value.breadth?.score), available: c.value.breadth?.available, description: '看赚钱效应是否扩散到多数股票，而不是只看指数。', basis: '权重35% · 上涨家数占全市场比例', metrics: [
    { label: '上涨', value: c.value.breadth?.up_count ?? '-' }, { label: '下跌', value: c.value.breadth?.down_count ?? '-' }, { label: '上涨占比', value: pct100(c.value.breadth?.up_ratio) },
  ] },
  { key: 'limit', index: '02', title: '涨停结构', score: fmtScore(c.value.limit_structure?.score), available: c.value.limit_structure?.available, description: '观察首板供给、连板接力与市场高度是否形成正反馈。', basis: '权重30% · 涨跌停平衡 + 连板率 + 空间高度', metrics: [
    { label: '涨/跌停', value: `${c.value.limit_structure?.limit_up ?? '-'}/${c.value.limit_structure?.limit_down ?? '-'}` }, { label: '连板', value: c.value.limit_structure?.multi_board ?? '-' }, { label: '最高板', value: c.value.limit_structure?.max_board ? `${c.value.limit_structure.max_board}板` : '-' },
  ] },
  { key: 'continuity', index: '03', title: '接力连续性', score: fmtScore(c.value.continuity?.score), available: c.value.continuity?.available, description: '用前后交易日集合确认接力，不用单日结果猜周期。', basis: '权重20% · 首板晋级率 + 断板率（跨日代理）', metrics: [
    { label: '晋级率', value: pct100(c.value.continuity?.promotion_rate) }, { label: '断板率', value: pct100(c.value.continuity?.broken_rate) }, { label: '历史基准', value: regime.value?.previous_date || '-' },
  ] },
  { key: 'rotation', index: '04', title: '板块轮动', score: fmtScore(c.value.rotation?.score), available: c.value.rotation?.available, description: '确认资金是否形成多个正向板块，而非孤立拉升。', basis: '权重15% · 净流入为正的板块占比', metrics: [
    { label: '正流入', value: c.value.rotation?.positive_sectors ?? '-' }, { label: '统计板块', value: c.value.rotation?.sector_count ?? '-' }, { label: '主线', value: leaders.value[0]?.name || '-' },
  ] },
])

function fmtScore(v) { return v == null ? '--' : Number(v).toFixed(0) }
function pct(v) { return v == null ? '--' : `${Math.round(Number(v) * 100)}%` }
function pct100(v) { return v == null ? '--' : `${Number(v).toFixed(1)}%` }
function signed(v) { return v == null ? '-' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%` }
function money(v) { const n = Number(v); if (!Number.isFinite(n)) return '-'; return `${n >= 0 ? '+' : ''}${(n / 1e8).toFixed(1)}亿` }

async function loadHistory() {
  try { history.value = await marketApi.regimeHistory(historyDays.value) || [] } catch { history.value = [] }
  await nextTick()
  renderChart()
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [current, past] = await Promise.all([marketApi.regime(), marketApi.regimeHistory(historyDays.value)])
    regime.value = current || null
    history.value = past || []
  } catch (e) {
    error.value = e?.message || '市场周期数据加载失败'
  } finally {
    loading.value = false
    await nextTick()
    renderChart()
  }
}

function renderChart() {
  if (!chartEl.value || !history.value.length) { chart?.dispose(); chart = null; return }
  if (!chart) chart = echarts.init(chartEl.value)
  const rows = history.value
  chart.setOption({
    animationDuration: 320,
    grid: { left: 42, right: 42, top: 34, bottom: 30 },
    tooltip: { trigger: 'axis', formatter: (items) => items.map(i => `${i.marker}${i.seriesName}: ${i.value ?? '-'}${i.seriesName === '周期分' ? '' : '%'}`).join('<br>') },
    xAxis: { type: 'category', data: rows.map(r => r.date.slice(5)), axisLine: { lineStyle: { color: '#d3d9e0' } }, axisLabel: { color: '#7b8492' } },
    yAxis: [{ type: 'value', min: 0, max: 100, splitLine: { lineStyle: { color: '#edf0f4' } }, axisLabel: { color: '#7b8492' } }, { type: 'value', min: 0, max: 100, show: false }],
    series: [
      { name: '周期分', type: 'line', data: rows.map(r => r.score), symbolSize: 6, lineStyle: { width: 3, color: '#2e6bc6' }, itemStyle: { color: '#2e6bc6' }, areaStyle: { color: 'rgba(46,107,198,.08)' }, connectNulls: false },
      { name: '上涨占比', type: 'line', data: rows.map(r => r.up_ratio), symbol: 'none', lineStyle: { width: 1.5, color: '#ef232a' } },
      { name: '断板率', type: 'line', data: rows.map(r => r.has_previous ? r.broken_rate : null), symbol: 'none', lineStyle: { width: 1.5, type: 'dashed', color: '#14b143' } },
    ],
  }, true)
  chart.resize()
}

function handleResize() { chart?.resize() }
onMounted(() => { loadAll(); window.addEventListener('resize', handleResize) })
onBeforeUnmount(() => { window.removeEventListener('resize', handleResize); chart?.dispose() })
</script>

<style scoped>
.regime-page { padding-bottom:32px; }
.method-tag { color:#2e6bc6; background:#edf4ff; border:1px solid #cadcf7; padding:3px 7px; font:600 10px var(--font-mono); letter-spacing:.04em; }
.data-alert { margin:0 0 10px; padding:9px 12px; border:1px solid #e9c46a; background:#fff8e6; color:#765411; font-size:12px; }
.regime-command { display:grid; grid-template-columns:minmax(280px, .85fr) minmax(520px, 1.5fr); gap:0; background:var(--c-navy); color:#fff; border-radius:var(--radius-md); overflow:hidden; box-shadow:0 12px 32px rgba(17,27,45,.16); }
.stage-block { padding:22px 24px; border-right:1px solid rgba(255,255,255,.12); }
.stage-kicker { color:#93a4bc; font:600 10px var(--font-mono); letter-spacing:.13em; }
.stage-line { display:flex; justify-content:space-between; align-items:flex-end; margin:13px 0 14px; }
.stage-line strong { color:#fff; font-size:36px; line-height:1; letter-spacing:-.06em; }
.stage-score { font-size:30px; color:#fff; }
.stage-scale { height:4px; background:rgba(255,255,255,.12); overflow:hidden; }
.stage-scale i { display:block; height:100%; background:#7da8e8; transition:width .35s ease; }
.tone-hot .stage-scale i { background:var(--c-up); }.tone-cold .stage-scale i { background:var(--c-down); }
.stage-meta { display:flex; justify-content:space-between; gap:12px; color:#aab8cb; font:11px var(--font-mono); margin-top:10px; }
.stage-map { display:grid; grid-template-columns:repeat(6, 1fr); align-items:stretch; padding:12px; }
.stage-map div { position:relative; display:flex; flex-direction:column; justify-content:center; gap:6px; padding:16px 12px; border-left:1px solid rgba(255,255,255,.08); color:#8393aa; }
.stage-map div:first-child { border-left:0; }
.stage-map div.active { color:#fff; background:rgba(255,255,255,.07); }
.stage-map div.active::after { content:''; position:absolute; left:12px; right:12px; bottom:7px; height:2px; background:#7da8e8; }
.tone-hot .stage-map div.active::after { background:var(--c-up); }.tone-cold .stage-map div.active::after { background:var(--c-down); }
.stage-map span { font-size:14px; font-weight:700; }.stage-map small { font-size:10px; color:inherit; white-space:nowrap; }
.component-grid { display:grid; grid-template-columns:repeat(4, 1fr); gap:10px; margin-top:10px; }
.regime-card { background:#fff; border:1px solid var(--c-border); border-top:3px solid var(--c-navy); padding:13px 14px 11px; min-width:0; }
.regime-card.unavailable { opacity:.58; border-top-color:var(--c-flat); }
.regime-card header { display:grid; grid-template-columns:24px 1fr auto; align-items:center; gap:7px; }
.regime-card header span { color:var(--c-primary); font:600 10px var(--font-mono); }.regime-card h2,.panel-head h2 { font-size:14px; }.regime-card header b { font:700 23px var(--font-mono); }
.regime-card > p { color:var(--c-text-2); font-size:11px; line-height:1.55; min-height:35px; margin:9px 0; }
.evidence-grid { display:grid; grid-template-columns:repeat(3,1fr); border-top:1px solid var(--c-border); border-bottom:1px solid var(--c-border); }
.evidence-grid div { padding:8px 5px; border-left:1px solid var(--c-border); min-width:0; }.evidence-grid div:first-child { border-left:0; }
.evidence-grid small { display:block; color:var(--c-text-3); font-size:9px; margin-bottom:3px; }.evidence-grid strong { display:block; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.regime-card footer { color:var(--c-text-3); font-size:9px; margin-top:8px; }
.regime-lower { display:grid; grid-template-columns:minmax(0,1.65fr) minmax(300px,.75fr); gap:10px; margin-top:10px; }
.trend-panel,.signal-panel,.leaders-panel { padding:13px 14px; }
.panel-head { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; margin-bottom:8px; }.panel-head p { color:var(--c-text-3); font-size:10px; margin-top:3px; }
.legend { display:flex; gap:9px; align-items:center; font-size:10px; color:var(--c-text-3); white-space:nowrap; }.legend span { width:8px; height:8px; border-radius:50%; }.score-dot{background:#2e6bc6}.up-dot{background:#ef232a}.risk-dot{background:#14b143}
.regime-chart { height:306px; }
.side-stack { display:grid; gap:10px; }
.signal-list { display:grid; gap:0; }.signal-list div { display:grid; grid-template-columns:30px 1fr; gap:8px; padding:8px 2px; border-top:1px solid var(--c-border); font-size:11px; }.signal-list b { color:var(--c-primary); }
.leader-row { display:grid; grid-template-columns:20px 1fr 58px 70px; align-items:center; gap:6px; padding:7px 2px; border-top:1px solid var(--c-border); font-size:11px; }.leader-row > b { color:var(--c-text-3); font:10px var(--font-mono); }.leader-row em { font-style:normal; text-align:right; }.leader-row strong { text-align:right; font-size:10px; }
.method-note { display:grid; grid-template-columns:76px 1fr 1.25fr; gap:12px; margin-top:10px; padding:10px 12px; border-left:3px solid var(--c-primary); background:#f7f9fc; color:var(--c-text-2); font-size:10px; line-height:1.55; }
@media (max-width:1100px) { .regime-command { grid-template-columns:1fr; }.stage-block { border-right:0; border-bottom:1px solid rgba(255,255,255,.12); }.component-grid { grid-template-columns:repeat(2,1fr); }.regime-lower { grid-template-columns:1fr; } }
@media (max-width:700px) { .stage-map { grid-template-columns:repeat(3,1fr); }.stage-map div:nth-child(4) { border-left:0; }.component-grid { grid-template-columns:1fr; }.method-note { grid-template-columns:1fr; }.stage-line strong { font-size:30px; }.leader-row { grid-template-columns:18px 1fr 54px 64px; } }
</style>
