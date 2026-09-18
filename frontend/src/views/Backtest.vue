<template>
  <MainLayout>
    <div class="page">
      <div class="flex between" style="align-items:center;margin-bottom:10px">
        <h2 style="font-size:18px">策略回测</h2>
        <el-button size="small" @click="openManager">策略管理（编辑 / 新增 / 自己写）</el-button>
      </div>

      <el-row :gutter="10">
        <el-col :xs="24" :sm="8" :md="6">
          <div class="card">
            <div class="fs14 bold mb8">回测参数</div>
            <el-form label-position="top" @submit.prevent>
              <el-form-item label="回测模式">
                <el-radio-group v-model="mode" size="small" style="width:100%">
                  <el-radio-button label="single">单只标的</el-radio-button>
                  <el-radio-button label="portfolio">自选组合</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item v-if="mode === 'single'" label="股票">
                <el-select
                  v-model="form.symbol"
                  filterable
                  remote
                  :remote-method="doSearch"
                  :loading="searchLoading"
                  placeholder="输入代码/名称搜索"
                  style="width:100%"
                >
                  <el-option
                    v-for="r in searchResults"
                    :key="r.symbol"
                    :label="`${r.name} (${r.symbol})`"
                    :value="r.symbol"
                  />
                </el-select>
              </el-form-item>
              <el-form-item v-else label="组合股票（最多 20 只，自己选股自己买卖）">
                <el-select
                  v-model="form.symbols"
                  multiple
                  filterable
                  remote
                  :remote-method="doSearch"
                  :loading="searchLoading"
                  placeholder="输入代码/名称搜索后回车选择"
                  style="width:100%"
                >
                  <el-option
                    v-for="r in searchResults"
                    :key="r.symbol"
                    :label="`${r.name} (${r.symbol})`"
                    :value="r.symbol"
                  />
                </el-select>
                <el-button size="small" style="width:100%;margin-top:6px" @click="openWatchlistImport">
                  从自选股导入
                </el-button>
              </el-form-item>
              <el-form-item label="策略">
                <el-select
                  v-model="form.strategy"
                  style="width:100%"
                  @change="onStrategyChange"
                >
                  <el-option
                    v-for="s in visibleStrategies"
                    :key="s.key"
                    :label="s.name"
                    :value="s.key"
                  >
                    <span>{{ s.name }}</span>
                    <el-tag v-if="s.is_builtin" size="small" type="info" style="margin-left:6px">内置</el-tag>
                  </el-option>
                </el-select>
              </el-form-item>
              <el-form-item v-if="activeSchema.length" label="策略参数">
                <div style="width:100%">
                  <div v-for="p in activeSchema" :key="p.key" class="mb8">
                    <div class="fs12 mb4" style="color:#606266">{{ p.label }}</div>
                    <el-input-number
                      v-if="p.type === 'int' || p.type === 'number'"
                      v-model="paramsInputs[p.key]"
                      :min="p.min != null ? p.min : undefined"
                      :max="p.max != null ? p.max : undefined"
                      :step="p.step || 1"
                      style="width:100%"
                    />
                    <el-select
                      v-else-if="p.type === 'select'"
                      v-model="paramsInputs[p.key]"
                      style="width:100%"
                    >
                      <el-option
                        v-for="o in p.options || []"
                        :key="o.value != null ? o.value : o"
                        :label="o.label != null ? o.label : o"
                        :value="o.value != null ? o.value : o"
                      />
                    </el-select>
                    <el-switch v-else-if="p.type === 'bool'" v-model="paramsInputs[p.key]" />
                    <el-input
                      v-else
                      v-model="paramsInputs[p.key]"
                      :placeholder="p.placeholder || p.label"
                    />
                  </div>
                </div>
              </el-form-item>
              <el-form-item label="时间区间">
                <el-date-picker
                  v-model="range"
                  type="daterange"
                  value-format="YYYY-MM-DD"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  style="width:100%"
                />
              </el-form-item>
              <el-form-item label="初始资金">
                <el-input-number v-model="form.initial_capital" :min="10000" :step="50000" style="width:100%" />
              </el-form-item>
              <el-button type="primary" :loading="running" style="width:100%" @click="run">
                {{ running ? '回测中…' : '开始回测' }}
              </el-button>
            </el-form>
          </div>
        </el-col>

        <el-col :xs="24" :sm="16" :md="18">
          <div v-if="result" class="card">
            <div class="flex between" style="align-items:center;margin-bottom:10px">
              <span class="fs14 bold">{{ result.symbol }} · {{ result.strategy_name }}</span>
              <span class="fs12" style="color:#909399">{{ result.start_date }} ~ {{ result.end_date }} · {{ result.metrics.bars }} 个交易日</span>
            </div>
            <el-row :gutter="8" class="mb8">
              <el-col v-for="m in metricCards" :key="m.label" :xs="12" :sm="8" :md="4">
                <div class="metric-card">
                  <div class="fs12" style="color:#909399">{{ m.label }}</div>
                  <div class="fs18 bold" :class="m.cls">{{ m.value }}</div>
                </div>
              </el-col>
            </el-row>
            <div ref="chartEl" style="width:100%;height:320px" />
            <el-divider content-position="left">交易明细（{{ result.trades.length }} 笔）</el-divider>
            <el-table v-if="result.trades.length" :data="result.trades" size="small" max-height="320">
              <el-table-column prop="symbol" label="标的" width="110" />
              <el-table-column prop="entry_date" label="买入日期" width="110" />
              <el-table-column prop="entry_price" label="买入价" width="90" align="right" />
              <el-table-column prop="exit_date" label="卖出日期" width="110" />
              <el-table-column prop="exit_price" label="卖出价" width="90" align="right" />
              <el-table-column prop="shares" label="股数" width="90" align="right" />
              <el-table-column label="盈亏" width="150" align="right">
                <template #default="{ row }">
                  <span :class="row.pnl >= 0 ? 'up' : 'down'">{{ row.pnl >= 0 ? '+' : '' }}{{ fmtNum(row.pnl) }}</span>
                  <span class="fs11" :class="row.pnl >= 0 ? 'up' : 'down'"> ({{ (row.pnl_pct * 100).toFixed(2) }}%)</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="80">
                <template #default="{ row }">
                  <el-tag v-if="row.open_position" size="small" type="warning">持仓中</el-tag>
                  <el-tag v-else size="small" type="info">已平仓</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="区间内无完整交易信号" :image-size="60" />
          </div>
          <div v-else class="card">
            <el-empty description="配置左侧参数后点击「开始回测」" :image-size="90" />
          </div>
        </el-col>
      </el-row>

      <!-- 策略管理抽屉 -->
      <el-drawer v-model="managerOpen" title="策略管理" size="72%" append-to-body>
        <div class="strategy-layout">
          <div class="strategy-list">
            <div class="flex between mb8">
              <span class="fs14 bold">策略列表</span>
              <el-button size="small" type="primary" @click="newStrategy">新建策略</el-button>
            </div>
            <div
              v-for="s in strategies"
              :key="s.id"
              class="strategy-item"
              :class="{ active: s.id === selectedId, muted: !s.is_active }"
              @click="selectStrategy(s)"
            >
              <div class="flex between">
                <span class="fs13 bold">{{ s.name }}</span>
                <span>
                  <el-tag v-if="s.is_builtin" size="small" type="info">内置</el-tag>
                  <el-tag v-if="!s.is_active" size="small" type="danger" style="margin-left:4px">停用</el-tag>
                </span>
              </div>
              <div class="fs11" style="color:#909399;margin-top:2px">
                {{ s.key }}<template v-if="s.description"> · {{ s.description.slice(0, 30) }}</template>
              </div>
            </div>
          </div>

          <div class="strategy-edit">
            <template v-if="editing">
              <div class="flex between mb8" style="align-items:center">
                <el-input v-model="editing.name" placeholder="策略名称" style="width:280px" />
                <span>
                  <el-button size="small" @click="testCode">测试代码</el-button>
                  <el-button size="small" @click="duplicate(editing)">复制</el-button>
                  <el-button size="small" type="warning" :disabled="editing.is_builtin" @click="removeStrategy(editing)">删除</el-button>
                  <el-button size="small" type="primary" @click="saveStrategy">保存</el-button>
                </span>
              </div>
              <el-input v-model="editing.description" placeholder="策略说明（可选）" class="mb8" />

              <div style="color:#909399" class="fs13 mb8">
                参数定义（驱动左侧回测表单）：每项含 key / label / type（int、number、select、bool）/ default / min / max / step / options
              </div>
              <div v-for="(p, idx) in editing.params_schema" :key="idx" class="schema-row">
                <el-input v-model="p.key" placeholder="key" class="sc-w1" />
                <el-input v-model="p.label" placeholder="label" class="sc-w2" />
                <el-select v-model="p.type" class="sc-w3">
                  <el-option label="整数" value="int" />
                  <el-option label="数字" value="number" />
                  <el-option label="下拉" value="select" />
                  <el-option label="开关" value="bool" />
                </el-select>
                <el-input v-model="p.default" placeholder="default" class="sc-w2" />
                <el-button size="small" text type="danger" @click="removeSchema(idx)">移除</el-button>
              </div>
              <el-button size="small" @click="addSchema">+ 添加参数</el-button>

              <el-divider content-position="left">策略代码（run(bars, params)）</el-divider>
              <div style="color:#909399" class="fs12 mb8">
                环境提供 sma / ema 辅助函数。返回信号列表 [{"dt":"YYYY-MM-DD","action":"buy"|"sell","fraction":1}]；
                buy 在 dt 当日开盘建仓（fraction=资金占比），sell 当日开盘减仓（fraction=持仓占比），信号 dt 必须是 bars 中的交易日。
              </div>
              <textarea
                v-model="editing.code"
                class="code-editor"
                spellcheck="false"
                :disabled="running"
              />
              <div v-if="testResult" class="fs12 mt8" style="white-space:pre-wrap">
                <span :class="testResult.ok ? 'up' : 'down'">{{ testResult.ok ? '✓ 通过' : '✗ 失败' }}</span>
                {{ testResult.ok
                  ? `：产生 ${testResult.signals} 个信号，合成K线预回测收益 ${(testResult.preview.total_return * 100).toFixed(2)}%（${testResult.preview.trade_count} 笔）`
                  : `：${testResult.error}` }}
              </div>
            </template>
            <el-empty v-else description="从左侧选择一个策略进行编辑" :image-size="80" />
          </div>
        </div>
      </el-drawer>

      <!-- 从自选股导入组合 -->
      <el-dialog v-model="importOpen" title="从自选股导入" width="500px" append-to-body>
        <template v-if="importGroups.length">
          <div style="color:#909399" class="fs12 mb8">选择自选分组，将其中的股票加入回测组合：</div>
          <el-radio-group v-model="importGroupId" style="display:flex;flex-direction:column;align-items:flex-start;gap:8px">
            <el-radio
              v-for="g in importGroups"
              :key="g.id"
              :label="g.id"
            >{{ g.name }}（{{ (g.items || []).length }} 只）</el-radio>
          </el-radio-group>
          <div class="mt8">
            <el-button size="small" type="primary" :disabled="!importGroupId" @click="importGroup">
              加入组合
            </el-button>
          </div>
        </template>
        <el-empty v-else description="暂未创建自选分组" :image-size="60" />
      </el-dialog>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import MainLayout from '../layout/MainLayout.vue'
