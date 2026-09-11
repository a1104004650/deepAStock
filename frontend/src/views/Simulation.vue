<template>
  <MainLayout>
    <div class="page">
      <div class="flex gap" style="align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h2 style="font-size:18px">模拟交易</h2>
        <el-button size="small" type="primary" @click="createDialog = true"><el-icon><Plus /></el-icon>新建账户</el-button>
        <el-button size="small" type="warning" :loading="running" @click="runAll">全部执行当日交易</el-button>
      </div>
      <div class="fs12" style="color:#909399;margin-bottom:8px">
        账户可绑定智能体（投研/短线/波段）自动执行当日交易，不依赖手动点击；系统将在每个交易日 15:10 收盘后自动执行，20:00 自动进化。每个账户提供完整决策日志（选股池 / 观察池 / 逻辑 / 买卖原因 / 每日复盘 / 盈亏统计）。A股按 T+1 规则，当日买入不可当日卖出。
      </div>

      <!-- 透视总览：全部账户一屏对比 + 收益图表 -->
      <el-card shadow="never" v-if="accounts.length" class="mt8">
        <template #header><span class="fs14 bold">透视总览（全部账户）</span></template>
        <el-row :gutter="10">
          <el-col :xs="24" :sm="14">
            <el-table :data="accounts" size="small">
              <el-table-column label="账户" min-width="150">
                <template #default="{ row }">{{ row.name || ('模拟账户 #' + row.id) }}</template>
              </el-table-column>
              <el-table-column label="总资产" align="right"><template #default="{ row }">{{ fmt(row.performance?.current_capital) }}</template></el-table-column>
              <el-table-column label="当日盈亏" align="right"><template #default="{ row }"><span class="mono" :class="pnlCls(row.performance?.today_pnl)">{{ sign(row.performance?.today_pnl) }}{{ fmt(row.performance?.today_pnl) }}</span></template></el-table-column>
              <el-table-column label="持有盈亏" align="right"><template #default="{ row }"><span class="mono" :class="pnlCls(row.performance?.holding_pnl)">{{ sign(row.performance?.holding_pnl) }}{{ fmt(row.performance?.holding_pnl) }}</span></template></el-table-column>
              <el-table-column label="总盈亏" align="right"><template #default="{ row }"><span class="mono" :class="pnlCls(row.performance?.total_pnl)">{{ sign(row.performance?.total_pnl) }}{{ fmt(row.performance?.total_pnl) }}</span></template></el-table-column>
              <el-table-column label="交易次数" align="right"><template #default="{ row }">{{ row.performance?.buy_count ?? 0 }}/{{ row.performance?.sell_count ?? 0 }}</template></el-table-column>
              <el-table-column label="胜率" align="right"><template #default="{ row }">{{ fmtPct(row.performance?.win_rate) }}</template></el-table-column>
              <el-table-column label="做T" align="right"><template #default="{ row }">{{ row.performance?.t_times ?? 0 }}次/{{ fmtPct(row.performance?.t_win_rate) }}</template></el-table-column>
            </el-table>
          </el-col>
          <el-col :xs="24" :sm="10">
            <div class="fs12" style="color:#909399;margin-bottom:4px">账户总收益率 / 当日盈亏对比（红盈绿亏）</div>
            <div ref="barEl" style="height:220px"></div>
          </el-col>
        </el-row>
      </el-card>

      <el-card shadow="never" v-for="acc in accounts" :key="acc.id" class="mt8">
        <template #header>
          <div class="flex between" style="align-items:center">
            <div class="flex gap" style="align-items:center">
              <span>{{ acc.name || '模拟账户 #' + acc.id }}</span>
              <el-tag v-if="acc.agent_type" size="small" type="info">{{ acc.agent_name }}（{{ acc.agent_type }}）</el-tag>
            </div>
            <div class="flex gap">
              <el-button size="small" @click="showLogs(acc)">决策日志</el-button>
              <el-button size="small" type="primary" :loading="runningId === acc.id" @click="runOne(acc.id)">执行当日交易</el-button>
              <el-popconfirm title="重置该账户？将清空持仓/交易/复盘/日志，资金回到初始值" @confirm="resetAcc(acc.id)">
                <template #reference><el-button size="small" type="warning" plain>重置</el-button></template>
              </el-popconfirm>
              <el-popconfirm title="删除该模拟账户？" @confirm="remove(acc.id)">
                <template #reference><el-button size="small" type="danger" plain>删除</el-button></template>
              </el-popconfirm>
            </div>
          </div>
        </template>

        <el-row :gutter="10">
          <el-col :xs="24" :sm="6">
            <div class="fs12" style="color:#909399">总资产</div>
            <div class="fs18 bold mono">{{ fmt(acc.performance?.current_capital ?? acc.initial_capital) }}</div>
            <div class="fs12 mt8">初始资金 {{ fmt(acc.initial_capital) }}</div>
            <div class="fs12 mt8" :class="(acc.performance?.total_return || 0) >= 0 ? 'up' : 'down'">
              总收益率 {{ (acc.performance?.total_return || 0) >= 0 ? '+' : '' }}{{ fmtPct(acc.performance?.total_return) }}
              <span class="mono" :class="pnlCls(acc.performance?.total_pnl)">（{{ sign(acc.performance?.total_pnl) }}{{ fmt(acc.performance?.total_pnl) }}）</span>
            </div>
            <div class="fs12 mt8"><span :class="pnlCls(acc.performance?.today_pnl)">当日盈亏 <b class="mono">{{ sign(acc.performance?.today_pnl) }}{{ fmt(acc.performance?.today_pnl) }}</b></span></div>
            <el-divider />
            <div class="fs12">持有盈亏 <b class="mono" :class="pnlCls(acc.performance?.holding_pnl)">{{ sign(acc.performance?.holding_pnl) }}{{ fmt(acc.performance?.holding_pnl) }}</b></div>
            <div class="fs12">已实现盈亏 <b class="mono" :class="pnlCls(acc.performance?.realized_pnl)">{{ sign(acc.performance?.realized_pnl) }}{{ fmt(acc.performance?.realized_pnl) }}</b></div>
            <div class="fs12">胜率 <b class="mono">{{ fmtPct(acc.performance?.win_rate) }}</b>（{{ acc.performance?.wins ?? 0 }}胜/{{ acc.performance?.losses ?? 0 }}负）</div>
            <div class="fs12">最大回撤 <b class="down mono">{{ fmtPct(acc.performance?.max_drawdown) }}</b></div>
            <div class="fs12">做T <b class="mono">{{ acc.performance?.t_times ?? 0 }}次</b>· 胜率 <b class="mono">{{ fmtPct(acc.performance?.t_win_rate) }}</b></div>
            <div class="fs12">交易笔数 <b class="mono">{{ acc.performance?.total_trades ?? 0 }}</b>（买 {{ acc.performance?.buy_count ?? 0 }} / 卖 {{ acc.performance?.sell_count ?? 0 }}）</div>
          </el-col>

          <el-col :xs="24" :sm="9">
            <div class="fs14 bold mb8">收益曲线</div>
            <LineChart v-if="acc.equity?.length" :data="acc.equity" height="170px" />
            <div v-else class="fs12" style="color:#909399;height:170px;line-height:170px;text-align:center">暂无交易数据</div>
          </el-col>

          <el-col :xs="24" :sm="9">
            <el-tabs v-model="poolTab" class="pool-tabs">
              <el-tab-pane label="持仓池" name="positions">
                <el-table :data="(acc.positions || []).slice(0, 10)" size="small" max-height="250" @row-click="showPosChart">
                  <el-table-column label="名称" min-width="110">
                    <template #default="{ row }"><span class="fs12">{{ row.name || row.symbol }}</span></template>
                  </el-table-column>
                  <el-table-column prop="symbol" label="代码" width="96" />
                  <el-table-column prop="quantity" label="股数" width="72" align="right" />
                  <el-table-column label="盈亏%" align="right">
                    <template #default="{ row }">
                      <span class="mono" :class="pnlCls(pnlPct(row))">{{ pnlPct(row) >= 0 ? '+' : '' }}{{ pnlPct(row).toFixed(2) }}%</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="盈亏" align="right">
                    <template #default="{ row }">
                      <span class="mono" :class="pnlCls(row.unrealized_pnl||0)">{{ sign(row.unrealized_pnl||0) }}{{ fmt(row.unrealized_pnl) }}</span>
                    </template>
                  </el-table-column>
                </el-table>
                <div v-if="!(acc.positions || []).length" class="fs12" style="color:#909399;line-height:50px;text-align:center">暂无持仓</div>
              </el-tab-pane>

              <el-tab-pane label="追踪池" name="tracked">
                <div class="fs12" style="color:#909399;margin-bottom:6px">手动跟踪（AI 买入重点关注，可增删）</div>
                <div class="flex gap">
                  <el-input v-model="trackInput[acc.id]" size="small" placeholder="如：600519" />
                  <el-button size="small" type="primary" @click="addTrack(acc)">添加</el-button>
                </div>
                <div class="tracked-chips mt8">
                  <span v-for="t in (acc.pool?.tracked || [])" :key="(t.symbol || t.name || '') + ''" class="log-chip">
                    {{ t.name || t.symbol }}
                    <el-tag size="small" type="info" style="margin-left:4px">{{ t.symbol }}</el-tag>
                    <el-icon class="chip-close" @click="removeTrack(acc, t)"><Close /></el-icon>
                  </span>
                  <span v-if="!(acc.pool?.tracked || []).length" class="fs12" style="color:#c0c4cc">暂无跟踪标的</span>
                </div>
              </el-tab-pane>

              <el-tab-pane :label="'观察池 ' + poolCount(acc, '观察池')" name="watch">
                <div class="fs12" style="color:#909399;margin-bottom:6px">当日涨停/强势候选（按账户差异化轮转）</div>
                <div class="chip-wrap">
                  <span v-for="p in poolBy(acc, '观察池')" :key="p.symbol" class="log-chip">{{ p.name || p.symbol }}</span>
                  <span v-if="!poolBy(acc, '观察池').length" class="fs12" style="color:#c0c4cc">暂无候选</span>
                </div>
              </el-tab-pane>

              <el-tab-pane :label="'复盘池 ' + poolCount(acc, '复盘池')" name="replay">
                <div class="fs12" style="color:#909399;margin-bottom:6px">最近复盘报告选出的强势标的（{{ poolSourceNote }}）</div>
                <div class="chip-wrap">
                  <span v-for="p in poolBy(acc, '复盘池')" :key="p.symbol" class="log-chip">{{ p.name || p.symbol }}</span>
                  <span v-if="!poolBy(acc, '复盘池').length" class="fs12" style="color:#c0c4cc">暂无候选（运行每日复盘后生成）</span>
                </div>
              </el-tab-pane>
            </el-tabs>
            <div class="fs12 mt8" style="color:#e6a23c">AI 账户禁止买入 ST / *ST 风险警示股</div>
          </el-col>
        </el-row>

        <div class="fs14 bold mt8">最近交易</div>
        <el-table :data="(acc.trades || []).slice(0, 8)" size="small" class="mt8">
          <el-table-column prop="timestamp" label="时间" width="140"><template #default="{ row }">{{ (row.timestamp || '').slice(0, 16) }}</template></el-table-column>
          <el-table-column prop="action" label="方向" width="70">
            <template #default="{ row }">
              <el-tag size="small" :type="row.action === 'buy' ? 'danger' : 'success'">{{ row.action === 'buy' ? '买入' : '卖出' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="股票" min-width="120">
            <template #default="{ row }">
              <el-link type="primary" style="font-size:12px" @click="showSymbolChart(row.symbol)">{{ row.name || row.symbol }}</el-link>
              <span class="fs11 ml4" style="color:#909399">{{ row.symbol }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="price" label="价格" align="right" />
          <el-table-column prop="quantity" label="数量" align="right" />
          <el-table-column prop="reason" label="决策理由" min-width="220"><template #default="{ row }">{{ row.reason }}</template></el-table-column>
          <el-table-column prop="confidence" label="置信度" width="80" align="right">
            <template #default="{ row }">{{ ((row.confidence || 0) * 100).toFixed(0) }}%</template>
          </el-table-column>
        </el-table>

        <el-collapse class="mt8">
          <el-collapse-item name="stats">
            <template #title><span class="fs14 bold">复盘与统计（盈亏比 / 纪律性 / 交易模式 / 选股能力）</span></template>
            <el-row :gutter="10">
              <el-col :xs="24" :sm="8">
                <div class="fs12">已平仓 <b class="mono">{{ acc.stats?.closed ?? 0 }}</b> 笔（{{ acc.stats?.win_count ?? 0 }}胜/{{ acc.stats?.loss_count ?? 0 }}负）· 胜率 <b class="mono">{{ fmtPct(acc.stats?.win_rate) }}</b></div>
                <div class="fs12 mt4">盈亏比 <b class="mono">{{ acc.stats?.profit_factor ?? '-' }}</b>（平均盈 <b class="up mono">{{ fmt(acc.stats?.avg_win) }}</b> ／ 平均亏 <b class="down mono">{{ fmt(acc.stats?.avg_loss) }}</b>）</div>
                <div class="fs12 mt4">单笔最大盈 <b class="up mono">{{ fmt(acc.stats?.max_win) }}</b> · 单笔最大亏 <b class="down mono">{{ fmt(acc.stats?.max_loss) }}</b></div>
                <div class="fs12 mt4">平均持有 <b class="mono">{{ acc.stats?.avg_holding_days }}</b> 天 · 交易模式 <b>{{ acc.stats?.pattern || '-' }}</b></div>
                <el-divider />
                <div class="fs12">纪律性评分 <b class="mono" :class="(acc.stats?.discipline?.score || 0) >= 70 ? 'up' : 'down'">{{ acc.stats?.discipline?.score ?? '-' }}</b>
                  <div class="fs11 mt4" style="color:#909399;line-height:1.6">{{ (acc.stats?.discipline?.notes || []).join('；') }}</div>
                </div>
                <div class="fs12 mt4">选股能力评分 <b class="mono" :class="(acc.stats?.stock_pick?.score || 0) >= 60 ? 'up' : 'down'">{{ acc.stats?.stock_pick?.score ?? '-' }}</b>
                  <div class="fs11 mt4" style="color:#909399;line-height:1.6">{{ (acc.stats?.stock_pick?.notes || []).join('；') }}</div>
                </div>
              </el-col>
              <el-col :xs="24" :sm="8">
                <div class="fs12 bold mb8">每笔已平仓盈亏</div>
                <el-table :data="(acc.stats?.per_trade || []).slice(0, 8)" size="small" max-height="210">
                  <el-table-column label="股票" min-width="120">
                    <template #default="{ row }">
                      <el-link type="primary" style="font-size:12px" @click="showSymbolChart(row.symbol)">{{ row.name || row.symbol }}</el-link>
                    </template>
                  </el-table-column>
                  <el-table-column label="持有" width="60" align="right"><template #default="{ row }">{{ row.buy_date === row.sell_date ? '0天' : row.holding_days + '天' }}</template></el-table-column>
                  <el-table-column label="成本" width="70" align="right"><template #default="{ row }">{{ row.avg_cost }}</template></el-table-column>
                  <el-table-column label="卖出" width="70" align="right"><template #default="{ row }">{{ row.price }}</template></el-table-column>
                  <el-table-column label="盈亏" width="90" align="right">
                    <template #default="{ row }"><span class="mono" :class="pnlCls(row.pnl)">{{ sign(row.pnl) }}{{ fmt(row.pnl) }}</span></template>
                  </el-table-column>
                  <el-table-column label="盈亏%" width="80" align="right">
                    <template #default="{ row }"><span class="mono" :class="pnlCls(row.pnl)">{{ (row.pnl_pct || 0) >= 0 ? '+' : '' }}{{ (row.pnl_pct || 0).toFixed(2) }}%</span></template>
                  </el-table-column>
                </el-table>
              </el-col>
              <el-col :xs="24" :sm="8">
                <div class="fs12 bold mb8">每周复盘汇总</div>
                <el-table :data="acc.stats?.weekly || []" size="small" max-height="104">
                  <el-table-column prop="week" label="周起始" width="110" />
                  <el-table-column prop="trades" label="笔数" width="60" align="right" />
                  <el-table-column label="盈亏" align="right">
                    <template #default="{ row }"><span class="mono" :class="pnlCls(row.pnl)">{{ sign(row.pnl) }}{{ fmt(row.pnl) }}</span></template>
                  </el-table-column>
                </el-table>
                <div class="fs12 bold mt8 mb8">历史复盘（每日）</div>
                <el-scrollbar max-height="132">
                  <div v-for="(r, i) in (acc.reviews || []).slice(0, 8)" :key="i" class="fs12 mb4" style="line-height:1.6">
                    <el-tag size="small" type="info" style="margin-right:4px">{{ (r.date || '').slice(0, 10) }}</el-tag>
                    {{ r.summary }}
                    <span v-if="r.mistakes && r.mistakes.length" class="down">【{{ r.mistakes.join('；') }}】</span>
                    <span v-if="r.improvements && r.improvements.length" class="up">【{{ r.improvements.join('；') }}】</span>
                  </div>
                  <el-empty v-if="!(acc.reviews || []).length" description="暂无复盘记录" :image-size="34" />
                </el-scrollbar>
              </el-col>
            </el-row>
          </el-collapse-item>
        </el-collapse>

        <div v-if="acc.lastError" class="mt8">
          <el-alert type="warning" :closable="false" :title="acc.lastError" />
        </div>
      </el-card>

      <el-empty v-if="!accounts.length" description="暂无模拟账户，点击「新建账户」创建" />

      <!-- 决策日志 -->
      <el-drawer v-model="logDrawer" :title="logTitle" size="600px">
        <el-timeline v-if="logs.length">
          <el-timeline-item v-for="l in logs" :key="l.id" :timestamp="(l.created_at || '').slice(0, 19)" placement="top">
            <div class="flex gap" style="align-items:center">
              <el-tag size="small" :type="logTagType(l.log_type)">{{ logTypeName(l.log_type) }}</el-tag>
              <span class="fs14 bold">{{ l.title }}</span>
            </div>
            <div v-if="l.log_type === 'pool'" class="fs12 mt4">
              <span v-for="p in (l.content?.pool || [])" :key="p.symbol" class="log-chip">
                {{ p.name || p.symbol }}<span class="fs12" style="color:#909399">（{{ p.source || '' }}）</span>
              </span>
            </div>
            <div v-else-if="l.log_type === 'decision'" class="fs12 mt4">
              <div v-for="(a, i) in (l.content?.actions || [])" :key="i" class="mt4">
                <el-tag size="small" :type="a.action === 'buy' ? 'danger' : a.action === 'sell' ? 'success' : 'info'" style="margin-right:4px">
                  {{ a.action === 'buy' ? '买入' : a.action === 'sell' ? '卖出' : '持有' }}
                </el-tag>
                <b>{{ a.symbol }}</b> × {{ a.quantity || 0 }} @ {{ a.price }}
                <span class="fs12" style="color:#606266"> — {{ a.reason || '' }}（置信度 {{ ((a.confidence || 0) * 100).toFixed(0) }}%）</span>
              </div>
              <div v-if="!(l.content?.actions || []).length" style="color:#909399">今日无买卖动作（弱市持币观望或已满仓）</div>
            </div>
            <div v-else-if="l.log_type === 'error'" class="fs12 mt4" style="color:#e6a23c">{{ l.content }}</div>
            <div v-else class="fs12 mt4" style="color:#909399">{{ l.content && l.content.error }}</div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无决策日志，运行一次「执行当日交易」即可生成" />
      </el-drawer>

      <!-- 个股 K线 + 缠论（持仓/交易点击查看） -->
      <el-dialog v-model="chartDialog" :title="chartTitle" width="820" top="6vh">
        <div class="fs12" style="color:#909399;margin-bottom:6px">日K线 + 缠论分型/笔/中枢/买卖点（真实行情 + 官方 czsc 插件）</div>
        <KlineChart v-if="posKline.length" :data="posKline" height="420px"
          :fx="posCzsc.fx_list || []" :bi="posCzsc.bi_list || []" :zs="posCzsc.zs_list || []"
          :signals="posCzsc.signals || []"
          :stage-points="posCzsc.stage_points || []" />
        <div v-else class="fs12" style="color:#909399;text-align:center;height:420px;line-height:420px">K线加载中…</div>
      </el-dialog>

      <el-dialog v-model="createDialog" title="新建模拟账户" width="420">
        <el-form label-width="90px">
          <el-form-item label="账户名称"><el-input v-model="newAccount.name" placeholder="如：AI短线账户" /></el-form-item>
          <el-form-item label="初始资金"><el-input-number v-model="newAccount.initial_capital" :min="1000" :step="10000" /></el-form-item>
          <el-form-item label="使用智能体">
            <el-select v-model="newAccount.agent_config_id" clearable placeholder="默认使用投研智能体" style="width:100%">
              <el-option v-for="a in agents" :key="a.id" :label="`${a.name}（${a.agent_type}）`" :value="a.id" />
            </el-select>
          </el-form-item>
        </el-form>
        <div class="fs12" style="color:#c26b0a">提示：交易决策基于真实行情（新浪/腾讯）；未配置 API Key 时使用内置本地决策（止损/止盈/均线）自动执行。</div>
        <template #footer>
          <el-button @click="createDialog = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="create">创建</el-button>
        </template>
      </el-dialog>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import MainLayout from '../layout/MainLayout.vue'
import LineChart from '../components/LineChart.vue'
import KlineChart from '../components/KlineChart.vue'
import { simulationApi, agentApi, stockApi } from '../api'

const accounts = ref([])
const agents = ref([])
const running = ref(false)
const runningId = ref(null)
const creating = ref(false)
const createDialog = ref(false)
const logDrawer = ref(false)
const logs = ref([])
const logTitle = ref('决策日志')
const newAccount = ref({ name: '', initial_capital: 100000, agent_config_id: null })
const barEl = ref(null)
let barChart = null
const chartDialog = ref(false)
const chartTitle = ref('个股分析')
const posKline = ref([])
const posCzsc = ref({})
const poolTab = ref('positions')
const trackInput = reactive({})
const poolSourceNote = '来源于最近一次 18:00 每日复盘报告'

const poolBy = (acc, src) => (acc.pool?.pool || []).filter((p) => p.source === src)
const poolCount = (acc, src) => poolBy(acc, src).length

async function addTrack(acc) {
  const raw = (trackInput[acc.id] || '').trim()
  if (!raw) { ElMessage.warning('请输入股票代码'); return }
  const sym = /^\d{6}$/.test(raw) ? (raw.startsWith('6') ? 'SH' + raw : 'SZ' + raw) : raw.toUpperCase()
  const tracked = [...(acc.pool?.tracked || [])]
  if (tracked.some((t) => (t.symbol || '') === sym)) { ElMessage.warning('已在追踪池'); return }
  tracked.push({ symbol: sym, name: raw.toUpperCase() })
  acc.pool = await simulationApi.setPool(acc.id, tracked)
  trackInput[acc.id] = ''
  ElMessage.success('已加入追踪池')
}

async function removeTrack(acc, t) {
  const tracked = (acc.pool?.tracked || []).filter((x) => (x.symbol || x.name) !== (t.symbol || t.name))
  acc.pool = await simulationApi.setPool(acc.id, tracked)
  ElMessage.success('已移除')
}

function logTypeName(t) {
  return t === 'run_start' ? '开始' : t === 'pool' ? '股池' : t === 'decision' ? '决策' : t === 'error' ? '降级' : t
}
function logTagType(t) {
  return t === 'error' ? 'warning' : t === 'decision' ? 'success' : t === 'pool' ? 'primary' : 'info'
}

function fmt(v) {
  return v == null ? '-' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v) {
  return v == null ? '0%' : (Number(v) * 100).toFixed(2) + '%'
}
function sign(v) {
  const n = Number(v || 0)
  return n >= 0 ? (n > 0 ? '+' : '') : '-'
}
function pnlCls(v) {
  const n = Number(v || 0)
  return n > 0 ? 'up' : n < 0 ? 'down' : ''
}
function pnlPct(row) {
  const cost = Number(row.avg_cost || 0)
  const cur = Number(row.current_price || 0)
  if (!cost) return 0
  return ((cur - cost) / cost) * 100
}

function onChartResize() { barChart && barChart.resize() }
function ensureBarChart() {
  if (barChart || !barEl.value) return
  try {
    barChart = echarts.init(barEl.value)
    window.addEventListener('resize', onChartResize)
  } catch { /* DOM 尚不可用时等待下一次 renderBar */ }
}
function renderBar() {
  if (!accounts.value.length) return
  ensureBarChart()
  if (!barChart) return
  const names = accounts.value.map((a) => a.name || ('账户#' + a.id))
  const returns = accounts.value.map((a) => Number(a.performance?.total_return || 0) * 100)
  const today = accounts.value.map((a) => Number(a.performance?.today_pnl || 0))
  barChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 44, right: 14, top: 26, bottom: 24 },
    xAxis: { type: 'category', data: names, axisLabel: { fontSize: 10, interval: 0 } },
    yAxis: [
      { type: 'value', name: '收益%', axisLabel: { fontSize: 10, formatter: '{value}%' } },
      { type: 'value', name: '当日(元)', axisLabel: { fontSize: 10 }, splitLine: { show: false } }
    ],
    series: [
      { name: '总收益率%', type: 'bar', data: returns, barWidth: 16, itemStyle: { color: (p) => (p.value >= 0 ? '#ef232a' : '#14b143') } },
      { name: '当日盈亏', type: 'bar', yAxisIndex: 1, data: today, barWidth: 16, itemStyle: { color: (p) => (p.value >= 0 ? '#f7b32b' : '#8b5cf6') } }
    ]
  }, true)
}

