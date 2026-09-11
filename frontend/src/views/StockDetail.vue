<template>
  <MainLayout>
    <div class="page" v-loading="loading">
      <div class="flex gap" style="align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <el-button size="small" @click="goBack"><el-icon><Back /></el-icon></el-button>
        <h2 style="font-size:18px">{{ basic.name || symbol }}</h2>
        <span class="fs12" style="color:#909399">{{ symbol }}</span>
        <span v-if="realtime" class="fs18 bold mono" :class="cls(realtime.change_pct)">
          {{ fmt(realtime.price) }}
          <span class="fs12">{{ realtime.change_pct >= 0 ? '+' : '' }}{{ realtime.change }} / {{ realtime.change_pct >= 0 ? '+' : '' }}{{ realtime.change_pct }}%</span>
        </span>
        <el-tag size="small" type="info">{{ basic.industry }}</el-tag>
        <div style="flex:1"></div>
        <el-radio-group v-model="period" size="small">
          <el-radio-button value="mf">分时</el-radio-button>
          <el-radio-button value="m5">5分</el-radio-button>
          <el-radio-button value="m15">15分</el-radio-button>
          <el-radio-button value="m30">30分</el-radio-button>
          <el-radio-button value="m60">60分</el-radio-button>
          <el-radio-button value="day">日K</el-radio-button>
          <el-radio-button value="week">周K</el-radio-button>
          <el-radio-button value="month">月K</el-radio-button>
        </el-radio-group>
        <el-button size="small" type="primary" :loading="aiLoading" @click="runAI">AI 分析</el-button>
      </div>

      <el-row :gutter="10">
        <el-col :xs="24" :sm="16">
          <div class="card">
            <div v-if="period !== 'mf'">
              <KlineChart :data="kline" :height="'380px'" title="K线图"
                :fx="period === 'day' ? czsc.fx_list : []"
                :bi="period === 'day' ? czsc.bi_list : []"
                :zs="period === 'day' ? czsc.zs_list : []"
                :signals="period === 'day' ? czsc.signals : []"
                :stage-points="period === 'day' ? (czsc.stage_points || []) : []" />
              <el-empty v-if="!kline.length" description="暂无该周期K线（数据源受限）" :image-size="60" />
            </div>
            <div v-else>
              <div class="fs14 bold">分时图</div>
              <LineChart :data="intraday" :height="'360px'" :volume="true" />
              <el-empty v-if="!intraday.length" description="暂无分时数据" :image-size="60" />
            </div>
          </div>
          <div class="card mt8">
            <div class="flex gap" style="align-items:center;flex-wrap:wrap">
              <span class="fs14 bold">技术标签</span>
              <el-tag size="small" :type="ratingTag">{{ ratingText }}</el-tag>
              <span class="fs12" style="color:#909399">由日K/资金流/缠论信号自动识别（真实行情）</span>
            </div>
            <div class="mt8">
              <el-tag v-for="t in techTags" :key="t.value + t.label" size="small" effect="plain" :type="t.type" style="margin:3px 6px 3px 0">{{ t.value }}</el-tag>
              <el-empty v-if="!techTags.length" description="暂无足够日K数据" :image-size="45" />
            </div>
          </div>