import { backtestApi, stockApi, watchlistApi, marketApi } from '../api'

const mode = ref('single')
const form = reactive({
  symbol: '',
  symbols: [],
  strategy: '',
  initial_capital: 100000
})
const range = ref([new Date(Date.now() - 730 * 864e5).toISOString().slice(0, 10), new Date().toISOString().slice(0, 10)])
const strategies = ref([])
const paramsInputs = reactive({})
const result = ref(null)
const running = ref(false)
const searchResults = ref([])
const searchLoading = ref(false)

const managerOpen = ref(false)
const selectedId = ref(null)
const editing = ref(null)
const testResult = ref(null)

const importOpen = ref(false)
const importGroups = ref([])
const importGroupId = ref(null)

const visibleStrategies = computed(() => strategies.value.filter(s => s.is_active !== false))
const activeStrategy = computed(() => strategies.value.find(s => s.key === form.strategy))
const activeSchema = computed(() => activeStrategy.value?.params_schema || [])

const metricCards = computed(() => {
  if (!result.value) return []
  const m = result.value.metrics
  const pctCls = v => (v >= 0 ? 'up' : 'down')
  return [
    { label: '累计收益', value: ((m.total_return * 100).toFixed(2)) + '%', cls: pctCls(m.total_return) },
    { label: '年化收益', value: ((m.annualized_return * 100).toFixed(2)) + '%', cls: pctCls(m.annualized_return) },
    { label: '最大回撤', value: ((m.max_drawdown * 100).toFixed(2)) + '%', cls: 'down' },
    { label: '胜率', value: ((m.win_rate * 100).toFixed(1)) + '%', cls: 'flat' },
    { label: '交易次数', value: String(m.trade_count), cls: 'flat' },
    { label: '期末资金', value: fmtNum(m.final_equity), cls: 'flat' }
  ]
})

