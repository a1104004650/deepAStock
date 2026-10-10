<template>
  <MainLayout>
    <div class="page wave-page">
      <header class="study-head">
        <div>
          <div class="eyebrow">MULTI-SCALE WAVE EVIDENCE</div>
          <h1>指数波浪</h1>
          <p>由行情噪声自动确定 ZigZag 尺度，枚举并验证连续波浪窗口，不对最近拐点机械贴标签。</p>
        </div>
        <div class="head-status">
          <span class="method-badge">ATR14 自适应</span>
          <span class="method-badge muted">多尺度交叉验证</span>
        </div>
      </header>

      <section class="control-sheet" aria-label="研究参数">
        <div class="control-block primary-controls">
          <label>研究指数</label>
          <el-select v-model="symbol" size="small" aria-label="研究指数">
            <el-option v-for="item in indices" :key="item.value" :label="`${item.name} ${item.value}`" :value="item.value" />
          </el-select>
        </div>
        <div class="control-block period-control">
          <label>周期</label>
          <el-radio-group v-model="period" size="small" aria-label="K线周期">
            <el-radio-button value="day">日</el-radio-button>
            <el-radio-button value="week">周</el-radio-button>
            <el-radio-button value="month">月</el-radio-button>
          </el-radio-group>
        </div>
        <div class="control-block">
          <label for="lookback">回看数量</label>
          <el-input-number id="lookback" v-model="lookback" :min="40" :max="500" :step="20" size="small" controls-position="right" />
        </div>
        <div class="control-block scale-control">
          <label>分析尺度 <b>{{ scaleMode === 'auto' ? '自动' : scaleNames[scaleMode] }}</b></label>
          <el-select v-model="scaleMode" size="small" aria-label="分析尺度">
            <el-option label="自动选择" value="auto" />
            <el-option label="短期" value="short" />
            <el-option label="中期" value="medium" />
            <el-option label="主要" value="major" />
          </el-select>
        </div>
        <el-button size="small" :loading="loading" @click="loadKlines">刷新行情</el-button>
      </section>

      <div v-if="error" class="state-panel error-state" role="alert">
        <strong>行情加载失败</strong><span>{{ error }}</span><el-button size="small" @click="loadKlines">重试</el-button>
      </div>

      <section v-loading="loading" class="chart-sheet">
        <div class="panel-head">
          <div>
            <h2>{{ currentIndex.name }} <span class="mono">{{ symbol }}</span></h2>
            <p>{{ periodName }}线 · {{ bars.length }}根 · {{ chartScaleText }}</p>
          </div>
          <div class="chart-legend" aria-label="图例">
            <span><i class="legend-ma"></i>MA20</span>
            <span><i class="legend-zigzag"></i>确认折线</span>
            <span><i class="legend-candidate"></i>活动C</span>
            <span><i class="legend-zone"></i>目标区</span>
          </div>
        </div>
        <div v-if="bars.length" ref="chartEl" class="wave-chart" role="img" :aria-label="`${currentIndex.name}${periodName}线波浪结构证据图`"></div>
        <el-empty v-else-if="!loading && !error" description="当前指数和周期暂无可用K线" :image-size="64" />
      </section>

      <section v-if="bars.length" class="analysis-grid">
        <article class="card conclusion-card">
          <div class="panel-head compact">
            <div><h2>结构结论</h2><p>连续窗口规则、比例、显著度、近期性与尺度一致性的综合结果</p></div>
            <span class="structure-tag" :class="{ empty: !selectedCandidate }">{{ conclusionName }}</span>
          </div>
          <template v-if="selectedCandidate">
            <div class="conclusion-main">
              <div><small>结构评分 / 证据一致度</small><strong>{{ selectedCandidate.score }} / 100</strong></div>
              <div><small>自动尺度 / 反转阈值</small><strong>{{ scaleNames[selectedCandidate.scale] }} · {{ pctThreshold(selectedCandidate.threshold) }}</strong></div>
              <div><small>当前阶段</small><strong>{{ selectedCandidate.complete ? 'C 已确认' : 'C 发展中' }}</strong></div>
            </div>
            <p class="candidate-note">{{ selectedCandidate.summary }}。评分表达当前证据的一致程度，不代表上涨、下跌或目标到达的概率。</p>
          </template>
          <div v-else class="no-structure">
            <strong>未发现通过硬规则且评分达到 55 的连续窗口</strong>
            <span>{{ noStructureReason }}。可尝试切换日/周周期或增加回看数量；系统不会为不足的样本伪造标签和点位。</span>
          </div>
        </article>

        <article class="card candidate-card">
          <div class="panel-head compact"><div><h2>候选比较</h2><p>自动优先最近仍有效的结构，再比较证据评分</p></div></div>
          <button v-if="selectedCandidate" class="candidate-choice active" type="button">
            <span>当前 · {{ selectedCandidate.complete ? '完整ABC' : '发展中C' }}</span><b>{{ scaleNames[selectedCandidate.scale] }} {{ selectedCandidate.score }}</b>
          </button>
          <button v-for="item in alternatives" :key="item.key" class="candidate-choice" type="button" @click="selectCandidate(item)">
            <span>备选 · {{ item.direction === 'up' ? '上升推动后' : '下降推动后' }}{{ item.complete ? '完整ABC' : '发展中C' }}</span><b>{{ scaleNames[item.scale] }} {{ item.score }}</b>
          </button>
          <p v-if="!alternatives.length" class="candidate-note">{{ selectedCandidate ? '当前没有其他达到门槛的可靠备选。' : '当前没有可供比较的可靠候选。' }}</p>
        </article>
      </section>

      <section v-if="bars.length" class="target-section card">
        <div class="panel-head compact">
          <div><h2>C 目标区</h2><p>A浪扩展、0-5回撤与历史支撑压力按波动带宽聚类</p></div>
          <span v-if="selectedCandidate && !selectedCandidate.complete" class="count-note">带宽 {{ priceText(targetAnalysis.bandwidth) }}</span>
        </div>
        <div v-if="targetZones.length" class="target-grid">
          <article v-for="(zone, index) in targetZones" :key="`${zone.low}-${zone.high}`" class="target-zone">
            <div><span>区域 {{ index + 1 }}</span><b>{{ priceText(zone.low) }} – {{ priceText(zone.high) }}</b></div>
            <strong>证据一致度 {{ zone.score }} / 100 · {{ zone.statusText }}</strong>
            <p>{{ zone.sourceText }}</p>
          </article>
        </div>
        <div v-else class="target-empty">{{ selectedCandidate?.complete ? 'C 已确认，目标区不再作为进行中推演展示。' : '无可靠发展中 C 结构，因此不生成目标区。' }}</div>
        <p class="zone-disclaimer">目标区是多类价格锚点的聚集带，不是预测必达点位；支撑压力可能失效，黄金分割仅用于比较结构比例。</p>
      </section>

      <section v-if="bars.length" class="detail-grid">
        <article class="card rule-card">
          <div class="panel-head compact"><div><h2>可检验规则</h2><p>硬规则失败的窗口不会入选</p></div></div>
          <div class="rule-list">
            <div v-for="rule in displayedRules" :key="rule.label">
              <span class="rule-state" :class="`is-${rule.state}`">{{ stateText(rule.state) }}</span>
              <p><strong>{{ rule.label }}</strong><small>{{ rule.detail }}</small></p>
            </div>
          </div>
        </article>

        <article class="card pivot-card">
          <div class="panel-head compact">
            <div><h2>当前窗口拐点作业表</h2><p>只展示入选连续窗口；确认日可能晚于极值日</p></div>
            <span class="count-note">{{ pivotRows.length ? `${pivotRows.length} 点` : '无标签' }}</span>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>标签</th><th>峰谷</th><th>极值日</th><th>确认日</th><th>价格</th><th>前浪变化</th><th>状态</th></tr></thead>
              <tbody>
                <tr v-for="row in pivotRows" :key="`${row.label}-${row.index}`">
                  <td><b class="wave-label" :class="{ candidate: row.status === '发展中' }">{{ row.label }}</b></td>
                  <td>{{ row.type === 'peak' ? '峰' : '谷' }}</td>
                  <td class="mono">{{ row.date }}</td>
                  <td class="mono">{{ row.confirmedAtDate || '待确认' }}</td>
                  <td class="mono">{{ priceText(row.price) }}</td>
                  <td class="mono" :class="row.change >= 0 ? 'up' : 'down'">{{ pctText(row.change) }}</td>
                  <td><span class="status-text" :class="{ candidate: row.status === '发展中' }">{{ row.status }}</span></td>
                </tr>
                <tr v-if="!pivotRows.length"><td colspan="7" class="empty-cell">没有可靠结构，不生成波浪标签</td></tr>
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <footer class="method-note">
        <strong>方法论提醒</strong>
        <span>ZigZag 以 ATR14/收盘价的中位噪声自动构造短期、中期和主要尺度。黄金分割衡量腿之间的比例，历史支撑压力来自 B 点之前的多尺度确认拐点；二者都是结构证据，不是投资建议，也不保证目标区必达。</span>
      </footer>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import MainLayout from '../layout/MainLayout.vue'