async function showPosChart(row) {
  await showSymbolChart(row.symbol)
}
async function showSymbolChart(symbol) {
  chartTitle.value = `${symbol} · 日K + 缠论`
  chartDialog.value = true
  posKline.value = []
  posCzsc.value = {}
  try {
    const [k, c] = await Promise.all([
      stockApi.kline(symbol, { period: 'day' }),
      stockApi.czsc(symbol)
    ])
    posKline.value = k.data || []
    posCzsc.value = c || {}
  } catch {
    posKline.value = []
  }
}

async function showLogs(acc) {
  logTitle.value = `${acc.name || ('模拟账户 #' + acc.id)} 决策日志`
  logs.value = await simulationApi.logs(acc.id)
  logDrawer.value = true
}

async function load() {
  accounts.value = await simulationApi.accounts()
  const agentMap = {}
  for (const a of agents.value) agentMap[a.id] = a
  for (const acc of accounts.value) {
    const ag = agentMap[acc.agent_config_id]
    acc.agent_name = ag?.name
    acc.agent_type = ag?.agent_type
    try { acc.performance = await simulationApi.performance(acc.id) } catch { acc.performance = {} }
    try { acc.positions = await simulationApi.positions(acc.id) } catch { acc.positions = [] }
    try { acc.trades = await simulationApi.trades(acc.id) } catch { acc.trades = [] }
    try { acc.equity = await simulationApi.equity(acc.id) } catch { acc.equity = [] }
    try { acc.pool = await simulationApi.pool(acc.id) } catch { acc.pool = {} }
    try { acc.stats = await simulationApi.stats(acc.id) } catch { acc.stats = {} }
    try { acc.reviews = await simulationApi.reviews(acc.id) } catch { acc.reviews = [] }
  }
  await nextTick()
  renderBar()
}