const chartEl = ref(null)
let chart = null
const benchmarkData = ref([])

function fmtNum(v) {
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function doSearch(kw) {
  if (!kw || !kw.trim()) { searchResults.value = []; return }
  searchLoading.value = true
  stockApi.search(kw.trim())
    .then(r => { searchResults.value = Array.isArray(r) ? r : [] })
    .catch(() => { searchResults.value = [] })
    .finally(() => { searchLoading.value = false })
}

function fillParamsInputs(schema) {
  for (const k of Object.keys(paramsInputs)) delete paramsInputs[k]
  for (const p of schema || []) {
    paramsInputs[p.key] = p.default != null ? p.default : ''
  }
}

function onStrategyChange() {
  fillParamsInputs(activeStrategy.value?.params_schema || [])
}

function renderChart(curve) {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const dates = curve.map(c => c.dt)
  const equities = curve.map(c => c.equity)
  // 归一化基准为1
  const benchDates = benchmarkData.value.map(b => b.dt)
  const benchVals = benchmarkData.value.map(b => b.close)
  let benchNorm = []
  if (benchVals.length > 0) {
    const base = benchVals[0]
    benchNorm = benchVals.map(v => equities[0] * v / base)
  }
  // 找最大回撤位置
  let peak = 0, maxDd = 0, ddStart = 0, ddEnd = 0
  let pIdx = 0
  for (let i = 0; i < equities.length; i++) {
    if (equities[i] > peak) { peak = equities[i]; pIdx = i }
    const dd = (peak - equities[i]) / peak
    if (dd > maxDd) { maxDd = dd; ddStart = pIdx; ddEnd = i }
  }
  // 修复周期：从ddEnd开始找回到peak值的位置
  let recoveryIdx = equities.length - 1
  for (let i = ddEnd; i < equities.length; i++) {
    if (equities[i] >= peak) { recoveryIdx = i; break }
  }
  const markPoints = []
  if (maxDd > 0) {
    markPoints.push(
      { name: '最大回撤', coord: [dates[ddStart], equities[ddStart]], symbol: 'triangle', symbolSize: 14, itemStyle: { color: '#f56c6c' },
        label: { show: true, formatter: `回撤 ${(maxDd*100).toFixed(1)}%`, position: 'top', color: '#f56c6c', fontSize: 11 } },
      { name: '回撤底', coord: [dates[ddEnd], equities[ddEnd]], symbol: 'pin', symbolSize: 30, itemStyle: { color: '#e6a23c' },
        label: { show: true, formatter: '底', position: 'bottom', color: '#e6a23c', fontSize: 10 } }
    )
    if (recoveryIdx < equities.length - 1 || equities[equities.length-1] >= peak) {
      markPoints.push(
        { name: '修复', coord: [dates[recoveryIdx], equities[recoveryIdx]], symbol: 'circle', symbolSize: 10, itemStyle: { color: '#67c23a' },
          label: { show: true, formatter: `修复 ${recoveryIdx - ddEnd}日`, position: 'right', color: '#67c23a', fontSize: 10 } }
      )
    }
  }
  const series = [{
    name: '策略净值',
    type: 'line',
    data: equities,
    smooth: false,
    showSymbol: false,
    lineStyle: { width: 2, color: '#409eff' },
    areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: 'rgba(64,158,255,.28)' },
      { offset: 1, color: 'rgba(64,158,255,.02)' }
    ]) },
    markPoint: { data: markPoints, animation: false }
  }]
  if (benchNorm.length) {
    series.push({
      name: '沪深300',
      type: 'line',
      data: benchNorm,
      smooth: false,
      showSymbol: false,
      lineStyle: { width: 1.5, color: '#909399', type: 'dashed' },
    })
  }
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { color: '#909399', fontSize: 11 } },
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: dates, boundaryGap: false },
    yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#eee' } } },
    series
  })
}