import { marketApi } from '../api'

const indices = [
  { value: 'SH000001', name: '上证指数' },
  { value: 'SH000300', name: '沪深300' },
  { value: 'SH000905', name: '中证500' },
  { value: 'SZ399001', name: '深证成指' },
  { value: 'SZ399006', name: '创业板指' },
  { value: 'SH000688', name: '科创50' },
]
const labels = ['0', '1', '2', '3', '4', '5', 'A', 'B', 'C']
const scaleNames = { short: '短期', medium: '中期', major: '主要' }
const scaleSpecs = [
  { key: 'short', factor: 2, minGap: 3 },
  { key: 'medium', factor: 3.2, minGap: 5 },
  { key: 'major', factor: 5, minGap: 8 },
]
const symbol = ref('SH000001')
const period = ref('day')
const lookback = ref(280)
const scaleMode = ref('auto')
const rawBars = ref([])
const loading = ref(false)
const error = ref('')
const chartEl = ref(null)
const selectedCandidateKey = ref('')
let chart = null
let requestId = 0

const currentIndex = computed(() => indices.find((item) => item.value === symbol.value) || indices[0])
const periodName = computed(() => ({ day: '日', week: '周', month: '月' }[period.value]))
const bars = computed(() => rawBars.value.slice(-lookback.value))
const atrValues = computed(() => calculateAtr(bars.value, 14))
const noise = computed(() => median(atrValues.value.map((atr, index) => atr && bars.value[index].close > 0 ? atr / bars.value[index].close : null).filter(Number.isFinite)) || fallbackNoise(bars.value))
const scaleResults = computed(() => scaleSpecs.map((spec) => {
  const threshold = clamp(noise.value * spec.factor, 0.01, 0.2)
  return { ...spec, threshold, ...calculateZigzag(bars.value, threshold, spec.minGap) }
}))
const allCandidates = computed(() => buildCandidates(scaleResults.value, bars.value))
const eligibleCandidates = computed(() => allCandidates.value
  .filter((item) => item.score >= 55 && (scaleMode.value === 'auto' || item.scale === scaleMode.value))
  .sort((a, b) => b.endIndex - a.endIndex || b.score - a.score || Number(b.complete) - Number(a.complete)))