async function create() {
  creating.value = true
  try {
    await simulationApi.create({
      name: newAccount.value.name,
      initial_capital: newAccount.value.initial_capital,
      agent_config_id: newAccount.value.agent_config_id
    })
    createDialog.value = false
    newAccount.value = { name: '', initial_capital: 100000, agent_config_id: null }
    await load()
  } finally {
    creating.value = false
  }
}

async function remove(id) {
  await simulationApi.remove(id)
  await load()
}

async function resetAcc(id) {
  await simulationApi.reset(id)
  ElMessage.success('账户已重置（资金回到初始值，持仓/交易/复盘/日志已清空）')
  await load()
}

async function runOne(id) {
  runningId.value = id
  try {
    const r = await simulationApi.run(id, { date: undefined })
    if (r.error) {
      ElMessage.warning(r.error)
    } else {
      ElMessage.success(`完成 ${r.trades?.length || 0} 笔交易`)
    }
    await load()
  } finally {
    runningId.value = null
  }
}

async function runAll() {
  running.value = true
  try {
    for (const acc of accounts.value) {
      await simulationApi.run(acc.id, { date: undefined }).catch(() => {})
    }
    await load()
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  agents.value = await agentApi.list()
  await load()
})
onBeforeUnmount(() => {
  if (barChart) {
    barChart.dispose()
    barChart = null
  }
  window.removeEventListener('resize', onChartResize)
})
</script>

<style scoped>
.pool-tabs :deep(.el-tabs__header) { margin-bottom: 8px; }
.chip-wrap { display: flex; flex-wrap: wrap; gap: 6px; max-height: 260px; overflow-y: auto; }
.tracked-chips { display: flex; flex-wrap: wrap; gap: 6px; max-height: 260px; overflow-y: auto; }
.chip-close { margin-left: 4px; cursor: pointer; color: #c0c4cc; font-size: 13px; vertical-align: -2px; }
.chip-close:hover { color: #f56c6c; }
</style>