async function loadStrategies() {
  try {
    strategies.value = await backtestApi.strategies()
  } catch { strategies.value = [] }
  if (!strategies.value.length) return
  if (!form.strategy || !strategies.value.find(s => s.key === form.strategy)) {
    const first = strategies.value.find(s => s.is_active !== false) || strategies.value[0]
    form.strategy = first.key
    fillParamsInputs(first.params_schema)
  }
}

async function run() {
  if (mode.value === 'portfolio') {
    if (!form.symbols || !form.symbols.length) { ElMessage.warning('请先选择至少一只组合股票'); return }
  } else if (!form.symbol) {
    ElMessage.warning('请先选择股票')
    return
  }
  if (!range.value || !range.value.length) { ElMessage.warning('请选择时间区间'); return }
  if (!form.strategy) { ElMessage.warning('请选择策略'); return }
  running.value = true
  try {
    result.value = await backtestApi.run({
      symbol: mode.value === 'single' ? form.symbol : '',
      symbols: mode.value === 'portfolio' ? form.symbols : [],
      strategy: form.strategy,
      strategy_id: activeStrategy.value?.id,
      params: { ...paramsInputs },
      start_date: range.value[0],
      end_date: range.value[1],
      initial_capital: form.initial_capital
    })
    // 获取沪深300基准
    benchmarkData.value = []
    try {
      const benchKline = await marketApi.kline({ symbol: 'SH000300', period: 'day', start: range.value[0], end: range.value[1] })
      benchmarkData.value = (benchKline?.data || []).map(k => ({ dt: k.dt, close: k.close }))
    } catch { benchmarkData.value = [] }
    requestAnimationFrame(() => renderChart(result.value.equity_curve || []))
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '回测失败')
  } finally {
    running.value = false
  }
}

