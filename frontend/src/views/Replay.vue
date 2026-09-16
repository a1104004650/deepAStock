<template>
  <MainLayout>
    <div class="page">
      <div class="flex gap" style="align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h2 style="font-size:18px">每日复盘</h2>
        <el-button size="small" type="primary" :loading="loading" @click="load">刷新</el-button>
        <el-select v-if="historyDates.length" v-model="viewDate" size="small" style="width:170px;margin-left:8px"
          placeholder="历史复盘日期" @change="(d) => viewReport(d)">
          <el-option v-for="d in historyDates" :key="d" :label="d" :value="d" />
        </el-select>
        <el-tag v-if="rpt?.date" size="small" type="info" style="margin-left:8px">查看 {{ rpt.date }}</el-tag>
        <el-select v-model="triggerDate" size="small" style="width:150px;margin-left:8px">
          <el-option v-for="i in 30" :key="i" :label="dateStr(i) + (i === 0 ? '（今日）' : '')" :value="dateStr(i)" />
        </el-select>
        <el-button size="small" :loading="triggering" @click="trigger"
          :type="status === 'pending' ? 'danger' : 'warning'">
          生成复盘
        </el-button>
        <el-tag v-if="status === 'pending'" size="small" type="warning">今日尚未生成，交易日 18:00 自动复盘</el-tag>
        <el-tag v-if="status === 'empty'" size="small" type="info">暂无复盘记录</el-tag>
        <div style="flex:1"></div>
        <el-button v-if="rpt?.report_md" size="small" @click="mdDialog = true">查看复盘原文 (Markdown)</el-button>
      </div>

      <el-alert
        v-if="status === 'pending'"
        type="warning"
        :closable="false"
        show-icon
        class="mt8"
        :title="report?.message || '今日复盘尚未生成，交易日 18:00 将自动生成，也可点击「生成复盘」立即生成'"
      />

      <el-alert
        v-if="status === 'gated'"
        type="error"
        :closable="false"
        show-icon
        class="mt8"
        :title="report?.message || '当前时间受限，无法生成该日期复盘'"
      />

      <el-alert
        v-if="rpt && emLimited"
        type="warning"
        :closable="false"
        show-icon
        class="mt8"
        title="板块资金流 / 龙虎榜显示东方财富当日行情，休市期间可能为空"
      />

      <template v-if="rpt">
        <el-row :gutter="10">
          <el-col :xs="24" :sm="16">
            <div class="card">
              <div class="fs14 bold">大盘概况</div>
              <el-table :data="arr(rpt.market_summary?.indices) || []" size="small" class="mt8">
                <el-table-column prop="name" label="指数" />
                <el-table-column prop="price" label="点位" align="right" />
                <el-table-column label="涨跌幅" align="right">
                  <template #default="{ row }">
                    <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct >= 0 ? '+' : '' }}{{ row.change_pct }}%</span>
                  </template>
                </el-table-column>
              </el-table>
              <div class="fs12 mt8" style="color:#909399">
                涨停 {{ rpt.market_summary?.limit_up_count ?? 0 }} 家 · 上涨 {{ rpt.market_summary?.distribution?.up_count ?? '-' }} / 下跌 {{ rpt.market_summary?.distribution?.down_count ?? '-' }}
              </div>
              <div class="fs12 mt8" v-if="arr(rpt.market_summary?.news).length">
                <span class="bold">要闻：</span>{{ rpt.market_summary.news[0].title }}
              </div>
            </div>

            <div class="card mt8">
              <div class="fs14 bold">板块资金流（主力净流入）</div>
              <el-table :data="arr(rpt.sector_flow).slice(0, 12)" size="small" class="mt8">
                <el-table-column label="板块" min-width="110">
                  <template #default="{ row }">{{ row.sector_name || row.name }}</template>
                </el-table-column>
                <el-table-column label="主力净" align="right" width="90">
                  <template #default="{ row }">
                    <span class="mono" :class="(row.net_inflow||0) >= 0 ? 'up' : 'down'">{{ fmtBig(row.net_inflow) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="净占比" align="right" width="70">
                  <template #default="{ row }">{{ row.net_ratio == null ? '-' : row.net_ratio + '%' }}</template>
                </el-table-column>
                <el-table-column label="涨幅" align="right" width="70">
                  <template #default="{ row }">
                    <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct == null ? '-' : ((row.change_pct >= 0 ? '+' : '') + row.change_pct + '%') }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="涨停" align="right" width="64">
                  <template #default="{ row }">
                    <span class="mono up">{{ row.limit_up_count ?? '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="跌停" align="right" width="64">
                  <template #default="{ row }">
                    <span class="mono down">{{ row.limit_down_count ?? '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="领涨" min-width="90">
                  <template #default="{ row }">
                    <el-link v-if="row.leader_symbol" type="primary" :underline="false" @click="goStock(row.leader_symbol, row.leader)">
                      {{ row.leader || '-' }}
                    </el-link>
                    <span v-else>-</span>
                  </template>
                </el-table-column>
                <el-table-column label="市值龙头" min-width="130">
                  <template #default="{ row }">
                    <span v-for="(m, i) in (row.mkt_cap_top || [])" :key="i" class="fs12 mr8">
                      {{ ['龙一', '龙二', '龙三'][i] }}:
                      <el-link v-if="m.symbol" type="primary" :underline="false" @click="goStock(m.symbol, m.name)">{{ m.name }}</el-link>
                    </span>
                    <span v-if="!(row.mkt_cap_top || []).length">-</span>
                  </template>
                </el-table-column>
                <el-table-column label="人气票" width="70">
                  <template #default="{ row }">
                    <el-link v-if="row.hot_pick?.symbol" type="primary" :underline="false" @click="goStock(row.hot_pick.symbol, row.hot_pick.name)">{{ row.hot_pick.name }}</el-link>
                    <span v-else>-</span>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="!arr(rpt.sector_flow).length" description="当日东方财富板块资金数据为空（休市或网络受限）" :image-size="50" />
            </div>
          </el-col>

          <el-col :xs="24" :sm="8">
            <div class="card">
              <div class="fs14 bold">涨停梯队</div>
              <div v-for="(items, days) in sortedLadder" :key="days" class="ladder-group mt8">
                <div class="ladder-header">
                  <el-tag size="small" :type="days >= 3 ? 'danger' : days >= 2 ? 'warning' : 'info'">
                    {{ days }}板 ({{ items.length }}只)
                  </el-tag>
                  <span v-if="days == maxBoard" class="fs11 bold" style="color:#ef232a;margin-left:4px">最高板</span>
                </div>
                <div class="ladder-stocks">
                  <el-link v-for="s in items" :key="s.symbol" type="primary" :underline="false"
                    @click="goStock(s.symbol, s.name)" style="margin-right:10px;margin-bottom:4px">
                    {{ s.name || s.symbol }}
                    <span class="fs11" :class="(s.change_pct||0) >= 0 ? 'up' : 'down'" v-if="s.change_pct != null">
                      {{ s.change_pct >= 0 ? '+' : '' }}{{ s.change_pct }}%
                    </span>
                  </el-link>
                </div>
              </div>
              <el-empty v-if="!Object.keys(sortedLadder).length" description="数据源受限，暂无涨停梯队" :image-size="50" />
            </div>
            <div class="card mt8">
              <div class="fs14 bold">龙虎榜（{{ arr(rpt.limit_analysis?.dragon_tiger).length }}）</div>
              <el-table :data="arr(rpt.limit_analysis?.dragon_tiger).slice(0, 10)" size="small" class="mt8"
                @row-click="(row) => goStock(row.symbol, row.name)">
                <el-table-column prop="name" label="名称" width="74" />
                <el-table-column prop="symbol" label="代码" width="88" />
                <el-table-column label="净买额" align="right" width="86">
                  <template #default="{ row }">
                    <span class="mono" :class="(row.net_amount||0) >= 0 ? 'up' : 'down'">{{ fmtBig(row.net_amount) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="涨幅" width="62" align="right">
                  <template #default="{ row }">
                    <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct == null ? '-' : ((row.change_pct >= 0 ? '+' : '') + row.change_pct + '%') }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="原因" min-width="140">
                  <template #default="{ row }">{{ (row.reason || '').slice(0, 20) }}</template>
                </el-table-column>
              </el-table>
              <el-empty v-if="!arr(rpt.limit_analysis?.dragon_tiger).length" description="当日龙虎榜数据为空（收盘后才发布）" :image-size="50" />
              <div v-if="seats.length" class="mt8" style="border-top:1px dashed #f0f0f0;padding-top:6px">
                <div class="fs12 bold" style="color:#e6a23c">席位游资（{{ seats.length }}条，按净值）</div>
                <div v-for="s in seats" :key="s.seat + s.symbol" class="seat-row">
                  <el-tag v-if="s.tag" size="small" type="warning" effect="plain">{{ s.tag }}</el-tag>
                  <el-tag v-else size="small" type="info" effect="plain">营业部</el-tag>
                  <el-link type="primary" :underline="false" @click="goStock(s.symbol, s.stock_name)">{{ s.stock_name }}</el-link>
                  <span class="mono fs12" :class="(s.net||0) >= 0 ? 'up' : 'down'">{{ fmtBig(s.net) }}</span>
                  <span class="fs11" style="color:#909399;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ s.seat_name }}</span>
                </div>
              </div>
            </div>
            <div class="card mt8">
              <div class="fs14 bold">次日选股池（{{ arr(rpt.stock_pool).length }}）</div>
              <el-table :data="arr(rpt.stock_pool)" size="small" class="mt8" @row-click="(row) => goStock(row.symbol, row.name)">
                <el-table-column prop="symbol" label="代码" width="95" />
                <el-table-column prop="name" label="名称" width="90" />
                <el-table-column label="涨幅" width="75" align="right">
                  <template #default="{ row }">
                    <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">
                      {{ (row.change_pct||0) >= 0 ? '+' : '' }}{{ row.change_pct || '-' }}%
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="价格" width="70" align="right">
                  <template #default="{ row }">{{ row.price || '-' }}</template>
                </el-table-column>
                <el-table-column label="表现" min-width="100">
                  <template #default="{ row }">{{ row.performance || row.reason || '-' }}</template>
                </el-table-column>
                <el-table-column label="建议" min-width="120">
                  <template #default="{ row }">
                    <el-tag size="small" :type="(row.suggestion||'').includes('关注') ? 'warning' : 'info'">
                      {{ row.suggestion || '关注' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="!arr(rpt.stock_pool).length" description="暂无选股池" :image-size="50" />
            </div>
          </el-col>
        </el-row>

        <!-- 投资日历（未来45天 解禁 / 分红除权） -->
        <el-row :gutter="10" class="mt8">
          <el-col :span="24">
            <div class="card">
              <div class="flex between" style="align-items:center">
                <span class="fs14 bold">投资日历 <span class="fs12" style="color:#909399">（未来45天 解禁 / 分红除权）</span></span>
                <el-button size="small" :loading="calLoading" @click="loadCalendar">刷新</el-button>
              </div>
              <div class="split-grid mt8">
                <div class="cal-scroll">
                  <div class="fs12 bold" style="color:#f56c6c;margin:2px 0">🛡 限售解禁 <span class="fs11" style="color:#909399">（{{ calendar.unlocks.length }}笔，TOP解禁市值）</span></div>
                  <div v-for="(u, i) in topUnlocks" :key="'u' + i" class="cal-row">
                    <span class="cal-date">{{ (u.date || '').slice(5) }}</span>
                    <el-link v-if="u.symbol" class="cal-name" type="danger" :underline="false" @click="goStock(u.symbol, u.name)">{{ u.name }}</el-link>
                    <span v-else class="fs12 cal-name">{{ u.name }}</span>
                    <span class="cal-val mono fs12" style="color:#f56c6c">{{ u.market_cap_yi }}亿</span>
                    <span class="cal-sub">{{ u.type }}</span>
                  </div>
                  <el-empty v-if="!topUnlocks.length" description="未来45天无解禁" :image-size="30" />
                </div>
                <div class="cal-scroll">
                  <div class="fs12 bold" style="color:#67c23a;margin:2px 0">💰 分红除权 <span class="fs11" style="color:#909399">（{{ calendar.dividends.length }}笔）</span></div>
                  <div v-for="(d, i) in topDividends" :key="'d' + i" class="cal-row">
                    <span class="cal-date">{{ (d.date || '').slice(5) }}</span>
                    <el-link v-if="d.symbol" class="cal-name" type="success" :underline="false" @click="goStock(d.symbol, d.name)">{{ d.name }}</el-link>
                    <span v-else class="fs12 cal-name">{{ d.name }}</span>
                    <span class="cal-val mono fs12" style="color:#67c23a">{{ (d.record_date || '').slice(5) }}除权</span>
                    <span class="cal-sub">{{ d.plan }}</span>
                  </div>
                  <el-empty v-if="!topDividends.length" description="未来45天无分红除权" :image-size="30" />
                </div>
              </div>
            </div>
          </el-col>
        </el-row>

        <el-row :gutter="10" class="mt8">
          <el-col v-for="(rv, at) in (rpt.agent_reviews || {})" :key="at" :xs="24" :sm="8">
            <div class="card">
              <el-tag size="small" :type="tagType(at)">{{ at }}</el-tag>
              <div class="fs12 mt8" style="line-height:1.9;white-space:pre-wrap">{{ rv.summary || rv.raw_output || '(' + JSON.stringify(rv).slice(0, 400) + ')' }}</div>
            </div>
          </el-col>
        </el-row>
      </template>

      <el-empty v-else :description="(status === 'empty' && report?.message) || '暂无复盘报告，点击「生成复盘」手动触发（默认交易日 18:00 自动生成）'" />

      <el-dialog v-model="mdDialog" title="复盘报告原文" width="700">
        <pre class="md">{{ report?.report_md }}</pre>
      </el-dialog>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import MainLayout from '../layout/MainLayout.vue'
import { replayApi, marketApi } from '../api'

const router = useRouter()
const loading = ref(false)
const triggering = ref(false)
const report = ref(null)
const triggerDate = ref('')
const viewDate = ref('')
const historyDates = ref([])
const mdDialog = ref(false)
const calendar = ref({ date: '', unlocks: [], dividends: [] })
const calLoading = ref(false)
const seats = ref([])
const topUnlocks = computed(() => [...(calendar.value.unlocks || [])]
  .sort((a, b) => b.market_cap_yi - a.market_cap_yi).slice(0, 6))
const topDividends = computed(() => [...(calendar.value.dividends || [])]
  .sort((a, b) => (a.date || '').localeCompare(b.date || '')).slice(0, 6))

async function loadCalendar() {
  calLoading.value = true
  try { calendar.value = (await marketApi.investCalendar()) || { date: '', unlocks: [], dividends: [] } } catch { /* 保留旧数据 */ }
  calLoading.value = false
}

async function loadSeats() {
  const d = rpt.value?.date
  if (!d) { seats.value = []; return }
  try {
    const rows = (await marketApi.dragonTigerSeats(d)) || []
    seats.value = rows.sort((a, b) => Math.abs(b.net || 0) - Math.abs(a.net || 0)).slice(0, 10)
  } catch { seats.value = [] }
}

const rpt = computed(() => {
  const v = report.value
  if (!v) return null
  if (v.status === 'ready' || v.status === 'pending') return v.data || null
  return null
})
const status = computed(() => report.value?.status || '')

function toAsiaShanghai() {
  return new Date(Date.now() + 8 * 3600 * 1000 - new Date().getTimezoneOffset() * 60000)
}
function isWeekday(d) {
  const w = d.getUTCDay()
  return w >= 1 && w <= 5
}
const prevTradingDate = computed(() => {
  const d = toAsiaShanghai()
  d.setUTCDate(d.getUTCDate() - 1)
  while (!isWeekday(d)) d.setUTCDate(d.getUTCDate() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})

function goStock(symbol, name) {
  if (!symbol) return
  try {
    const list = JSON.parse(localStorage.getItem('recent_viewed') || '[]')
    const filtered = list.filter(r => r.symbol !== symbol)
    filtered.unshift({ symbol, name: name || symbol, ts: Date.now() })
    localStorage.setItem('recent_viewed', JSON.stringify(filtered.slice(0, 30)))
  } catch {}
  router.push({ path: '/watchlist', query: { symbol } })
}

function dateStr(backDays) {
  const d = new Date(Date.now() - backDays * 86400000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function fmtBig(v) {
  if (v == null) return '-'
  const n = Number(v)
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(0)
}
const emLimited = computed(() =>
  !arr(rpt.value?.sector_flow).length
)
function tagType(at) {
  return at === 'research' ? 'primary' : at === 'short_term' ? 'danger' : 'success'
}
function arr(v) {
  return Array.isArray(v) ? v : []
}
const sortedLadder = computed(() => {
  const raw = rpt.value?.limit_analysis?.ladder || {}
  const entries = raw && typeof raw === 'object' && !Array.isArray(raw) && raw.ladder && typeof raw.ladder === 'object'
    ? raw.ladder
    : raw
  const sorted = Object.entries(entries).sort((a, b) => Number(b[0]) - Number(a[0]))
  return Object.fromEntries(sorted)
})
const maxBoard = computed(() => {
  const keys = Object.keys(sortedLadder.value)
  return keys.length ? Math.max(...keys.map(Number)) : 0
})

async function loadHistory() {
  try {
    const rows = (await replayApi.history()) || []
    const dates = (Array.isArray(rows) ? rows : []).map((r) => r.date || '').filter(Boolean)
    historyDates.value = [...new Set(dates)]
  } catch {
    historyDates.value = []
  }
}

async function viewReport(d) {
  if (!d) return
  try {
    const data = await replayApi.byDate(d)
    if (data) {
      report.value = { status: 'ready', date: d, data }
      viewDate.value = d
      await loadSeats()
    } else {
      report.value = { status: 'empty', date: d, message: '该日期暂无复盘记录，可用底部「生成复盘」为该日期生成' }
      viewDate.value = d
    }
  } catch {
    report.value = { status: 'gated', date: d, message: '加载失败，请检查后端服务' }
    viewDate.value = d
  }
}

async function load() {
  loading.value = true
  try {
    report.value = await replayApi.latest()
    const d = rpt.value?.date || report.value?.date
    if (d) viewDate.value = d
    await loadSeats()
    await loadHistory()
  } catch {
    report.value = null
  } finally {
    loading.value = false
  }
}

async function trigger() {
  triggering.value = true
  try {
    const resp = await replayApi.trigger({ date: triggerDate.value || undefined })
    await loadHistory()
    if (resp?.status === 'success' && resp?.date) viewReport(resp.date)
    else await load()
  } finally {
    triggering.value = false
  }
}

onMounted(() => {
  triggerDate.value = dateStr(0)
  load()
  loadCalendar()
})
</script>

<style scoped>
.md {
  font-family: Consolas, 'Microsoft YaHei', monospace;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  background: #f8f9fa;
  padding: 12px;
  border-radius: 6px;
  max-height: 70vh;
  overflow: auto;
}
.ladder-group {
  padding: 6px 0;
  border-bottom: 1px dashed #f0f0f0;
}
.ladder-header {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}
.ladder-stocks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.split-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.cal-scroll { max-height: 260px; overflow: auto; }
.cal-row { display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px dashed #f5f5f5; }
.cal-date { color: #c0c4cc; font-size: 11px; flex-shrink: 0; width: 42px; }
.cal-name { flex-shrink: 0; }
.cal-val { flex-shrink: 0; }
.cal-sub { flex: 1; min-width: 0; text-align: right; color: #909399; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.seat-row { display: flex; align-items: center; gap: 5px; padding: 3px 0; border-bottom: 1px dashed #f5f5f5; font-size: 12px; }

/* H5 移动端适配：单列堆叠 + 表格横滚 + 梯队换行 */
@media (max-width: 820px) {
  .page { padding: 8px; }
  .card { padding: 10px; }
  .card .el-table { width: 100%; }
  .split-grid { grid-template-columns: 1fr; }
  .ladder-stocks { justify-content: flex-start; }
  .ladder-header { flex-wrap: wrap; row-gap: 4px; }
  .fs14 { font-size: 13px; }
  .cal-scroll { max-height: 180px; }
}
@media (max-width: 480px) {
  .card { padding: 8px; }
  .card .el-table { font-size: 11px; }
  .ladder-stocks .el-link { margin-right: 6px; margin-bottom: 4px; }
  .seat-row { flex-wrap: wrap; }
  .mono, .fs12 { font-size: 11px; }
}

/* H5 deepen: 复盘游资工具手感 */
@media (max-width: 820px) {
  .ladder-stocks { display: flex; gap: 4px; flex-wrap: wrap; }
  .ladder-link { color: #409eff; }
  .seat-row { display: flex; align-items: center; gap: 6px; flex-wrap: nowrap; overflow-x: auto; }
  .dragon-row { overflow-x: auto; white-space: nowrap; }
}
@media (max-width: 480px) {
  .card { padding: 10px; }
  .card .fs14 { font-size: 13px; }
  .el-table { font-size: 11px; }
  .mt8 .el-tag { margin: 2px; }
}

/* 连板梯队横滚提示：右侧渐隐遮罩暗示可滑动（移动端游资可每天横向扫板） */
.ladder-scroller { position: relative; }
.ladder-scroller::after {
  content: ''; position: absolute; top: 0; right: 0; bottom: 0; width: 28px;
  background: linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.9) 100%);
  pointer-events: none;
}
.ladder-scroller::-webkit-scrollbar { height: 4px; }
.ladder-scroller::-webkit-scrollbar-thumb { background: #f7b32b; border-radius: 2px; }
</style>