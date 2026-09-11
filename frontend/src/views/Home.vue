<template>
  <MainLayout>
    <div class="page">
      <div class="flex gap" style="align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h2 style="font-size: 18px">大盘看板</h2>
        <el-tag size="small" type="info">{{ todayStr }}</el-tag>
        <el-button size="small" type="primary" :loading="loading" @click="load">刷新</el-button>
        <el-button size="small" type="warning" :loading="mktLoading" @click="analyzeMarket">AI 大盘分析</el-button>
        <span class="fs12" style="color:#909399">每 15 秒自动刷新行情</span>
      </div>

      <!-- 三大指数整行展示：每个面板独立周期（分时/日K/60/30/15/5分），分时与K线均带成交量 -->
      <el-row :gutter="10">
        <el-col v-for="mc in mainIdxDefs" :key="mc.code" :xs="24" :sm="8">
          <div class="card ix-panel">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <div>
                <span class="fs13 bold">{{ mc.name }}</span>
                <span class="fs12 ml4" style="color:#909399">{{ mc.code }}</span>
              </div>
              <el-select :model-value="indexPeriods[mc.code] || 'mf'" size="small" style="width:82px"
                @change="(v) => changeIndexPeriod(mc.code, v)">
                <el-option v-for="p in indexPeriodDefs" :key="p.val" :value="p.val" :label="p.label" />
              </el-select>
            </div>
            <div class="mt4">
              <div class="mono fs18 bold" :class="ixCls(mc.code)">
                {{ fmtPrice(ixOf(mc.code)?.price) }}
                <span class="fs13">({{ (ixOf(mc.code)?.change_pct ?? 0) >= 0 ? '+' : '' }}{{ fmtPct(ixOf(mc.code)?.change_pct) }}%)</span>
              </div>
              <div class="fs12" style="color:#909399">成交 {{ fmtMoney(ixOf(mc.code)?.amount) }}</div>
            </div>
            <div class="chart-box mt4">
              <template v-if="(indexPeriods[mc.code] || 'mf') !== 'mf'">
                <KlineChart v-if="indexKlines[keyOf(mc.code)]?.length" :data="indexKlines[keyOf(mc.code)]" height="220px" />
                <div v-else class="fs12" style="color:#909399;text-align:center;height:220px;line-height:220px">K线加载中…</div>
              </template>
              <template v-else>
                <LineChart v-if="indexIntradays[mc.code]?.length" :data="indexIntradays[mc.code]" height="200px" :volume="true" />
                <div v-else class="fs12" style="color:#909399;text-align:center;height:200px;line-height:200px">分时加载中…</div>
              </template>
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 市场状态卡片 -->
      <el-row :gutter="10" class="mt8">
        <el-col :span="24">
          <div class="card">
            <div class="flex gap" style="align-items:center;flex-wrap:wrap">
              <span class="fs14 bold">市场状态</span>
              <el-tag :type="emotion.tagType" size="small">{{ emotion.label }}</el-tag>
              <el-divider direction="vertical" />
              <span class="fs12 up">上涨 {{ distribution.up_count ?? '-' }}</span>
              <span class="fs12 down">下跌 {{ distribution.down_count ?? '-' }}</span>
              <span class="fs12 flat">平盘 {{ distribution.flat_count ?? '-' }}</span>
              <el-divider direction="vertical" />
              <span class="fs12" style="color:#f56c6c">涨停 <b>{{ distribution.limit_up ?? '0' }}</b></span>
              <span class="fs12" style="color:#67c23a">跌停 <b>{{ distribution.limit_down ?? '0' }}</b></span>
              <span class="fs12" style="color:#909399">连板高度 <b>{{ maxBoard }}</b></span>
              <el-divider direction="vertical" />
              <span class="fs12" style="color:#606266">A股成交 <b class="mono">{{ fmtMoney(distribution.amount) }}</b></span>
              <span class="fs12" style="color:#606266">涨跌停比 <b>{{ ratioUpDown }}</b></span>
            </div>
            <!-- 涨跌区间分布柱状图 -->
            <div class="mt8" style="border-top:1px dashed #f0f0f0;padding-top:8px">
              <div class="fs12 mb8" style="color:#909399">涨跌区间分布（家数）</div>
              <div class="dist-bars" v-if="distBuckets.length">
                <div v-for="(b, i) in distBuckets" :key="i" class="dist-col" :title="b.label + '：' + b.count + ' 家'">
                  <span class="dist-num mono" :class="b.cls">{{ b.count }}</span>
                  <div class="dist-bar" :style="{ height: b.h + 'px', background: b.color }" />
                  <span class="dist-label">{{ b.label }}</span>
                </div>
              </div>
              <div v-else class="fs12" style="color:#c0c4cc">暂无分布数据</div>
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 人气股票排行 TOP5 -->
      <el-row :gutter="10" class="mt8">
        <el-col :span="24">
          <div class="card">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <span class="fs14 bold">人气股票 TOP5 <span class="fs12" style="color:#909399">（按当日 换手×量比×涨幅 综合热度估算）</span></span>
              <span class="fs12" style="color:#909399">点击进入个股详情 · {{ todayStr }}</span>
            </div>
            <div class="hot-grid mt8">
              <div v-for="(r, i) in hotStocks" :key="r.symbol" class="hot-card" @click="goStock(r.symbol, r.name)">
                <div class="flex between" style="align-items:center;gap:4px">
                  <span class="fs13 bold">{{ i + 1 }}. {{ r.name }}</span>
                  <el-tag size="small" :type="Number(r.change_pct) >= 0 ? 'danger' : 'success'">
                    {{ Number(r.change_pct) >= 0 ? '+' : '' }}{{ r.change_pct }}%
                  </el-tag>
                </div>
                <div class="mono fs15" style="color:#303133">{{ r.price }}</div>
                <div class="fs11" style="color:#909399">
                  热度 <b :style="{ color: hotColor(r.heat) }">{{ r.heat }}</b>
                  · 换手 {{ r.hsl }}% · 量比 {{ r.lb }} · 成交 {{ fmtMoney(r.turnover * 1e4) }}
                </div>
                <div class="heat-bar"><div class="heat-fill" :style="{ width: Math.min(100, r.heat) + '%' }" /></div>
              </div>
              <el-empty v-if="!hotStocks.length" description="暂无人气排行" :image-size="40" />
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 板块监控：自选板块ETF + 概念/行业实时行情 -->
      <el-row :gutter="10" class="mt8">
        <el-col :span="24">
          <div class="card">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <span class="fs14 bold">板块监控</span>
              <div class="flex gap" style="align-items:center">
                <span class="fs12" style="color:#909399">点击板块查看分时</span>
                <el-button size="small" :loading="sectorLoading" @click="loadSectorMonitor">刷新</el-button>
              </div>
            </div>
            <div class="sector-grid mt8">
              <div v-for="s in sectorList" :key="s.symbol"
                class="sector-card" :class="{ active: selectedSector?.symbol === s.symbol }"
                @click="selectSector(s)">
                <div class="fs12 bold">{{ s.sector }}</div>
                <div class="mono fs13" :class="Number(s.change_pct) >= 0 ? 'up' : 'down'">
                  {{ Number(s.change_pct) >= 0 ? '+' : '' }}{{ (s.change_pct || 0).toFixed(2) }}%
                </div>
                <div class="fs11" style="color:#909399">{{ fmtMoney(s.amount) }}</div>
                <div v-if="s.is_etf === false" class="fs11" style="color:#c0c4cc">
                  领涨 <b style="color:#606266">{{ s.leader_name || '-' }}</b>
                </div>
              </div>
              <el-empty v-if="!sectorList.length" description="暂无数据" :image-size="40" />
            </div>
            <!-- 选中板块详情：ETF 有分时图，概念/行业展示实时行情+领涨股 -->
            <div v-if="selectedSector" class="mt8" style="border-top:1px solid #f0f0f0;padding-top:8px">
              <div class="flex gap" style="align-items:center;flex-wrap:wrap">
                <span class="fs13 bold">{{ selectedSector.name }}</span>
                <span class="mono fs13" :class="Number(selectedSector.change_pct) >= 0 ? 'up' : 'down'">
                  {{ selectedSector.price || '-' }} ({{ Number(selectedSector.change_pct) >= 0 ? '+' : '' }}{{ (selectedSector.change_pct || 0).toFixed(2) }}%)
                </span>
                <span class="fs12" style="color:#909399">{{ fmtMoney(selectedSector.amount) }}</span>
              </div>
              <template v-if="selectedSector.is_etf === false">
                <div class="fs12 mt4" style="line-height:1.8">
                  成分股 <b>{{ selectedSector.count || '-' }}</b> · 领涨股
                  <el-link v-if="selectedSector.leader_symbol" type="primary" :underline="false" style="font-size:12px"
                    @click="goStock(selectedSector.leader_symbol, selectedSector.leader_name)">
                    {{ selectedSector.leader_name }}
                  </el-link>
                  <span v-else>{{ selectedSector.leader_name || '-' }}</span>
                  <span class="fs11" style="color:#c0c4cc">（概念板块暂无 ETF 分时，展示板块实时行情）</span>
                </div>
              </template>
              <template v-else>
                <LineChart v-if="sectorIntraday.length" :data="sectorIntraday" height="180px" :pre-close="sectorPreClose" class="mt4" />
                <div v-else class="fs12" style="color:#909399;text-align:center;height:60px;line-height:60px">分时数据加载中…</div>
              </template>
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 板块资金流：行业 / 概念，各流入·流出前5 -->
      <el-row :gutter="10" class="mt8">
        <el-col :xs="24" :sm="12">
          <div class="card col-card">
            <div class="fs14 bold">行业资金流 <span class="fs12" style="color:#909399">（东方财富板块主力净流入，单位亿元）</span></div>
            <div class="split-grid mt8">
              <div>
                <div class="fs12 bold" style="color:#f56c6c">流入 TOP5</div>
                <div v-for="(r, i) in flowRank.industries.in" :key="'ii' + i" class="flow-row">
                  <span class="fs12">{{ i + 1 }}.{{ r.name }}
                    <el-link v-if="r.leader_symbol" type="primary" :underline="false" style="font-size:11px;margin-left:2px"
                      @click.stop="goStock(r.leader_symbol, r.leader)">领涨 {{ r.leader }}</el-link>
                    <i v-else class="fs11" style="color:#b0b3b8;font-style:normal">领涨 {{ r.leader }}</i>
                  </span>
                  <span class="mono fs12 up">{{ r.amount }}亿</span>
                  <span class="mono fs12 up">{{ r.change_pct >= 0 ? '+' : '' }}{{ r.change_pct }}%</span>
                </div>
                <el-empty v-if="!flowRank.industries.in.length" description="暂无" :image-size="34" />
              </div>
              <div>
                <div class="fs12 bold" style="color:#67c23a">流出 TOP5</div>
                <div v-for="(r, i) in flowRank.industries.out" :key="'io' + i" class="flow-row">
                  <span class="fs12">{{ i + 1 }}.{{ r.name }}
                    <el-link v-if="r.leader_symbol" type="primary" :underline="false" style="font-size:11px;margin-left:2px"
                      @click.stop="goStock(r.leader_symbol, r.leader)">领涨 {{ r.leader }}</el-link>
                    <i v-else class="fs11" style="color:#b0b3b8;font-style:normal">领涨 {{ r.leader }}</i>
                  </span>
                  <span class="mono fs12 down">{{ r.amount }}亿</span>
                  <span class="mono fs12 down">{{ r.change_pct >= 0 ? '+' : '' }}{{ r.change_pct }}%</span>
                </div>
                <el-empty v-if="!flowRank.industries.out.length" description="暂无" :image-size="34" />
              </div>
            </div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12">
          <div class="card col-card">
            <div class="fs14 bold">概念资金流 <span class="fs12" style="color:#909399">（东方财富板块主力净流入，单位亿元）</span></div>
            <div class="split-grid mt8">
              <div>
                <div class="fs12 bold" style="color:#f56c6c">流入 TOP5</div>
                <div v-for="(r, i) in flowRank.concepts.in" :key="'ci' + i" class="flow-row">
                  <span class="fs12">{{ i + 1 }}.{{ r.name }}
                    <el-link v-if="r.leader_symbol" type="primary" :underline="false" style="font-size:11px;margin-left:2px"
                      @click.stop="goStock(r.leader_symbol, r.leader)">领涨 {{ r.leader }}</el-link>
                    <i v-else class="fs11" style="color:#b0b3b8;font-style:normal">领涨 {{ r.leader }}</i>
                  </span>
                  <span class="mono fs12 up">{{ r.amount }}亿</span>
                  <span class="mono fs12 up">{{ r.change_pct >= 0 ? '+' : '' }}{{ r.change_pct }}%</span>
                </div>
                <el-empty v-if="!flowRank.concepts.in.length" description="暂无" :image-size="34" />
              </div>
              <div>
                <div class="fs12 bold" style="color:#67c23a">流出 TOP5</div>
                <div v-for="(r, i) in flowRank.concepts.out" :key="'co' + i" class="flow-row">
                  <span class="fs12">{{ i + 1 }}.{{ r.name }}
                    <el-link v-if="r.leader_symbol" type="primary" :underline="false" style="font-size:11px;margin-left:2px"
                      @click.stop="goStock(r.leader_symbol, r.leader)">领涨 {{ r.leader }}</el-link>
                    <i v-else class="fs11" style="color:#b0b3b8;font-style:normal">领涨 {{ r.leader }}</i>
                  </span>
                  <span class="mono fs12 down">{{ r.amount }}亿</span>
                  <span class="mono fs12 down">{{ r.change_pct >= 0 ? '+' : '' }}{{ r.change_pct }}%</span>
                </div>
                <el-empty v-if="!flowRank.concepts.out.length" description="暂无" :image-size="34" />
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 消息滚动 + ETF资金流 -->
      <el-row :gutter="10" class="mt8">
        <el-col :xs="24" :sm="14">
          <div class="card col-card">
            <div class="fs14 bold">消息滚动 <span class="fs12" style="color:#909399">（区分板块与重要性）</span></div>
            <el-scrollbar class="news-scroll">
              <div v-for="(n, i) in news" :key="i" class="news-item">
                <el-tag size="small" :type="impTag(n.importance)" style="flex-shrink:0">{{ impText(n.importance) }}</el-tag>
                <el-tag size="small" type="info" effect="plain" style="flex-shrink:0">{{ n.category }}</el-tag>
                <a v-if="n.url" :href="n.url" target="_blank" rel="noopener" class="fs12 news-title">{{ n.title }}</a>
                <span v-else class="fs12 news-title">{{ n.title }}</span>
                <span class="fs12 news-time">{{ formatNewsTime(n.time) }}</span>
              </div>
              <el-empty v-if="!news.length" description="暂无消息" :image-size="50" />
            </el-scrollbar>
          </div>
        </el-col>
        <el-col :xs="24" :sm="10">
          <div class="card col-card">
            <div class="flex between" style="align-items:center">
              <span class="fs14 bold">ETF 资金流 <span class="fs12 mono" style="color:#909399">（截至 {{ etfFlowDate }}）</span></span>
              <el-radio-group v-model="etfDim" size="small">
                <el-radio-button value="net_1d">今日</el-radio-button>
                <el-radio-button value="net_5d">5日</el-radio-button>
                <el-radio-button value="net_20d">20日</el-radio-button>
              </el-radio-group>
            </div>
            <div class="split-grid mt8">
              <div>
                <div class="fs12 bold" style="color:#f56c6c">净流入 TOP5</div>
                <div v-for="(r, i) in etfIn" :key="'ei' + i" class="flow-row">
                  <span class="fs12">{{ r.name }}</span>
                  <span class="mono fs12 up">{{ r[etfDim] }}亿</span>
                </div>
                <el-empty v-if="!etfIn.length" description="暂无" :image-size="34" />
              </div>
              <div>
                <div class="fs12 bold" style="color:#67c23a">净流出 TOP5</div>
                <div v-for="(r, i) in etfOut" :key="'eo' + i" class="flow-row">
                  <span class="fs12">{{ r.name }}</span>
                  <span class="mono fs12 down">{{ r[etfDim] }}亿</span>
                </div>
                <el-empty v-if="!etfOut.length" description="暂无" :image-size="34" />
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- AI 大盘分析（内联显示，非弹框） -->
      <el-row :gutter="10" class="mt8">
        <el-col :span="24">
          <div class="card" v-if="mktSummary">
            <div class="flex between" style="align-items:center;margin-bottom:8px">
              <span class="fs14 bold">AI 大盘分析</span>
              <span class="fs12" style="color:#909399">{{ mktDate }}</span>
            </div>
            <div class="mkt-text">{{ mktSummary }}</div>
          </div>
        </el-col>
      </el-row>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import MainLayout from '../layout/MainLayout.vue'