// ---------------- 自选组合导入 ----------------
async function openWatchlistImport() {
  importGroupId.value = null
  try {
    importGroups.value = (await watchlistApi.groups()) || []
  } catch {
    importGroups.value = []
  }
  importOpen.value = true
}

function importGroup() {
  const g = importGroups.value.find(x => x.id === importGroupId.value)
  const fromGroup = (g?.items || []).map(it => it.symbol).filter(Boolean)
  if (!fromGroup.length) { ElMessage.warning('该分组暂无自选股票'); return }
  for (const sym of fromGroup) {
    if (form.symbols.length >= 20) break
    if (!form.symbols.includes(sym)) form.symbols.push(sym)
  }
  ElMessage.success(`已加入 ${form.symbols.length} 只股票`)
  importOpen.value = false
}

// ---------------- 策略管理 ----------------
function openManager() {
  managerOpen.value = true
  if (!selectedId.value && strategies.value.length) selectStrategy(strategies.value[0])
}
function selectStrategy(s) {
  selectedId.value = s.id
  editing.value = JSON.parse(JSON.stringify(s))
  testResult.value = null
}
function newStrategy() {
  const tempId = 'temp_' + Date.now()
  const tempStrategy = {
    id: tempId, key: '', name: '新策略（未保存）', description: '',
    params_schema: [
      { key: 'fast', label: '快线周期', type: 'int', default: 5, min: 2, max: 120, step: 1 },
      { key: 'slow', label: '慢线周期', type: 'int', default: 20, min: 5, max: 250, step: 1 }
    ],
    code: '',
    is_builtin: false, is_active: true, _temp: true
  }
  strategies.value.unshift(tempStrategy)
  selectedId.value = tempId
  editing.value = JSON.parse(JSON.stringify(tempStrategy))
  testResult.value = null
}
function addSchema() { editing.value.params_schema.push({ key: '', label: '', type: 'int', default: null }) }
function removeSchema(idx) { editing.value.params_schema.splice(idx, 1) }