<div class="card mt8">
            <div class="fs14 bold">缠论信号（{{ czsc.multi?.length ? '多周期综合' : '日线' }}）</div>
            <div v-if="czsc.fx_list?.length" class="fs12" style="line-height:1.8">
              <el-tag v-for="fx in recentFx" :key="fx.dt" size="small" :type="fx.mark === 'g' ? 'danger' : 'success'" style="margin:2px">
                {{ fx.dt }} {{ fx.type }} {{ fx.price }}
              </el-tag>
            </div>
            <el-empty v-else description="暂无缠论信号" :image-size="50" />
          </div>
          <div class="card mt8">
            <div class="fs14 bold">消息面</div>
            <div v-if="news.length" class="mt8" style="max-height:340px;overflow:auto">
              <div v-for="n in news" :key="n.url" class="fs12 mb6" style="line-height:1.5">
                <el-tag :type="n.sentiment === 'good' ? 'danger' : n.sentiment === 'bad' ? 'success' : 'info'" size="small" style="margin-right:4px">
                  {{ n.sentiment === 'good' ? '利好' : n.sentiment === 'bad' ? '利空' : '中性' }}
                </el-tag>
                <el-tooltip :content="n.title" placement="top">
                  <a :href="n.url" target="_blank" rel="noreferrer" style="color:#409eff;text-decoration:none">{{ n.title }}</a>
                </el-tooltip>
                <div class="mt2" style="color:#909399">{{ n.time }}<span v-if="n.matched"> · 命中「{{ n.matched }}」</span></div>
              </div>
            </div>
            <el-empty v-else description="暂无相关个股新闻" :image-size="50" />
          </div>
        </el-col>

        <el-col :xs="24" :sm="8">
          <div class="card">
            <div class="fs14 bold">AI 分析</div>
            <div v-if="aiResult" class="mt8">
              <div class="flex gap mb8">
                <el-tag :type="aiRiskTag" size="small">风险 {{ aiResult.risk_level }}</el-tag>
                <el-tag type="info" size="small">置信度 {{ (aiResult.confidence * 100).toFixed(0) }}%</el-tag>
              </div>
              <div class="fs12" style="white-space:pre-wrap;line-height:1.8">{{ aiResult.summary }}</div>
              <el-divider v-if="aiResult.signals?.length || aiResult.watch_list?.length" style="margin:8px 0" />
              <div v-if="aiResult.watch_list?.length" class="fs12 mt8">
                <div class="bold">关注列表</div>
                <div v-for="(w, i) in aiResult.watch_list" :key="i" class="mt4">
                  · {{ w.symbol }} — {{ w.reason }}
                </div>
              </div>
              <div v-if="aiResult.signals?.length" class="fs12 mt8">
                <div class="bold">信号</div>
                <div v-for="(s, i) in aiResult.signals" :key="i" class="mt4 fs12">
                  · [{{ s.type }}] {{ s.condition }}
                </div>
              </div>
            </div>
            <el-empty v-else description="点击「AI 分析」解读该股（未配置 API Key 时使用本地启发式分析）" :image-size="70" />
          </div>
        </el-col>
      </el-row>

      <el-card shadow="never" class="mt8">
        <el-tabs v-model="tab">
          <el-tab-pane label="技术形态" name="forms">
            <el-table :data="forms" size="small">
              <el-table-column prop="name" label="形态" width="180" />
              <el-table-column label="信号" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.level === 'bullish' ? 'success' : row.level === 'bearish' ? 'danger' : 'info'">{{ row.level }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="desc" label="说明" />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="财务数据" name="fin">
            <div class="fs12 mb8" style="color:#909399">近{{ financial.length || '各' }}个报告期：东方财富季度财报 营收/净利/盈利质量，最新一期含毛利率、每股经营现金流、分红方案</div>
            <el-table :data="financial" size="small">
              <el-table-column prop="report_date" label="报告期" width="92" />
              <el-table-column prop="revenue" label="营收" width="100" align="right"><template #default="{ row }">{{ fmtBig(row.revenue) }}</template></el-table-column>
              <el-table-column prop="revenue_yoy" label="营收同比" width="82" align="right"><template #default="{ row }"><span :class="cls(row.revenue_yoy)">{{ row.revenue_yoy == null ? '-' : row.revenue_yoy + '%' }}</span></template></el-table-column>
              <el-table-column prop="net_profit" label="净利润" width="100" align="right"><template #default="{ row }">{{ fmtBig(row.net_profit) }}</template></el-table-column>
              <el-table-column prop="net_profit_yoy" label="净利同比" width="82" align="right"><template #default="{ row }"><span :class="cls(row.net_profit_yoy)">{{ row.net_profit_yoy == null ? '-' : row.net_profit_yoy + '%' }}</span></template></el-table-column>
              <el-table-column prop="gross_margin" label="毛利率" width="70" align="right"><template #default="{ row }">{{ row.gross_margin == null ? '-' : row.gross_margin + '%' }}</template></el-table-column>
              <el-table-column prop="roe" label="ROE(W)" width="78" align="right"><template #default="{ row }">{{ row.roe == null ? '-' : row.roe + '%' }}</template></el-table-column>
              <el-table-column prop="eps" label="EPS" width="70" align="right"><template #default="{ row }">{{ row.eps ?? '-' }}</template></el-table-column>
              <el-table-column prop="bps" label="每股净资产" width="90" align="right"><template #default="{ row }">{{ row.bps ?? '-' }}</template></el-table-column>
              <el-table-column prop="ocf_per_share" label="每股经营现金流" width="110" align="right"><template #default="{ row }">{{ row.ocf_per_share ?? '-' }}</template></el-table-column>
              <el-table-column prop="assign" label="分红方案" min-width="120"><template #default="{ row }">{{ row.assign || '-' }}</template></el-table-column>
            </el-table>
            <div class="fs11 mt8" style="color:#909399">ROE(W)为加权平均净资产收益率；EPS为基本每股收益；每股经营现金流可判断盈利含金量，长期为负需警惕。</div>
            <el-empty v-if="!financial.length" description="财务数据源在本机网络受限（东方财富），暂无数据" :image-size="60" />
          </el-tab-pane>

          <el-tab-pane label="资金流向" name="flow">
            <div v-if="flowSummary" class="flex gap mb8" style="flex-wrap:wrap">
              <el-tag :type="n(flowSummary.net_1d) >= 0 ? 'danger' : 'success'" effect="plain">1日主力 {{ fmtBig(absToYuan(flowSummary.net_1d)) }}</el-tag>
              <el-tag :type="n(flowSummary.net_5d) >= 0 ? 'danger' : 'success'" effect="plain">5日主力 {{ fmtBig(absToYuan(flowSummary.net_5d)) }}</el-tag>
              <el-tag :type="n(flowSummary.net_20d) >= 0 ? 'danger' : 'success'" effect="plain">20日主力 {{ fmtBig(absToYuan(flowSummary.net_20d)) }}</el-tag>
              <el-tag type="info" effect="plain">趋势 {{ flowSummary.trend === 'inflow' ? '持续流入' : flowSummary.trend === 'outflow' ? '持续流出' : '反复' }}</el-tag>
              <el-tag type="info" effect="plain" v-if="flowSummary.latest_date">截至 {{ flowSummary.latest_date }}</el-tag>
            </div>
            <div class="mb8">
              <div class="fs12 mb8" style="color:#909399">近{{ moneyFlow.length || '' }}个交易日主力当日净流入（单位：万元）</div>
              <LineChart v-if="moneyFlow.length"
                :data="moneyFlow.map(m => ({ name: String(m.date).slice(5), value: Math.round((Number(m.netamount) || 0) / 1e4) }))"
                height="200px" :area="false" :colors="['#ef232a']" />
            </div>
            <el-table :data="moneyFlow" size="small">
              <el-table-column prop="date" label="日期" width="110" />
              <el-table-column label="主力当日净流入(元)" align="right"><template #default="{ row }"><span :class="cls(row.netamount)">{{ fmtBig(row.netamount) }}</span></template></el-table-column>
              <el-table-column prop="net_5d" label="5日累计(亿)" align="right"><template #default="{ row }"><span :class="cls(row.net_5d)">{{ row.net_5d }}</span></template></el-table-column>
              <el-table-column prop="net_20d" label="20日累计(亿)" align="right"><template #default="{ row }"><span :class="cls(row.net_20d)">{{ row.net_20d }}</span></template></el-table-column>
            </el-table>
            <el-empty v-if="!moneyFlow.length" description="个股资金流数据源在本机网络受限，暂无数据" :image-size="60" />
          </el-tab-pane>

          <el-tab-pane label="行业对比" name="rank">
            <div v-if="industryRanking?.available" class="mb8">
              <div class="fs13 bold mb8">行业：{{ industryRanking.industry }}（同行业 {{ industryRanking.peers_count }} 家 · 东方财富季度财报）</div>
              <el-descriptions :column="4" size="small" border class="mb8">
                <el-descriptions-item label="净利增速排名">
                  {{ industryRanking.target?.rank_by_growth ?? '-' }} / {{ industryRanking.target?.total_by_growth ?? '-' }}
                </el-descriptions-item>
                <el-descriptions-item label="ROE排名">
                  {{ industryRanking.target?.rank_by_roe ?? '-' }} / {{ industryRanking.target?.total_by_roe ?? '-' }}
                </el-descriptions-item>
                <el-descriptions-item label="行业净利增速中位数">
                  <span :class="cls(industryRanking.median_growth)">{{ industryRanking.median_growth == null ? '-' : industryRanking.median_growth + '%' }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="行业ROE中位数">
                  <span :class="cls(industryRanking.median_roe)">{{ industryRanking.median_roe == null ? '-' : industryRanking.median_roe + '%' }}</span>
                </el-descriptions-item>
              </el-descriptions>
              <div class="fs12 bold mb4">同行净利增速 TOP8</div>
              <el-table :data="industryRanking.top_growth || []" size="small" @row-click="(r) => goStock2(r.code)">
                <el-table-column prop="name" label="名称" width="110" />
                <el-table-column prop="code" label="代码" width="90" />
                <el-table-column prop="net_profit_yoy" label="净利同比%" align="right"><template #default="{ row }"><span :class="cls(row.net_profit_yoy)">{{ row.net_profit_yoy }}%</span></template></el-table-column>
                <el-table-column prop="revenue_yoy" label="营收同比%" align="right"><template #default="{ row }"><span :class="cls(row.revenue_yoy)">{{ row.revenue_yoy }}%</span></template></el-table-column>
                <el-table-column prop="roe" label="ROE%" align="right" />
              </el-table>
              <div class="fs12 bold mb4 mt8">同行 ROE TOP8</div>
              <el-table :data="industryRanking.top_roe || []" size="small" @row-click="(r) => goStock2(r.code)">
                <el-table-column prop="name" label="名称" width="110" />
                <el-table-column prop="code" label="代码" width="90" />
                <el-table-column prop="roe" label="ROE%" align="right" width="90"><template #default="{ row }"><span :class="cls(row.roe)">{{ row.roe }}%</span></template></el-table-column>
                <el-table-column prop="net_profit_yoy" label="净利同比%" align="right"><template #default="{ row }"><span :class="cls(row.net_profit_yoy)">{{ row.net_profit_yoy }}%</span></template></el-table-column>
                <el-table-column prop="revenue_yoy" label="营收同比%" align="right" />
              </el-table>
            </div>
            <el-empty v-else description="行业对比数据不可用（东方财富网络受限）" :image-size="60" />
          </el-tab-pane>

          <el-tab-pane label="产业链" name="chain">
            <div v-if="industryChain?.industry" class="mb8">
              <div class="fs13 bold mb4">{{ industryChain.industry.name }}（{{ industryChain.industry.code }}）</div>
              <div class="fs12">
                <el-tag size="small" :type="n(industryChain.industry.change_pct) >= 0 ? 'danger' : 'success'">
                  {{ industryChain.industry.change_pct == null ? '-' : (n(industryChain.industry.change_pct) >= 0 ? '+' : '') + industryChain.industry.change_pct + '%' }}
                </el-tag>
                主力净流入 <b :class="cls(industryChain.industry.net_inflow)">{{ industryChain.industry.net_inflow ?? '-' }}亿</b>
                · 净占比 {{ industryChain.industry.net_ratio ?? '-' }}% · 成交 {{ industryChain.industry.amount ?? '-' }}亿
                · 领涨 <el-link v-if="industryChain.industry.leader_symbol" type="primary" :underline="false" style="font-size:12px"
                    @click="goStock2(industryChain.industry.leader_symbol)">{{ industryChain.industry.leader }}</el-link>
                  <span v-else>{{ industryChain.industry.leader || '-' }}</span>
              </div>
            </div>
            <div v-if="(industryChain?.peers || []).length">
              <div class="fs12 bold mb4 mt8">板块市值 TOP10（市值龙头/龙二/龙三）</div>
              <el-table :data="industryChain.peers" size="small" @row-click="(r) => goStock2(r.symbol)">
                <el-table-column prop="name" label="名称" width="90" />
                <el-table-column prop="symbol" label="代码" width="88" />
                <el-table-column label="角色" width="70"><template #default="{ row }"><el-tag :type="row.role === '市值龙头' ? 'danger' : row.role === '龙二' ? 'warning' : 'info'" size="small">{{ row.role || '-' }}</el-tag></template></el-table-column>
                <el-table-column label="市值(亿)" align="right" width="80"><template #default="{ row }">{{ row.mkt_cap }}</template></el-table-column>
                <el-table-column label="涨幅%" align="right" width="70"><template #default="{ row }"><span :class="cls(row.change_pct)">{{ n(row.change_pct) >= 0 ? '+' : '' }}{{ row.change_pct }}%</span></template></el-table-column>
                <el-table-column label="主力净(亿)" align="right" width="85"><template #default="{ row }"><span :class="cls(row.net_inflow)">{{ row.net_inflow ?? '-' }}</span></template></el-table-column>
                <el-table-column prop="turnover" label="换手%" align="right" width="70" />
              </el-table>
            </div>
            <div v-if="(industryChain?.concepts || []).length">
              <div class="fs12 bold mb4 mt8">所属概念板块（{{ industryChain.concepts.length }}）</div>
              <div class="concept-grid">
                <div v-for="c in industryChain.concepts" :key="c.code" class="concept-item">
                  <span class="fs12 bold">{{ c.name }}</span>
                  <div class="fs12 mt4">
                    <el-tag size="small" :type="n(c.change_pct) >= 0 ? 'danger' : 'success'">{{ c.change_pct == null ? '-' : (n(c.change_pct) >= 0 ? '+' : '') + c.change_pct + '%' }}</el-tag>
                    <span class="ml4">主力 <b :class="cls(c.net_inflow)">{{ c.net_inflow ?? '-' }}亿</b></span>
                    <el-link v-if="c.leader_symbol" type="primary" :underline="false" style="font-size:12px;margin-left:4px" @click="goStock2(c.leader_symbol)">{{ c.leader }}</el-link>
                  </div>
                </div>
              </div>
            </div>
            <el-empty v-if="!industryChain?.industry && !(industryChain?.concepts || []).length" description="产业链数据不可用（东方财富网络受限）" :image-size="60" />
          </el-tab-pane>

          <el-tab-pane label="股东结构" name="holders">
            <div class="fs12 mb8" style="color:#909399">十大股东持仓及较上期增减（真实股东名录）</div>
            <el-table :data="shareholders" size="small">
              <el-table-column prop="holder_name" label="股东" min-width="140" />
              <el-table-column prop="hold_count" label="持股数" align="right"><template #default="{ row }">{{ fmtInt(row.hold_count) }}</template></el-table-column>
              <el-table-column prop="hold_ratio" label="占比%" align="right" />
              <el-table-column prop="change_count" label="较上期增减" align="right"><template #default="{ row }"><span :class="cls(row.change_count)">{{ fmtInt(row.change_count) }}</span></template></el-table-column>
              <el-table-column prop="report_date" label="报告期" width="110" />
            </el-table>
            <el-empty v-if="!shareholders.length" description="股东数据源在本机网络受限，暂无数据" :image-size="60" />
          </el-tab-pane>

          <el-tab-pane label="所属板块" name="sector">
            <div v-if="sector.industry" class="mb8">
              <span class="fs13 bold">行业：</span>
              <el-tag type="warning">{{ sector.industry }}</el-tag>
              <span v-if="sector.changes?.industry" class="fs12 ml4" :class="cls(sector.changes.industry.change_pct)">（{{ n(sector.changes.industry.change_pct) >= 0 ? '+' : '' }}{{ sector.changes.industry.change_pct }}% · 领涨 {{ sector.changes.industry.leader }}）</span>
              <span v-else class="fs12 ml4" style="color:#909399">（未收录实时板块行情）</span>
            </div>
            <div v-if="(sector.concepts || []).length">
              <span class="fs13 bold">概念：</span>
              <div v-for="c in sector.concepts" :key="c" class="mt4">
                <el-tag style="margin:3px">{{ c }}</el-tag>
                <span v-if="sector.changes?.concepts" class="fs12 ml4">
                  <template v-for="cc in sector.changes.concepts" :key="cc.name">
                    <span v-if="cc.name === c" :class="cls(cc.change_pct)">（{{ n(cc.change_pct) >= 0 ? '+' : '' }}{{ cc.change_pct }}% · 领涨 {{ cc.leader }}）</span>
                  </template>
                </span>
              </div>
            </div>
            <el-empty v-if="!sector.concepts?.length && !sector.industry" description="暂无板块信息" :image-size="50" />
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MainLayout from '../layout/MainLayout.vue'
import KlineChart from '../components/KlineChart.vue'
import LineChart from '../components/LineChart.vue'
import { stockApi, agentApi, marketApi } from '../api'

const route = useRoute()
const router = useRouter()
const symbol = route.params.symbol

const loading = ref(false)
const VALID_PERIODS = ['mf', 'm5', 'm15', 'm30', 'm60', 'day', 'week', 'month']
const period = ref('day')
const tab = ref('forms')
const basic = ref({})
const realtime = ref(null)
const kline = ref([])
const intraday = ref([])
const czsc = ref({})
const forms = ref([])
const financial = ref([])
const moneyFlow = ref([])
const flowSummary = ref(null)
const news = ref([])
const shareholders = ref([])
const sentiment = ref({})
const sector = ref({})
const industryRanking = ref(null)
const industryChain = ref(null)
const aiResult = ref(null)
const aiLoading = ref(false)

const aiRiskTag = computed(() => (aiResult.value?.risk_level === 'high' ? 'danger' : aiResult.value?.risk_level === 'medium' ? 'warning' : 'success'))

const recentFx = computed(() => (czsc.value.fx_list || []).slice(-10))

const techKlines = ref([])
const techTags = computed(() => {
  const tags = []
  const ks = techKlines.value
  if (ks.length < 30) return tags
  const closes = ks.map((k) => Number(k.close))
  const c = closes[closes.length - 1]
  const ma = (n) => {
    const seg = closes.slice(-n)
    return seg.reduce((a, b) => a + b, 0) / seg.length
  }
  const ma5 = ma(5)
  const ma10 = ma(10)
  const ma20 = ma(20)
  const prevMa5 = closes.slice(-6, -1).reduce((a, b) => a + b, 0) / 5
  const prevMa10 = closes.slice(-11, -1).reduce((a, b) => a + b, 0) / 10

  if (ma5 > ma10 && ma10 > ma20) tags.push({ type: 'danger', value: '多头排列' })
  if (ma5 < ma10 && ma10 < ma20) tags.push({ type: 'success', value: '空头排列' })
  if (prevMa5 <= prevMa10 && ma5 > ma10) tags.push({ type: 'danger', value: 'MA5上穿MA10' })
  if (prevMa5 >= prevMa10 && ma5 < ma10) tags.push({ type: 'success', value: 'MA5下穿MA10' })
  const before = ks[ks.length - 2]
  if (before && Number(before.close) <= Number(before.ma20 ?? NaN) && c > ma20 && c > Number(before.close)) {
    tags.push({ type: 'danger', value: '出水芙蓉' })
  }
  const highs = closes.slice(-21, -1)
  const lows = closes.slice(-21, -1)
  if (Math.max.apply(null, highs) !== undefined && c >= Math.max.apply(null, highs)) tags.push({ type: 'danger', value: '突破20日新高' })
  if (Math.min.apply(null, lows) !== undefined && c <= Math.min.apply(null, lows)) tags.push({ type: 'success', value: '创20日新低' })

  const vols = ks.map((k) => Number(k.volume || 0))
  const avgVol = vols.slice(-6, -1).reduce((a, b) => a + b, 0) / 5
  const lastChg = (Number(ks[ks.length - 1].close) - Number(before.close)) / Number(before.close)
  if (avgVol > 0 && vols[vols.length - 1] > avgVol * 1.5 && lastChg > 0.02) tags.push({ type: 'danger', value: '放量上攻' })
  if (avgVol > 0 && vols[vols.length - 1] > avgVol * 1.5 && lastChg < -0.02) tags.push({ type: 'success', value: '放量下跌' })

  if (moneyFlow.value.length) {
    const net = Number(moneyFlow.value[0].netamount || 0)
    const net5 = moneyFlow.value.slice(0, 5).reduce((s, r) => s + Number(r.netamount || 0), 0)
    tags.push({ type: net >= 0 ? 'danger' : 'success', value: net >= 0 ? `主力净流入 ${fmtBig(net)}` : `主力净流出 ${fmtBig(Math.abs(net))}` })
    if (net5 >= 0) tags.push({ type: 'danger', value: '近5日主力吸筹' })
    else tags.push({ type: 'success', value: '近5日主力派发' })
  }

  const sigs = czsc.value.signals || []
  if (sigs.length) {
    const last = sigs[sigs.length - 1]
    if (String(last.mark || last.type || '').startsWith('b')) tags.push({ type: 'danger', value: `缠论买点 ${last.dt}` })
    if (String(last.mark || last.type || '').startsWith('s')) tags.push({ type: 'success', value: `缠论卖点 ${last.dt}` })
  }
  return tags
})
const bullCount = computed(() => techTags.value.filter((t) => t.type === 'danger').length)
const bearCount = computed(() => techTags.value.filter((t) => t.type === 'success').length)
const ratingText = computed(() => {
  const b = bullCount.value
  const e = bearCount.value
  if (b > e) return '短线偏强'
  if (b < e) return '短线偏弱'
  return '多空中性'
})
const ratingTag = computed(() => (bullCount.value > bearCount.value ? 'danger' : bullCount.value < bearCount.value ? 'success' : 'info'))

function fmt(v) {
  return v == null ? '-' : Number(v).toFixed(2)
}
function n(v) {
  return Number(v == null ? NaN : v)
}
function cls(v) {
  const n = Number(v)
  return n > 0 ? 'up' : n < 0 ? 'down' : 'flat'
}
function fmtBig(v) {
  if (v == null) return '-'
  const n = Number(v)
  const abs = Math.abs(n)
  if (abs >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (abs >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(0)
}
function absToYuan(v) {
  return n(v) * 1e8
}
function goStock2(code) {
  if (!code) return
  try {
    const list = JSON.parse(localStorage.getItem('recent_viewed') || '[]')
    const filtered = list.filter(r => r.symbol !== code)
    filtered.unshift({ symbol: code, name: '', ts: Date.now() })
    localStorage.setItem('recent_viewed', JSON.stringify(filtered.slice(0, 30)))
  } catch {}
  const sym = String(code).toUpperCase().replace(/^\D+/, '')
  const full = sym.length === 6 ? fullSymbol(sym) : code
  router.push({ path: '/stock/' + full, query: { t: Date.now() } })
}
function fullSymbol(sym) {
  if (sym.startsWith('6') || sym.startsWith('900')) return 'SH' + sym
  if (sym.startsWith('0') || sym.startsWith('3') || sym.startsWith('200')) return 'SZ' + sym
  return 'BJ' + sym
}
function fmtInt(v) {
  return v == null ? '-' : Number(v).toLocaleString()
}
function goBack() {
  router.back()
}

async function load() {
  loading.value = true
  try {
    const [b, c, f, fin, flow, fs, se, nz, holders, sec, rank, chain] = await Promise.all([
      stockApi.basic(symbol),
      stockApi.czsc(symbol),
      stockApi.forms(symbol),
      stockApi.financial(symbol),
      stockApi.moneyFlow(symbol),
      stockApi.moneyFlowSummary(symbol),
      stockApi.sentiment(symbol),
      stockApi.news(symbol),
      stockApi.shareholders(symbol),
      stockApi.sector(symbol),
      stockApi.industryRanking(symbol),
      stockApi.industryChain(symbol)
    ])
    basic.value = b
    realtime.value = b.realtime || null
    czsc.value = c
    forms.value = f
    financial.value = fin
    moneyFlow.value = flow
    flowSummary.value = fs || null
    sentiment.value = se
    news.value = nz || []
    shareholders.value = holders
    sector.value = sec
    industryRanking.value = rank || null
    industryChain.value = chain || null
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function loadKline() {
  try {
    if (period.value === 'mf') {
      intraday.value = await marketApi.intraday({ symbol })
      kline.value = []
      return
    }
    const d = await stockApi.kline(symbol, { period: period.value })
    kline.value = d.data || []
    intraday.value = []
    if (period.value === 'day') techKlines.value = kline.value
  } catch {
    kline.value = []
    intraday.value = []
  }
}

async function runAI() {
  aiLoading.value = true
  aiResult.value = null
  try {
    const r = await agentApi.analyzeStock({ symbol, task: 'analyze_stock' })
    aiResult.value = r || {}
  } catch {
    aiResult.value = null
  } finally {
    aiLoading.value = false
  }
}

watch(period, (v) => { if (VALID_PERIODS.includes(v)) loadKline() })
onMounted(() => {
  load()
  loadKline()
})
</script>