const selectedCandidate = computed(() => eligibleCandidates.value.find((item) => item.key === selectedCandidateKey.value) || eligibleCandidates.value[0] || null)
const selectedScale = computed(() => scaleResults.value.find((item) => item.key === selectedCandidate.value?.scale)
  || scaleResults.value.find((item) => item.key === (scaleMode.value === 'auto' ? 'medium' : scaleMode.value))
  || scaleResults.value[0])
const alternatives = computed(() => eligibleCandidates.value.filter((item) => item.key !== selectedCandidate.value?.key).slice(0, 2))
const conclusionName = computed(() => !selectedCandidate.value ? '无可靠结构' : selectedCandidate.value.direction === 'up' ? '上升推动后的ABC调整候选' : '下降推动后的ABC调整候选')
const chartScaleText = computed(() => `${scaleMode.value === 'auto' ? '自动尺度' : scaleNames[scaleMode.value]} · ${scaleNames[selectedScale.value?.key] || '--'}阈值 ${pctThreshold(selectedScale.value?.threshold)}`)
const noStructureReason = computed(() => {
  if (bars.value.length < 16) return `当前仅 ${bars.value.length} 根K线，连形成 8 个确认拐点的基础样本都不足`
  const available = scaleResults.value.reduce((max, item) => Math.max(max, item.confirmed.length), 0)
  if (available < 8) return `各尺度最多只有 ${available} 个确认拐点，完整结构需要 9 个，发展中结构也需要 8 个确认点`
  return '已枚举的连续窗口存在硬规则失效、C方向尚未形成或证据一致度不足'
})
const displayedRules = computed(() => selectedCandidate.value?.rules || [
  ruleResult('峰谷交替与时间顺序', null, '需要可靠的连续结构窗口'),
  ruleResult('浪2不越浪0', null, '需要0、1、2确认点'),
  ruleResult('浪3非最短且越过浪1', null, '需要完整推动五浪'),
  ruleResult('浪4不进入浪1价格区', null, '需要1与4确认点'),
  ruleResult('ABC方向交替', null, '需要A、B及确认或发展中的C'),
])
const pivotRows = computed(() => {
  if (!selectedCandidate.value) return []
  return selectedCandidate.value.points.map((point, index, rows) => ({
    ...point,
    label: labels[index],
    change: index ? (point.price / rows[index - 1].price - 1) * 100 : null,
    status: point.confirmed ? '已确认' : '发展中',
  }))
})
const targetAnalysis = computed(() => buildTargetZones(selectedCandidate.value, scaleResults.value, bars.value, atrValues.value))
const targetZones = computed(() => targetAnalysis.value.zones)

function normalizeBars(payload) {
  const rows = payload?.data || payload || []
  if (!Array.isArray(rows)) return []
  return rows.map((row) => ({
    date: String(row.dt || row.date || '').slice(0, 10),
    open: Number(row.open), close: Number(row.close), low: Number(row.low), high: Number(row.high),
  })).filter((row) => row.date && [row.open, row.close, row.low, row.high].every(Number.isFinite))
    .sort((a, b) => a.date.localeCompare(b.date))
}

async function loadKlines() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response = await marketApi.kline({ symbol: symbol.value, period: period.value })
    if (id !== requestId) return
    rawBars.value = normalizeBars(response)
  } catch (e) {
    if (id !== requestId) return
    rawBars.value = []
    error.value = e?.response?.data?.detail || e?.message || '无法取得指数K线，请稍后重试。'
  } finally {
    if (id === requestId) loading.value = false
  }
}

function calculateAtr(rows, periodLength) {
  const ranges = rows.map((row, index) => {
    const previousClose = rows[index - 1]?.close ?? row.close
    return Math.max(row.high - row.low, Math.abs(row.high - previousClose), Math.abs(row.low - previousClose))
  })
  return ranges.map((_, index) => {
    if (index < periodLength - 1) return null
    return ranges.slice(index - periodLength + 1, index + 1).reduce((sum, value) => sum + value, 0) / periodLength
  })
}

function fallbackNoise(rows) {
  const changes = rows.slice(1).map((row, index) => Math.abs(row.close / rows[index].close - 1)).filter(Number.isFinite)
  return clamp(median(changes) * 1.5 || 0.02, 0.005, 0.1)
}

function makePoint(bar, index, type, confirmedAtIndex = null, confirmedAtDate = null) {
  return {
    index,
    date: bar.date,
    price: type === 'peak' ? bar.high : bar.low,
    type,
    confirmed: confirmedAtIndex != null,
    confirmedAtIndex,
    confirmedAtDate,
  }
}