async function saveStrategy() {
  if (!editing.value.name || editing.value.name === '新策略（未保存）') { ElMessage.warning('请填写策略名称'); return }
  const payload = {
    name: editing.value.name,
    description: editing.value.description,
    params_schema: editing.value.params_schema,
    code: editing.value.code
  }
  try {
    const isTemp = editing.value._temp || String(editing.value.id).startsWith('temp_')
    const saved = isTemp
      ? await backtestApi.createStrategy(payload)
      : await backtestApi.updateStrategy(editing.value.id, payload)
    ElMessage.success('已保存')
    await loadStrategies()
    selectedId.value = saved.id
    editing.value = saved
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  }
}

async function duplicate(s) {
  try {
    const n = await backtestApi.duplicateStrategy(s.id)
    ElMessage.success('已复制')
    await loadStrategies()
    selectStrategy(n)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '复制失败')
  }
}

async function removeStrategy(s) {
  try {
    await ElMessageBox.confirm(
      s.is_builtin ? '这是内置策略，删除后将停用（不可彻底删除）。确认？' : `确认删除策略「${s.name}」？`,
      '提示', { type: 'warning' }
    )
    await backtestApi.deleteStrategy(s.id)
    ElMessage.success(s.is_builtin ? '已停用' : '已删除')
    await loadStrategies()
    editing.value = null
    selectedId.value = null
  } catch (e) { /* 取消 */ }
}

async function testCode() {
  if (!editing.value.code) { ElMessage.warning('请先填写策略代码'); return }
  testResult.value = null
  try {
    testResult.value = await backtestApi.testStrategy({ code: editing.value.code, params: { ...paramsInputs } })
  } catch (e) {
    testResult.value = { ok: false, error: e?.message || '测试失败' }
  }
}

function onResize() { if (chart) chart.resize() }

onMounted(() => {
  loadStrategies()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (chart) { chart.dispose(); chart = null }
})
</script>

<style scoped>
.metric-card {
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafbfc;
  margin-bottom: 4px;
}
.strategy-layout { display: flex; gap: 12px; align-items: flex-start; }
.strategy-list { width: 260px; flex-shrink: 0; }
.strategy-item {
  padding: 8px 10px; border: 1px solid #ebeef5; border-radius: 8px;
  margin-bottom: 6px; cursor: pointer;
}
.strategy-item.active { border-color: #409eff; background: #ecf5ff; }
.strategy-item.muted { opacity: 0.5; }
.strategy-edit { flex: 1; min-width: 0; }
.schema-row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
.sc-w1 { width: 110px; }
.sc-w2 { width: 150px; }
.sc-w3 { width: 100px; }
.code-editor {
  width: 100%; height: 360px;
  font-family: 'Cascadia Code', Consolas, 'Courier New', monospace;
  font-size: 12px; line-height: 1.6;
  border: 1px solid #dcdfe6; border-radius: 6px; padding: 8px;
  background: #0d1117; color: #e6edf3; resize: vertical;
}
.code-editor:focus { outline: none; border-color: #409eff; }
</style>