import LineChart from '../components/LineChart.vue'
import KlineChart from '../components/KlineChart.vue'
import { marketApi, agentApi } from '../api'

const router = useRouter()
function goStock(symbol, name) {
  if (!symbol) return
  router.push({ path: '/watchlist', query: { symbol, name: name || '' } })
}

const loading = ref(false)
const mktLoading = ref(false)
const mktSummary = ref('')
const mktDate = ref('')
const indices = ref([])
const news = ref([])
function formatNewsTime(ts) {
  if (!ts || isNaN(Number(ts))) return ts || ''
  const d = new Date(Number(ts) * 1000)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  if (isToday) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  return `${d.getMonth() + 1}/${d.getDate()} ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}`
}
const ladder = ref({})
const distribution = ref({})
const flowRank = ref({ industries: { in: [], out: [] }, concepts: { in: [], out: [] } })
const etfFlow = ref({ in_top: [], out_top: [], all: [] })
const etfDim = ref('net_1d')

const sectorList = ref([])
const sectorLoading = ref(false)
const selectedSector = ref(null)
const sectorIntraday = ref([])
const sectorPreClose = ref(0)
const hotStocks = ref([])

function hotColor(heat) {
  const n = Number(heat || 0)
  return n >= 80 ? '#ef232a' : n >= 60 ? '#f56c6c' : '#e6a23c'
}