function calculateZigzag(rows, reversal, minGap) {
  if (rows.length < 2) return { confirmed: [], active: null }
  let high = makePoint(rows[0], 0, 'peak')
  let low = makePoint(rows[0], 0, 'trough')
  let direction = null
  let extreme = null
  const raw = []

  for (let i = 1; i < rows.length; i += 1) {
    const row = rows[i]
    if (!direction) {
      if (row.high >= high.price) high = makePoint(row, i, 'peak')
      if (row.low <= low.price) low = makePoint(row, i, 'trough')
      const rise = high.index > low.index && high.price / low.price - 1 >= reversal
      const fall = low.index > high.index && 1 - low.price / high.price >= reversal
      if (rise) {
        raw.push({ ...low, confirmed: true, confirmedAtIndex: i, confirmedAtDate: row.date })
        direction = 'up'; extreme = high
      } else if (fall) {
        raw.push({ ...high, confirmed: true, confirmedAtIndex: i, confirmedAtDate: row.date })
        direction = 'down'; extreme = low
      }
      continue
    }

    if (direction === 'up') {
      if (row.high >= extreme.price) extreme = makePoint(row, i, 'peak')
      if (i > extreme.index && row.low <= extreme.price * (1 - reversal)) {
        raw.push({ ...extreme, confirmed: true, confirmedAtIndex: i, confirmedAtDate: row.date })
        direction = 'down'; extreme = makePoint(row, i, 'trough')
      }
    } else {
      if (row.low <= extreme.price) extreme = makePoint(row, i, 'trough')
      if (i > extreme.index && row.high >= extreme.price * (1 + reversal)) {
        raw.push({ ...extreme, confirmed: true, confirmedAtIndex: i, confirmedAtDate: row.date })
        direction = 'up'; extreme = makePoint(row, i, 'peak')
      }
    }
  }

  const confirmed = enforceMinimumGap(raw, minGap)
  let active = extreme && confirmed.length ? extreme : null
  const last = confirmed.at(-1)
  if (active && last) {
    if (active.index <= last.index) active = null
    else if (active.type === last.type) {
      const moreExtreme = active.type === 'peak' ? active.price > last.price : active.price < last.price
      if (!moreExtreme) active = null
    }
  }
  return { confirmed, active }
}

function enforceMinimumGap(points, minGap) {
  const filtered = []
  for (const point of points) {
    const last = filtered.at(-1)
    if (!last) { filtered.push(point); continue }
    if (point.type === last.type) {
      const replace = point.type === 'peak' ? point.price >= last.price : point.price <= last.price
      if (replace) filtered[filtered.length - 1] = point
      continue
    }
    if (point.index - last.index >= minGap) {
      filtered.push(point)
      continue
    }
    const previous = filtered.at(-2)
    if (!previous) continue
    const nextSameAsLast = point.type === previous.type
    if (nextSameAsLast) {
      const replacePrevious = point.type === 'peak' ? point.price >= previous.price : point.price <= previous.price
      if (replacePrevious) filtered[filtered.length - 2] = point
      filtered.pop()
    }
  }
  return filtered
}

function buildCandidates(results, rows) {
  const candidates = []
  for (const result of results) {
    for (let start = 0; start <= result.confirmed.length - 9; start += 1) {
      const points = result.confirmed.slice(start, start + 9)
      for (const direction of ['up', 'down']) {
        const candidate = scoreWindow(points, direction, true, result, rows)
        if (candidate) candidates.push(candidate)
      }
    }
    if (result.active && result.confirmed.length >= 8) {
      const confirmed = result.confirmed.slice(-8)
      if (confirmed.at(-1).index < result.active.index) {
        const points = [...confirmed, { ...result.active, confirmed: false }]
        for (const direction of ['up', 'down']) {
          const candidate = scoreWindow(points, direction, false, result, rows)
          if (candidate) candidates.push(candidate)
        }
      }
    }
  }

  for (const candidate of candidates) {
    const peers = candidates.filter((other) => other !== candidate
      && other.direction === candidate.direction
      && Math.abs(other.points[0].index - candidate.points[0].index) <= 12
      && Math.abs(other.endIndex - candidate.endIndex) <= 12)
    const stability = Math.min(10, peers.filter((peer) => peer.scale !== candidate.scale).length * 5)
    candidate.score = Math.round(clamp(candidate.baseScore + stability, 0, candidate.complete ? 100 : 90))
    candidate.stability = stability
    candidate.key = `${candidate.scale}-${candidate.complete ? 'full' : 'live'}-${candidate.points[0].index}-${candidate.endIndex}-${candidate.direction}`
  }
  return candidates.filter((item) => !item.hardFail)
}

