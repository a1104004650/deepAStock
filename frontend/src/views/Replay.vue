<template>
  <MainLayout>
    <div class="page">
      <div class="flex gap" style="align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h2 style="font-size:18px">每日复盘</h2>
        <el-button size="small" type="primary" :loading="loading" @click="load">刷新</el-button>
        <el-select v-model="triggerDate" size="small" style="width:150px;margin-left:8px">
          <el-option v-for="i in 30" :key="i" :label="dateStr(i)" :value="dateStr(i)" />
        </el-select>
        <el-button size="small" :loading="triggering" @click="trigger" :type="status === 'pending' ? 'danger' : 'warning'">生成复盘</el-button>
        <el-tag v-if="status === 'pending'" size="small" type="warning">今日尚未生成，交易日 18:00 自动复盘</el-tag>
        <el-tag v-if="status === 'empty'" size="small" type="info">暂无复盘记录</el-tag>
        <el-tag v-if="rpt?.date" size="small" type="info">{{ rpt.date }}</el-tag>
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
                <el-table-column label="涨停数" align="right" width="64">
                  <template #default="{ row }">{{ row.limit_up_count ?? '-' }}</template>
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
import { replayApi } from '../api'

const router = useRouter()
const loading = ref(false)
const triggering = ref(false)
const report = ref(null)
const triggerDate = ref('')
const mdDialog = ref(false)

const rpt = computed(() => report.value?.status === 'ready' ? (report.value.data || null) : null)
const status = computed(() => report.value?.status || '')

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

async function load() {
  loading.value = true
  try {
    report.value = await replayApi.latest()
  } catch {
    report.value = null
  } finally {
    loading.value = false
  }
}

async function trigger() {
  triggering.value = true
  try {
    await replayApi.trigger({ date: triggerDate.value || undefined })
    await load()
  } finally {
    triggering.value = false
  }
}

onMounted(() => {
  triggerDate.value = dateStr(0)
  load()
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
</style>