async function loadHotStocks() {
  try { hotStocks.value = (await marketApi.hotStocks()) || [] } catch { /* 保留旧数据 */ }
}

async function loadSectorMonitor() {
  sectorLoading.value = true
  try {
    sectorList.value = (await marketApi.sectorMonitor()) || []
  } catch { sectorList.value = [] }
  sectorLoading.value = false
}

async function selectSector(s) {
  selectedSector.value = s
  sectorIntraday.value = []
  sectorPreClose.value = 0
  if (s.is_etf === false) return
  try {
    const data = (await marketApi.sectorMonitorIntraday(s.symbol)) || []
    sectorIntraday.value = data
    if (data.length) sectorPreClose.value = data[0].price || 0
  } catch { sectorIntraday.value = [] }
}

const indexPeriodDefs = [
  { val: 'mf', label: '分时' },
  { val: 'day', label: '日K' },
  { val: 'm60', label: '60分' },
  { val: 'm30', label: '30分' },
  { val: 'm15', label: '15分' },
  { val: 'm5', label: '5分' }
]
const indexPeriods = reactive({})
const indexIntradays = reactive({})
const indexKlines = reactive({})
const keyOf = (code) => `${code}:${indexPeriods[code] || 'mf'}`

const mainIdxDefs = [
  { code: 'SH000001', name: '上证指数' },
  { code: 'SZ399006', name: '创业板指' },
  { code: 'SH000688', name: '科创50' }
]