function scoreWindow(points, direction, complete, scale, rows) {
  if (points.length !== 9) return null
  const [p0, p1, p2, p3, p4, p5, a, b, c] = points
  const sign = direction === 'up' ? 1 : -1
  const chronological = points.every((point, index) => !index || point.index > points[index - 1].index)
  const alternating = points.every((point, index) => !index || point.type !== points[index - 1].type)
  const expectedTypes = direction === 'up'
    ? ['trough', 'peak', 'trough', 'peak', 'trough', 'peak', 'trough', 'peak', 'trough']
    : ['peak', 'trough', 'peak', 'trough', 'peak', 'trough', 'peak', 'trough', 'peak']
  const typeOrder = points.every((point, index) => point.type === expectedTypes[index])
  const moves = points.slice(1).map((point, index) => (point.price - points[index].price) * sign)
  const impulseDirections = moves.slice(0, 5).every((move, index) => index % 2 === 0 ? move > 0 : move < 0)
  const abcDirections = moves.slice(5).every((move, index) => index % 2 === 0 ? move < 0 : move > 0)
  const rule2 = sign * (p2.price - p0.price) > 0
  const l1 = Math.abs(p1.price - p0.price)
  const l3 = Math.abs(p3.price - p2.price)
  const l5 = Math.abs(p5.price - p4.price)
  const rule3 = sign * (p3.price - p1.price) > 0 && l3 >= Math.min(l1, l5)
  const rule4 = sign * (p4.price - p1.price) > 0
  const activeDeveloping = complete || (c.index > b.index && sign * (c.price - b.price) < 0 && c.type === expectedTypes[8])
  const hardFail = !(chronological && alternating && typeOrder && impulseDirections && abcDirections && rule2 && rule3 && rule4 && activeDeveloping)
  const aLength = Math.abs(a.price - p5.price)
  const ratios = [
    { value: Math.abs(p2.price - p1.price) / l1, low: 0.382, high: 0.786 },
    { value: l3 / l1, low: 1, high: 2.618 },
    { value: Math.abs(p4.price - p3.price) / l3, low: 0.236, high: 0.5 },
    { value: l5 / l1, low: 0.618, high: 1.618 },
    { value: Math.abs(b.price - a.price) / aLength, low: 0.382, high: 0.886 },
  ]
  if (complete) ratios.push({ value: Math.abs(c.price - b.price) / aLength, low: 0.618, high: 1.618 })
  const fibScore = average(ratios.map((item) => bandScore(item.value, item.low, item.high)))
  const legs = points.slice(1).map((point, index) => Math.abs(point.price / points[index].price - 1))
  const significance = clamp(average(legs) / scale.threshold / 1.6, 0, 1) * 12
  const recency = clamp(1 - (rows.length - 1 - c.index) / Math.max(20, rows.length * 0.35), 0, 1) * 10
  const ruleScore = hardFail ? 0 : 42
  const quality = clamp(scale.confirmed.length / 12, 0.35, 1) * 6 + (complete ? 4 : 2)
  const baseScore = ruleScore + fibScore * 0.26 + significance + recency + quality
  const rules = [
    ruleResult('峰谷交替与时间顺序', chronological && alternating && typeOrder, chronological && alternating ? '极值依次出现，峰谷类型与推动方向一致' : '窗口存在乱序、同类相邻或方向类型冲突'),
    ruleResult('浪2不越浪0', rule2, `浪0 ${priceText(p0.price)}，浪2 ${priceText(p2.price)}`),
    ruleResult('浪3非最短且越过浪1', rule3, `浪1/3/5长度 ${[l1, l3, l5].map(priceText).join(' / ')}`),
    ruleResult('浪4不进入浪1价格区', rule4, `浪1端点 ${priceText(p1.price)}，浪4 ${priceText(p4.price)}`),
    ruleResult('ABC方向交替', complete ? abcDirections : null, complete ? 'A、B、C方向依次反向、回升、再反向' : 'A、B已确认，C仍在预期方向发展'),
  ]
  return {
    scale: scale.key,
    threshold: scale.threshold,
    points,
    direction,
    complete,
    hardFail,
    baseScore,
    score: 0,
    rules,
    endIndex: c.index,
    summary: `${complete ? '完整C已由后续反转确认' : `活动极值自B点向${direction === 'up' ? '下' : '上'}延伸，尚未确认C`}，比例得分 ${Math.round(fibScore)}，腿显著度 ${Math.round(significance / 12 * 100)}`,
  }
}

function bandScore(value, low, high) {
  if (!Number.isFinite(value)) return 0
  if (value >= low && value <= high) {
    const center = (low + high) / 2
    return 90 + 10 * (1 - Math.abs(value - center) / ((high - low) / 2 || 1))
  }
  const distance = value < low ? low - value : value - high
  return clamp(85 * (1 - distance / Math.max(high - low, low * 0.7)), 0, 85)
}

function buildTargetZones(candidate, results, rows, atr) {
  if (!candidate || candidate.complete) return { bandwidth: null, zones: [] }
  const [p0, , , , , p5, a, b] = candidate.points
  const sign = candidate.direction === 'up' ? -1 : 1
  const aLength = Math.abs(a.price - p5.price)
  const totalLength = Math.abs(p5.price - p0.price)
  const bandwidth = Math.max(atr[b.index] || 0, b.price * 0.006, aLength * 0.1)
  const anchors = []
  for (const ratio of [0.618, 1, 1.272]) addDirectionalAnchor(anchors, b.price + sign * ratio * aLength, b.price, sign, 'extension', `A×${ratio}`)
  for (const ratio of [0.382, 0.5, 0.618]) addDirectionalAnchor(anchors, p5.price + sign * ratio * totalLength, b.price, sign, 'retracement', `0-5回撤${ratio}`)
  const history = results.flatMap((result) => result.confirmed.map((point) => ({ ...point, scale: result.key })))
    .filter((point) => point.index < b.index && (sign < 0 ? point.price < b.price : point.price > b.price))
  for (const point of history) anchors.push({ price: point.price, source: 'history', label: `${scaleNames[point.scale]}${sign < 0 ? '支撑' : '压力'}` })
  anchors.sort((left, right) => left.price - right.price)
  const clusters = []
  for (const anchor of anchors) {
    const cluster = clusters.find((item) => Math.abs(anchor.price - item.center) <= bandwidth && Math.max(item.high, anchor.price) - Math.min(item.low, anchor.price) <= bandwidth * 2)
    if (cluster) {
      cluster.anchors.push(anchor)
      cluster.low = Math.min(cluster.low, anchor.price)
      cluster.high = Math.max(cluster.high, anchor.price)
      cluster.center = average(cluster.anchors.map((item) => item.price))
    } else {
      clusters.push({ anchors: [anchor], low: anchor.price, high: anchor.price, center: anchor.price })
    }
  }
  const cPrice = candidate.points[8].price
  const travelDown = cPrice < b.price
  const statusRank = { current: 0, ahead: 1, passed: 2 }
  const statusNames = { current: '当前价格所在', ahead: '尚未到达', passed: '已穿过' }
  const zones = clusters.map((cluster) => {
    const sources = [...new Set(cluster.anchors.map((item) => item.source))]
    const hasHistory = sources.includes('history')
    let score = 27 + sources.length * 18 + Math.min(16, (cluster.anchors.length - 1) * 4)
    if (sources.length === 1) score = Math.min(score, 49)
    if (!hasHistory) score = Math.min(score, 64)
    score = Math.min(score, 79)
    const step = priceStep(cluster.center)
    const padding = Math.min(bandwidth * 0.25, Math.max(step, cluster.center * 0.004))
    const low = floorStep(cluster.low - padding, step)
    const high = ceilStep(cluster.high + padding, step)
    const current = cPrice >= low && cPrice <= high
    const status = current ? 'current' : (travelDown ? (high < cPrice ? 'ahead' : 'passed') : (low > cPrice ? 'ahead' : 'passed'))
    return {
      low,
      high,
      score: Math.round(score),
      sourceCount: sources.length,
      anchorCount: cluster.anchors.length,
      distance: Math.abs(cluster.center - b.price),
      sourceText: sourceDescription(sources, sign),
      status,
      statusText: statusNames[status],
    }
  }).sort((left, right) => statusRank[left.status] - statusRank[right.status]
    || right.sourceCount - left.sourceCount
    || right.anchorCount - left.anchorCount
    || left.distance - right.distance)
  return { bandwidth, zones: zones.slice(0, 3) }
}

function addDirectionalAnchor(anchors, price, from, sign, source, label) {
  if (Number.isFinite(price) && (price - from) * sign > 0) anchors.push({ price, source, label })
}

function sourceDescription(sources, sign) {
  const names = []
  if (sources.includes('extension')) names.push('A浪扩展')
  if (sources.includes('retracement')) names.push('0-5黄金分割回撤')
  if (sources.includes('history')) names.push(`历史${sign < 0 ? '支撑' : '压力'}`)
  return names.join(' + ')
}

function movingAverage(rows, days) {
  return rows.map((_, index) => {
    if (index < days - 1) return null
    return Number((rows.slice(index - days + 1, index + 1).reduce((sum, row) => sum + row.close, 0) / days).toFixed(2))
  })
}

function renderChart() {
  if (!chartEl.value || !bars.value.length) {
    chart?.dispose(); chart = null
    return
  }
  if (!chart) chart = echarts.init(chartEl.value)
  const rows = bars.value
  const dates = rows.map((row) => row.date)
  const confirmed = selectedScale.value?.confirmed || []
  const candidate = selectedCandidate.value
  const windowPoints = candidate?.points || []
  const labelMap = new Map(windowPoints.map((point, index) => [point.index, labels[index] + (!point.confirmed ? '?' : '')]))
  const activeC = candidate && !candidate.complete ? candidate.points.at(-1) : null
  const bPoint = candidate && !candidate.complete ? candidate.points[7] : null
  const targetAreas = targetZones.value.map((zone) => [{ xAxis: bPoint?.date, yAxis: zone.low }, { xAxis: dates.at(-1), yAxis: zone.high }])
  const focusIndex = windowPoints.length ? Math.max(0, windowPoints[0].index - 15) : Math.max(0, rows.length - 120)
  const zoomStart = rows.length > 1 ? focusIndex / (rows.length - 1) * 100 : 0
  chart.setOption({
    animationDuration: 220,
    legend: { show: false },
    grid: { left: 54, right: 22, top: 18, bottom: 58 },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross' },
      formatter(items) {
        const candle = items.find((item) => item.seriesName === 'K线')
        const date = items[0]?.axisValue || ''
        const values = candle?.data || []
        const lines = [`<b>${date}</b>`]
        if (values.length) lines.push(`开 ${priceText(values[0])}　收 ${priceText(values[1])}`, `低 ${priceText(values[2])}　高 ${priceText(values[3])}`)
        const pivots = items.filter((item) => item.data?.pivot).map((item) => item.data.pivot)
        for (const point of pivots) lines.push(`${point.type === 'peak' ? '峰' : '谷'} ${priceText(point.price)} · 极值日 ${point.date} · 确认日 ${point.confirmedAtDate || '待确认'}`)
        return lines.join('<br>')
      },
    },
    xAxis: { type: 'category', data: dates, boundaryGap: true, axisLine: { lineStyle: { color: '#d3d9e0' } }, axisLabel: { color: '#7b8492', fontSize: 10, formatter: (value) => value.slice(5) } },
    yAxis: { scale: true, splitNumber: 5, axisLabel: { color: '#7b8492', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf0f4' } } },
    dataZoom: [
      { type: 'inside', start: zoomStart, end: 100, minValueSpan: Math.min(20, rows.length) },
      { type: 'slider', height: 20, bottom: 10, start: zoomStart, end: 100, borderColor: '#d3d9e0', fillerColor: 'rgba(46,107,198,.12)', handleStyle: { color: '#2e6bc6' }, textStyle: { color: '#7b8492' } },
    ],
    series: [
      { name: 'K线', type: 'candlestick', data: rows.map((row) => [row.open, row.close, row.low, row.high]), itemStyle: { color: '#ef232a', color0: '#14b143', borderColor: '#ef232a', borderColor0: '#14b143' } },
      { name: 'MA20', type: 'line', data: movingAverage(rows, 20), symbol: 'none', smooth: true, lineStyle: { width: 1.4, color: '#d79522' }, emphasis: { disabled: true } },
      { name: '确认折线', type: 'line', data: confirmed.map((point) => [point.date, point.price]), symbol: 'none', lineStyle: { width: 1.6, color: '#2e6bc6' }, z: 4 },
      { name: '确认拐点', type: 'scatter', symbolSize: 6, z: 6, data: confirmed.map((point) => ({ value: [point.date, point.price], pivot: point, itemStyle: { color: point.type === 'peak' ? '#d64b4b' : '#22965c' }, label: labelMap.has(point.index) ? { show: true, formatter: labelMap.get(point.index), position: point.type === 'peak' ? 'top' : 'bottom', color: '#18212f', fontWeight: 700, fontSize: 12 } : { show: false } })) },
      activeC && bPoint ? { name: '活动C', type: 'line', data: [[bPoint.date, bPoint.price], [activeC.date, activeC.price]], symbol: 'none', lineStyle: { width: 2, type: 'dashed', color: '#d79522' }, z: 7 } : null,
      activeC ? { name: '发展中C', type: 'scatter', symbol: 'emptyCircle', symbolSize: 13, z: 8, data: [{ value: [activeC.date, activeC.price], pivot: activeC, itemStyle: { color: '#d79522', borderWidth: 2 }, label: { show: true, formatter: 'C?', position: activeC.type === 'peak' ? 'top' : 'bottom', color: '#9a6512', fontWeight: 700 } }] } : null,
      targetAreas.length ? { name: 'C目标区', type: 'line', data: [], markArea: { silent: true, itemStyle: { color: 'rgba(215,149,34,.12)', borderColor: 'rgba(215,149,34,.38)', borderWidth: 1 }, data: targetAreas } } : null,
    ].filter(Boolean),
  }, true)
  chart.resize()
}

function selectCandidate(item) { selectedCandidateKey.value = item.key }
function ruleResult(label, result, detail) { return { label, detail, state: result == null ? 'pending' : result ? 'pass' : 'fail' } }
function stateText(state) { return ({ pass: '通过', fail: '未通过', pending: '未确认' }[state]) }
function priceText(value) { return value == null || !Number.isFinite(Number(value)) ? '--' : Number(value).toFixed(2) }
function pctText(value) { return value == null || !Number.isFinite(value) ? '--' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%` }
function pctThreshold(value) { return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : '--' }
function median(values) { if (!values.length) return 0; const sorted = [...values].sort((a, b) => a - b); const middle = Math.floor(sorted.length / 2); return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2 }
function average(values) { return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0 }
function clamp(value, low, high) { return Math.min(high, Math.max(low, value)) }
function priceStep(value) { if (value >= 1000) return 5; if (value >= 100) return 1; if (value >= 20) return 0.1; return 0.01 }
function floorStep(value, step) { return Math.floor(value / step) * step }
function ceilStep(value, step) { return Math.ceil(value / step) * step }
function handleResize() { chart?.resize() }

watch([symbol, period], loadKlines, { immediate: true })
watch([bars, scaleMode], () => { selectedCandidateKey.value = '' }, { flush: 'sync' })
watch([bars, scaleMode, selectedCandidateKey], async () => { await nextTick(); renderChart() }, { flush: 'post' })
if (typeof window !== 'undefined') window.addEventListener('resize', handleResize)
onBeforeUnmount(() => { requestId += 1; window.removeEventListener('resize', handleResize); chart?.dispose(); chart = null })
</script>

<style scoped>
.wave-page { padding-bottom:30px; }
.study-head { min-height:92px; display:flex; align-items:center; justify-content:space-between; gap:20px; padding:15px 2px 13px; }
.eyebrow { color:var(--c-primary); font:700 9px var(--font-mono); letter-spacing:.16em; margin-bottom:5px; }
.study-head h1 { font-size:24px; line-height:1.2; }
.study-head p { color:var(--c-text-2); font-size:12px; margin-top:5px; }
.head-status,.chart-legend { display:flex; align-items:center; gap:7px; flex-wrap:wrap; }
.method-badge { padding:4px 7px; border:1px solid #cadcf7; background:#edf4ff; color:var(--c-primary); font:600 10px var(--font-mono); }
.method-badge.muted { border-color:var(--c-border); background:#fff; color:var(--c-text-2); }
.control-sheet { display:grid; grid-template-columns:minmax(190px,1.3fr) auto 130px minmax(150px,.75fr) auto; align-items:end; gap:10px; padding:11px 12px; background:#fff; border:1px solid var(--c-border); border-top:3px solid var(--c-navy); }
.control-block { min-width:0; }
.control-block > label { display:flex; justify-content:space-between; color:var(--c-text-2); font-size:10px; font-weight:600; margin-bottom:6px; }
.control-block label b { color:var(--c-primary); font:700 10px var(--font-mono); }
.primary-controls .el-select,.scale-control .el-select,.control-block .el-input-number { width:100%; }
.chart-sheet { min-height:420px; margin-top:10px; padding:12px 14px 9px; background:#fff; border:1px solid var(--c-border); box-shadow:var(--shadow-card); }
.panel-head { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; }
.panel-head h2 { font-size:14px; line-height:1.3; }.panel-head h2 span { color:var(--c-text-3); font-size:10px; margin-left:4px; font-weight:500; }
.panel-head p { color:var(--c-text-3); font-size:10px; margin-top:3px; }
.panel-head.compact { padding-bottom:9px; border-bottom:1px solid var(--c-border); }
.chart-legend { color:var(--c-text-2); font-size:10px; }
.chart-legend span { display:flex; align-items:center; gap:4px; }.chart-legend i { display:inline-block; width:17px; height:2px; }
.legend-ma { background:#d79522; }.legend-zigzag { background:#2e6bc6; }.legend-candidate { border-top:2px dashed #d79522; }.legend-zone { height:8px !important; background:rgba(215,149,34,.18); border:1px solid rgba(215,149,34,.45); }
.wave-chart { width:100%; height:390px; margin-top:5px; }
.state-panel { display:flex; align-items:center; gap:12px; margin-top:10px; padding:10px 12px; font-size:12px; }
.state-panel span { flex:1; }.error-state { background:#fff1f0; border:1px solid #f2c2be; color:#9f2720; }
.analysis-grid { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(280px,.7fr); gap:10px; margin-top:10px; }
.analysis-grid .card,.detail-grid .card,.target-section { padding:12px 14px; }
.structure-tag { padding:4px 7px; color:#fff; background:var(--c-navy); font-size:11px; font-weight:700; white-space:nowrap; }.structure-tag.empty { background:#667180; }
.conclusion-main { display:grid; grid-template-columns:1fr 1fr 1fr; margin-top:10px; border:1px solid var(--c-border); }
.conclusion-main div { padding:9px 10px; border-left:1px solid var(--c-border); min-width:0; }.conclusion-main div:first-child { border-left:0; }
.conclusion-main small { display:block; color:var(--c-text-3); font-size:9px; margin-bottom:4px; }.conclusion-main strong { display:block; font-size:15px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.candidate-note { margin-top:9px; color:var(--c-text-2); font-size:10px; line-height:1.55; }
.no-structure { display:flex; flex-direction:column; gap:5px; margin-top:12px; padding:12px; border-left:3px solid #788596; background:#f5f7fa; }.no-structure strong { font-size:12px; }.no-structure span { color:var(--c-text-2); font-size:10px; line-height:1.6; }
.candidate-choice { width:100%; display:flex; justify-content:space-between; align-items:center; gap:8px; margin-top:8px; padding:9px 10px; border:1px solid var(--c-border); background:#fff; color:var(--c-text-2); cursor:pointer; text-align:left; font-size:10px; }.candidate-choice:hover { border-color:#9ebbe4; }.candidate-choice.active { border-color:#adc6e9; background:#f2f7ff; color:var(--c-ink); cursor:default; }.candidate-choice b { color:var(--c-primary); font:700 10px var(--font-mono); white-space:nowrap; }
.target-section { margin-top:10px; }
.target-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin-top:10px; }
.target-zone { min-width:0; padding:10px; border:1px solid #ead9b5; background:linear-gradient(135deg,#fffdf8,#fff8e9); }.target-zone div { display:flex; flex-direction:column; gap:3px; }.target-zone span { color:#8a6825; font-size:9px; font-weight:700; }.target-zone b { color:#392f20; font:700 15px var(--font-mono); white-space:nowrap; }.target-zone > strong { display:block; margin-top:8px; color:#9a6512; font-size:10px; }.target-zone p { margin-top:3px; color:var(--c-text-2); font-size:9px; line-height:1.45; }
.target-empty { margin-top:10px; padding:13px; background:#f5f7fa; color:var(--c-text-3); font-size:10px; text-align:center; }.zone-disclaimer { margin-top:9px; color:var(--c-text-2); font-size:10px; line-height:1.55; }
.detail-grid { display:grid; grid-template-columns:minmax(290px,.75fr) minmax(0,1.55fr); gap:10px; margin-top:10px; }
.rule-list > div { display:grid; grid-template-columns:54px 1fr; align-items:center; gap:8px; padding:8px 0; border-bottom:1px solid var(--c-border); }.rule-list > div:last-child { border-bottom:0; }
.rule-state { padding:3px 4px; border:1px solid; font-size:9px; text-align:center; }.is-pass { color:#167b35; border-color:#a8d9b5; background:#effaf2; }.is-fail { color:#b3262c; border-color:#efb9bc; background:#fff2f2; }.is-pending { color:#765411; border-color:#ead394; background:#fff9e8; }
.rule-list strong { display:block; font-size:11px; }.rule-list small { display:block; color:var(--c-text-3); font-size:9px; margin-top:2px; line-height:1.4; }
.count-note { color:var(--c-text-3); font:10px var(--font-mono); white-space:nowrap; }
.table-wrap { width:100%; overflow-x:auto; }
table { width:100%; border-collapse:collapse; min-width:760px; font-size:11px; } th { padding:7px 8px; color:var(--c-text-2); background:#f4f6f9; text-align:left; white-space:nowrap; } td { padding:7px 8px; border-bottom:1px solid var(--c-border); white-space:nowrap; }
.wave-label { display:inline-grid; place-items:center; width:22px; height:22px; color:#fff; background:var(--c-primary); font:700 11px var(--font-mono); }.wave-label.candidate { color:#9a6512; background:#fff5d9; border:1px dashed #d79522; }
.status-text { color:#1c6840; }.status-text.candidate { color:#9a6512; }.empty-cell { padding:18px; text-align:center; color:var(--c-text-3); }
.method-note { display:grid; grid-template-columns:92px 1fr; gap:12px; margin-top:10px; padding:10px 12px; border-left:3px solid #d79522; background:#fffaf0; color:var(--c-text-2); font-size:10px; line-height:1.55; }
@media (max-width:1200px) { .control-sheet { grid-template-columns:repeat(4,minmax(0,1fr)); }.control-sheet > .el-button { width:100%; }.analysis-grid,.detail-grid { grid-template-columns:1fr; }.target-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media (max-width:700px) {
  .wave-page { padding-left:10px; padding-right:10px; }.study-head { align-items:flex-start; flex-direction:column; gap:8px; padding:13px 2px; }.study-head h1 { font-size:21px; }
  .control-sheet { grid-template-columns:1fr 1fr; }.primary-controls { grid-column:1 / -1; }.control-sheet > .el-button { width:100%; }
  .chart-sheet { min-height:390px; padding:10px 8px; }.panel-head { flex-direction:column; gap:8px; }.wave-chart { height:340px; }
  .conclusion-main { grid-template-columns:1fr; }.conclusion-main div { border-left:0; border-top:1px solid var(--c-border); }.conclusion-main div:first-child { border-top:0; }
  .target-grid { grid-template-columns:1fr; }.method-note { grid-template-columns:1fr; gap:4px; }.analysis-grid .card,.detail-grid .card,.target-section { padding:10px; }
}
@media (max-width:420px) { .control-sheet { grid-template-columns:1fr; }.primary-controls { grid-column:auto; }.period-control :deep(.el-radio-group) { display:flex; }.period-control :deep(.el-radio-button) { flex:1; }.period-control :deep(.el-radio-button__inner) { width:100%; }.wave-chart { height:320px; } }
@media (prefers-reduced-motion:reduce) { :deep(*) { animation-duration:.01ms !important; transition-duration:.01ms !important; } }
</style>