function ixOf(code) {
  return indices.value.find((ix) => ix.code === code)
}
function ixCls(code) {
  const pct = ixOf(code)?.change_pct ?? 0
  return Number(pct) >= 0 ? 'up' : 'down'
}
const etfIn = computed(() => etfFlow.value.in_top || [])
const etfOut = computed(() => etfFlow.value.out_top || [])
const etfFlowDate = computed(() => (etfFlow.value.in_top || []).find((r) => r.flow_date)?.flow_date || '')
const maxBoard = computed(() => {
  const keys = Object.keys(ladder.value.ladder || {})
  return keys.length ? Math.max(...keys.map((k) => parseInt(k, 10))) : 0
})
const ratioUpDown = computed(() => {
  const up = distribution.value.limit_up || 0
  const down = distribution.value.limit_down || 0
  if (down === 0) return up > 0 ? '∞' : '-'
  return (up / down).toFixed(1)
})

const DIST_ORDER = ['≤-9%', '-9%~-7%', '-7%~-5%', '-5%~-3%', '-3%~0%', '平盘', '0%~+3%', '+3%~+5%', '+5%~+7%', '+7%~+9%', '≥+9%']
const distBuckets = computed(() => {
  const bk = distribution.value.buckets || {}
  if (!Object.keys(bk).length) return []
  const items = DIST_ORDER.map(label => ({ label, count: Number(bk[label]) || 0 }))
  const max = Math.max(1, ...items.map(b => b.count))
  return items.map(b => ({
    label: b.label, count: b.count,
    cls: b.label === '平盘' ? '' : b.label.includes('-') || b.count === 0 ? 'down' : 'up',
    color: b.label === '平盘' ? '#909399' : b.label.includes('-') ? '#14b143' : '#e6452f',
    h: 6 + Math.round(b.count / max * 40)
  }))
})
const emotion = computed(() => {
  const up = distribution.value.up_count || 0
  const down = distribution.value.down_count || 0
  const limUp = distribution.value.limit_up || 0
  const limDown = distribution.value.limit_down || 0
  const breadth = up - down
  const risk = limUp - limDown
  if (breadth > 200 && risk > 0) return { label: '情绪偏强 · 赚钱效应好', tagType: 'danger' }
  if (breadth > 0 && risk >= 0) return { label: '震荡偏强', tagType: 'warning' }
  if (breadth < -200 && risk < 0) return { label: '情绪冰点 · 亏钱效应', tagType: 'info' }
  if (breadth < 0) return { label: '震荡偏弱', tagType: 'info' }
  return { label: '多空均衡', tagType: 'success' }
})

const impText = (v) => (v === 1 ? '重要' : v === 3 ? '一般' : '普通')
const impTag = (v) => (v === 1 ? 'danger' : v === 3 ? 'info' : 'warning')

const todayStr = new Date().toLocaleDateString('zh-CN')

function fmtPrice(v) {
  return v == null ? '-' : Number(v).toFixed(2)
}
function fmtPct(v) {
  return v == null ? '0.00' : Number(v).toFixed(2)
}
function fmtMoney(v) {
  if (v == null) return '-'
  const n = Number(v)
  const abs = Math.abs(n)
  if (abs >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (abs >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(0)
}

// ---- 每个看板模块独立接口调用，独立定时刷新 ----
async function loadIndices() {
  try { indices.value = await marketApi.indices() } catch { /* 保留旧数据 */ }
}
async function loadIndexIntraday(code) {
  try {
    const rows = await marketApi.intraday({ symbol: code })
    if (Array.isArray(rows)) indexIntradays[code] = rows
  } catch {
    indexIntradays[code] = indexIntradays[code] || []
  }
}
async function loadIndexKline(code, period) {
  const key = `${code}:${period}`
  try {
    const r = await marketApi.kline({ symbol: code, period })
    indexKlines[key] = r?.data || []
  } catch {
    indexKlines[key] = indexKlines[key] || []
  }
}
function loadPanel(code) {
  if ((indexPeriods[code] || 'mf') === 'mf') loadIndexIntraday(code)
  else loadIndexKline(code, indexPeriods[code])
}
function changeIndexPeriod(code, v) {
  indexPeriods[code] = v
  loadPanel(code)
}
async function loadSectorFlowTop() {
  try { flowRank.value = await marketApi.sectorFlowTop() } catch { /* 保留旧数据 */ }
}
async function loadEtf() {
  try { etfFlow.value = await marketApi.etfFlow() } catch { /* 保留旧数据 */ }
}
async function loadNews() {
  try { news.value = (await marketApi.news(50)) || [] } catch { /* 保留旧数据 */ }
}
async function loadDistribution() {
  try { distribution.value = (await marketApi.distribution()) || {} } catch { /* 保留旧数据 */ }
}
async function loadLadder() {
  try { ladder.value = (await marketApi.limitUpLadder()) || {} } catch { /* 保留旧数据 */ }
}

async function analyzeMarket() {
  mktLoading.value = true
  try {
    const r = await agentApi.analyzeMarket()
    mktSummary.value = r?.summary || r?.raw_output || '（空结果，请检查智能体配置）'
    mktDate.value = new Date().toLocaleString('zh-CN')
  } finally {
    mktLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    await Promise.all([
      loadIndices(),
      ...mainIdxDefs.map((m) => loadPanel(m.code)),
      loadSectorFlowTop(),
      loadEtf(),
      loadNews(),
      loadDistribution(),
      loadLadder(),
      loadSectorMonitor(),
      loadHotStocks()
    ])
  } finally {
    loading.value = false
  }
}

let indexTimer = null
let newsTimer = null
let flowTimer = null
let distTimer = null
let sectorTimer = null

onMounted(() => {
  load()
  indexTimer = setInterval(() => { loadIndices(); mainIdxDefs.forEach((m) => loadPanel(m.code)) }, 15000)
  newsTimer = setInterval(loadNews, 60000)
  flowTimer = setInterval(() => { loadSectorFlowTop(); loadEtf(); loadHotStocks() }, 60000)
  distTimer = setInterval(() => { loadDistribution(); loadLadder() }, 60000)
  sectorTimer = setInterval(loadSectorMonitor, 15000)
})
onUnmounted(() => {
  if (indexTimer) clearInterval(indexTimer)
  if (newsTimer) clearInterval(newsTimer)
  if (flowTimer) clearInterval(flowTimer)
  if (distTimer) clearInterval(distTimer)
  if (sectorTimer) clearInterval(sectorTimer)
})
</script>

<style scoped>
.news-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 0;
  border-bottom: 1px dashed #f0f0f0;
}
.news-title {
  color: #303133;
  text-decoration: none;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.news-time {
  color: #c0c4cc;
  flex-shrink: 0;
}
.col-card {
  display: flex;
  flex-direction: column;
}
.news-scroll {
  flex: 1;
  height: 240px;
  margin-top: 8px;
}
.ix-panel {
  border-radius: 8px;
  height: 100%;
}
.chart-box {
  min-height: 200px;
}
.idx-card {
  cursor: pointer;
  border: 2px solid transparent;
}
.idx-card.active {
  border-color: #409eff;
}
.split-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.flow-row {
  display: grid;
  grid-template-columns: 1fr 72px 64px;
  gap: 4px;
  padding: 4px 0;
  border-bottom: 1px dashed #f5f5f5;
  align-items: center;
}
.mkt-text {
  white-space: pre-wrap;
  line-height: 1.9;
  max-height: 55vh;
  overflow: auto;
}
.sector-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}
.sector-card {
  padding: 8px;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  cursor: pointer;
  text-align: center;
  transition: all .15s;
}
.sector-card:hover { border-color: #409eff; background: #f0f7ff; }
.sector-card.active { border-color: #409eff; background: #ecf5ff; font-weight: 600; }
.hot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
  gap: 8px;
}
.hot-card {
  padding: 10px;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  cursor: pointer;
  transition: all .15s;
  line-height: 1.7;
}
.hot-card:hover { border-color: #ef232a; background: #fff5f5; }
.heat-bar {
  height: 5px;
  border-radius: 3px;
  background: #f0f0f0;
  margin-top: 6px;
  overflow: hidden;
}
.heat-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, #f7b32b, #ef232a);
}
.dist-bars {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}
.dist-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 3px;
  min-width: 40px;
  flex: 1;
  cursor: default;
}
.dist-num { font-size: 11px; line-height: 1; }
.dist-bar { width: 70%; border-radius: 2px 2px 0 0; min-height: 2px; opacity: .85; }
.dist-label { font-size: 10px; color: #909399; white-space: nowrap; }
</style>