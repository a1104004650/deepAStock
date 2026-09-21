<template>
  <MainLayout>
    <div class="page">
      <!-- Layer 1: Competition List -->
      <div v-if="!selected" class="selection-layer">
        <div class="selection-header">
          <div>
            <h2 class="page-title">AI炒股比赛</h2>
            <p class="page-subtitle">多个AI智能体实时模拟交易对决</p>
          </div>
          <el-button type="primary" @click="openCreateDialog" round>
            <el-icon><Plus /></el-icon>新建比赛
          </el-button>
        </div>
        <div class="comp-grid">
          <div
            v-for="c in competitions"
            :key="c.id"
            class="comp-card"
            @click="enterCompetition(c)"
          >
            <div class="comp-card-header">
              <div class="comp-card-icon">🏆</div>
              <el-tag
                :type="statusTagType(c.status)"
                size="small"
                effect="dark"
                round
              >{{ statusLabel(c.status) }}</el-tag>
            </div>
            <div class="comp-card-body">
              <div class="comp-card-name">{{ c.name }}</div>
              <div class="comp-card-desc" v-if="c.description">{{ c.description }}</div>
              <div class="comp-card-meta">
                <span class="meta-item">
                  <el-icon><User /></el-icon>
                  {{ c.participant_count || 0 }} 选手
                </span>
                <span class="meta-item">¥{{ formatMoney(c.initial_capital) }}</span>
                <span class="meta-item">{{ formatDate(c.created_at) }}</span>
              </div>
            </div>
            <div class="comp-card-footer">
              <span>进入比赛</span>
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
          <div v-if="!competitions.length && !loadingList" class="empty-state">
            <div class="empty-icon">🎯</div>
            <div class="empty-text">暂无比赛</div>
            <div class="empty-hint">点击上方按钮创建你的第一场AI对决</div>
          </div>
        </div>
      </div>

      <!-- Layer 2 & 3: Competition Dashboard + Arena -->
      <div v-else class="arena-layer">
        <!-- Hero Header -->
        <div class="arena-hero">
          <div class="arena-hero-left">
            <el-button text @click="leaveArena" class="back-btn">
              <el-icon size="20"><ArrowLeft /></el-icon>
            </el-button>
            <div class="arena-hero-info">
              <h2 class="arena-hero-title">{{ selected.name }}</h2>
              <el-tag
                :type="statusTagType(selected.status)"
                size="small"
                effect="dark"
                round
              >{{ statusLabel(selected.status) }}</el-tag>
            </div>
          </div>
          <div class="arena-hero-right">
            <el-button v-if="selected.status === 'setup'" type="success" :loading="actionLoading" @click="startCompetition" round>
              <el-icon><VideoPlay /></el-icon>开始比赛
            </el-button>
            <template v-if="selected.status === 'active'">
              <el-button type="warning" :loading="actionLoading" @click="pauseCompetition" round>
                <el-icon><VideoPause /></el-icon>暂停
              </el-button>
              <el-button type="danger" :loading="actionLoading" @click="finishCompetition" round>
                <el-icon><CircleCloseFilled /></el-icon>结束
              </el-button>
              <el-button type="primary" :loading="tradeAllLoading" @click="tradeAll" round>
                <el-icon><Refresh /></el-icon>全部交易一轮
              </el-button>
            </template>
            <template v-if="selected.status === 'paused'">
              <el-button type="success" :loading="actionLoading" @click="resumeCompetition" round>
                <el-icon><VideoPlay /></el-icon>恢复
              </el-button>
              <el-button type="danger" :loading="actionLoading" @click="finishCompetition" round>
                <el-icon><CircleCloseFilled /></el-icon>结束
              </el-button>
            </template>
            <el-button v-if="selected.status !== 'finished'" @click="openEditDialog" round>
              <el-icon><Edit /></el-icon>编辑设置
            </el-button>
            <el-button v-if="selected.status === 'setup' || selected.status === 'finished'" type="danger" :loading="actionLoading" @click="deleteCompetition" round>
              <el-icon><Delete /></el-icon>删除
            </el-button>
          </div>
        </div>

        <!-- Stats Cards -->
        <div v-if="statsLoaded" class="stats-row">
          <div class="stat-card">
            <div class="stat-value">{{ statsData.participant_count || players.length }}</div>
            <div class="stat-label">参赛人数</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ statsData.total_trades || 0 }}</div>
            <div class="stat-label">总交易次数</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" :class="avgReturnClass">{{ avgReturn >= 0 ? '+' : '' }}{{ avgReturn }}%</div>
            <div class="stat-label">平均收益率</div>
          </div>
          <div class="stat-card">
            <div class="stat-value best">{{ bestPlayerName }}</div>
            <div class="stat-label">最佳选手</div>
          </div>
        </div>

        <!-- Player Dashboard -->
        <div class="players-dashboard">
          <div class="dashboard-label">选手列表</div>
          <div class="players-scroll">
            <div
              v-for="(p, idx) in players"
              :key="p.id"
              class="player-card"
              :class="{ 'is-top': idx === 0 && players.length > 1 && (p.total_return || 0) > 0 }"
              @mouseenter="showPosTooltip(p, $event)"
              @mouseleave="hidePosTooltip"
            >
              <div class="player-card-top">
                <div class="player-rank" v-if="players.length > 1">#{{ idx + 1 }}</div>
                <el-button class="player-edit-btn" size="small" circle @click.stop="openEditPlayer(p)">
                  <el-icon><Edit /></el-icon>
                </el-button>
                <el-button class="player-remove-btn" size="small" circle @click.stop="removePlayer(p)" :loading="removingPlayerId === p.id">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <div class="player-main">
                <div class="player-avatar-wrap">
                  <span class="player-avatar">{{ p.avatar }}</span>
                </div>
                <div class="player-info">
                  <div class="player-name">{{ p.name }}</div>
                  <div class="player-model">{{ p.provider }} / {{ p.model_name }}</div>
                </div>
              </div>
              <div :class="['player-return', (p.total_return || 0) >= 0 ? 'profit' : 'loss']">
                <span class="return-sign">{{ (p.total_return || 0) >= 0 ? '+' : '' }}</span>{{ ((p.total_return || 0) * 100).toFixed(2) }}%
              </div>
              <div class="player-trades">交易 {{ p.trade_count || 0 }} 次</div>
              <el-button v-if="selected.status === 'active'" size="small" type="primary" class="player-trade-btn" @click.stop="triggerPlayerTrade(p)" :loading="tradingPlayerId === p.id" round>
                交易一轮
              </el-button>
            </div>
            <div class="player-card add-player-card" @click="showAddPlayer = true">
              <el-icon size="28" color="#c0c4cc"><Plus /></el-icon>
              <span class="add-player-text">添加选手</span>
            </div>
          </div>
        </div>

        <!-- Position Tooltip -->
        <Teleport to="body">
          <div v-if="posTooltip.show" class="pos-tooltip" :style="{ left: posTooltip.x + 'px', top: posTooltip.y + 'px' }">
            <div class="pos-tooltip-header">
              <span class="pos-tooltip-title">{{ posTooltip.player }}</span>
              <span class="pos-tooltip-sub">当前持仓</span>
            </div>
            <div v-if="posTooltip.positions && posTooltip.positions.length" class="pos-tooltip-list">
              <div v-for="(pos, i) in posTooltip.positions" :key="i" class="pos-tooltip-row">
                <span class="pos-symbol">{{ pos.symbol }}</span>
                <span class="pos-qty">{{ pos.quantity }}股</span>
                <span :class="['pos-pnl', (pos.unrealized_pnl || 0) >= 0 ? 'profit' : 'loss']">
                  {{ (pos.unrealized_pnl || 0) >= 0 ? '+' : '' }}{{ (pos.unrealized_pnl || 0).toFixed(0) }}
                </span>
              </div>
            </div>
            <div v-else class="pos-tooltip-empty">空仓中</div>
          </div>
        </Teleport>

        <!-- Main Content Grid -->
        <div class="arena-grid">
          <div class="grid-chart">
            <div class="panel-header">
              <span class="panel-title">收益曲线</span>
              <span class="panel-badge">{{ players.length }} 选手</span>
            </div>
            <div ref="chartRef" class="equity-chart"></div>
          </div>
          <div class="grid-chat">
            <div class="panel-header">
              <span class="panel-title">群聊</span>
              <span class="panel-badge">{{ messages.length }}</span>
            </div>
            <div class="chat-box">
              <div class="chat-messages" ref="chatBoxRef">
                <div
                  v-for="msg in messages"
                  :key="msg.id"
                  :class="['chat-msg', msg.participant_id ? 'ai-msg' : 'sys-msg']"
                >
                  <span class="chat-avatar" v-if="msg.participant_id">{{ msg.participant_avatar }}</span>
                  <div class="chat-body">
                    <div class="chat-name" v-if="msg.participant_name">{{ msg.participant_name }}</div>
                    <div class="chat-content">{{ msg.content }}</div>
                    <div class="chat-time">{{ formatTime(msg.created_at) }}</div>
                  </div>
                </div>
                <div v-if="!messages.length" class="chat-empty">
                  <span>💬</span>
                  <span>暂无消息</span>
                </div>
              </div>
              <div class="chat-input-wrap">
                <el-input v-model="chatInput" placeholder="发送消息..." size="small" @keyup.enter="sendChat" class="chat-input">
                  <template #append>
                    <el-button @click="sendChat" :disabled="!chatInput.trim()" type="primary">发送</el-button>
                  </template>
                </el-input>
              </div>
            </div>
          </div>
        </div>

        <!-- Trade Records -->
        <div class="trades-panel">
          <div class="panel-header">
            <span class="panel-title">交易记录</span>
            <span class="panel-badge">{{ allTrades.length }}</span>
          </div>
          <el-table :data="allTrades" size="small" stripe max-height="280" class="trades-table">
            <el-table-column label="选手" width="120">
              <template #default="{ row }">
                <div class="trade-player">
                  <span>{{ row.participant_avatar }}</span>
                  <span class="trade-player-name">{{ row.participant_name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="130">
              <template #default="{ row }">
                <span class="trade-time">{{ formatTime(row.created_at) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="代码" width="80">
              <template #default="{ row }">
                <span class="trade-symbol">{{ row.symbol }}</span>
              </template>
            </el-table-column>
            <el-table-column label="方向" width="70">
              <template #default="{ row }">
                <el-tag :type="row.action === 'buy' ? 'danger' : 'success'" size="small" effect="dark" round>
                  {{ row.action === 'buy' ? '买入' : '卖出' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="数量" width="80">
              <template #default="{ row }">{{ row.quantity }}</template>
            </el-table-column>
            <el-table-column label="价格" width="90">
              <template #default="{ row }">
                <span class="trade-price">¥{{ row.price?.toFixed(2) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="金额" width="100">
              <template #default="{ row }">
                <span class="trade-amount">¥{{ row.amount?.toFixed(0) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="理由" prop="reason" min-width="180" show-overflow-tooltip />
          </el-table>
        </div>
      </div>
    </div>

    <!-- Create Competition Dialog -->
    <el-dialog v-model="showCreateDialog" title="新建比赛" width="520px" destroy-on-close>
      <el-form label-position="top" size="small">
        <el-form-item label="比赛名称" required>
          <el-input v-model="compForm.name" placeholder="例如：第一届AI炒股大赛" />
        </el-form-item>
        <el-form-item label="比赛描述">
          <el-input v-model="compForm.description" type="textarea" :rows="2" placeholder="可选，描述比赛规则或主题" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="初始资金">
              <el-input-number v-model="compForm.initial_capital" :min="10000" :step="10000" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最大持仓比例(%)">
              <el-input-number v-model="compForm.max_position_pct" :min="1" :max="100" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="最大持仓数">
              <el-input-number v-model="compForm.max_positions" :min="1" :max="50" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="交易手续费(%)">
              <el-input-number v-model="compForm.trading_fee" :min="0" :max="1" :step="0.001" :precision="4" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="股票池（可选）">
          <el-input v-model="poolInput" type="textarea" :rows="3" placeholder="每行一个股票代码，留空则不限制" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="createCompetition" :disabled="!compForm.name" round>创建</el-button>
      </template>
    </el-dialog>

    <!-- Edit Competition Dialog -->
    <el-dialog v-model="showEditDialog" title="编辑比赛设置" width="520px" destroy-on-close>
      <el-form label-position="top" size="small">
        <el-form-item label="比赛名称" required>
          <el-input v-model="editForm.name" placeholder="例如：第一届AI炒股大赛" />
        </el-form-item>
        <el-form-item label="比赛描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" placeholder="可选，描述比赛规则或主题" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="初始资金">
              <el-input-number v-model="editForm.initial_capital" :min="10000" :step="10000" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最大持仓比例(%)">
              <el-input-number v-model="editForm.max_position_pct" :min="1" :max="100" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="最大持仓数">
              <el-input-number v-model="editForm.max_positions" :min="1" :max="50" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="交易手续费(%)">
              <el-input-number v-model="editForm.trading_fee" :min="0" :max="1" :step="0.001" :precision="4" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="股票池（可选）">
          <el-input v-model="editPoolInput" type="textarea" :rows="3" placeholder="每行一个股票代码，留空则不限制" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="updateCompetition" :disabled="!editForm.name" round>保存</el-button>
      </template>
    </el-dialog>

    <!-- Add/Edit Player Dialog -->
    <el-dialog v-model="showAddPlayer" :title="editingPlayerId ? '编辑AI选手' : '添加AI选手'" width="560px" destroy-on-close @close="resetPlayerForm">
      <div class="curl-section">
        <div class="curl-header">
          <span class="curl-icon">⚡</span>
          <span class="curl-title">CURL一键导入</span>
        </div>
        <el-input v-model="curlInput" type="textarea" :rows="3" placeholder="粘贴 curl 命令，自动解析 API 配置..." />
        <div class="curl-actions">
          <el-button size="small" type="primary" :loading="curlParsing" @click="parseCurl">解析</el-button>
          <div v-if="curlResult" :class="['curl-msg', curlOk ? 'ok' : 'err']">{{ curlResult }}</div>
        </div>
      </div>
      <el-divider content-position="center">
        <span style="font-size:12px;color:var(--el-text-color-placeholder)">或手动填写</span>
      </el-divider>
      <el-form label-position="top" size="small">
        <el-form-item label="选手名称" required>
          <el-input v-model="playerForm.name" placeholder="例如：DeepSeek战士" />
        </el-form-item>
        <el-form-item label="头像">
          <div class="avatar-picker">
            <div class="avatar-selected">{{ playerForm.avatar }}</div>
            <div class="avatar-grid">
              <span v-for="e in emojiList" :key="e" class="avatar-emoji" :class="{active: playerForm.avatar===e}" @click="playerForm.avatar=e">{{ e }}</span>
            </div>
          </div>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="AI提供商" required>
              <el-select v-model="playerForm.provider" style="width:100%">
                <el-option label="DeepSeek" value="deepseek" />
                <el-option label="OpenAI" value="openai" />
                <el-option label="通义千问" value="qwen" />
                <el-option label="智谱GLM" value="zhipu" />
                <el-option label="Claude" value="claude" />
                <el-option label="Gemini" value="gemini" />
                <el-option label="Ollama(本地)" value="ollama" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="模型名称">
              <el-input v-model="playerForm.model_name" placeholder="例如：deepseek-chat">
                <template #append>
                  <el-button :loading="modelsLoading" @click="fetchModels" title="获取模型列表">
                    <el-icon><Refresh /></el-icon>
                  </el-button>
                </template>
              </el-input>
              <div v-if="modelList.length" class="model-list">
                <el-tag v-for="m in modelList" :key="m" size="small" :type="m === playerForm.model_name ? 'primary' : 'info'" class="model-tag" @click="playerForm.model_name = m">{{ m }}</el-tag>
              </div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="API Base">
          <el-input v-model="playerForm.api_base" placeholder="留空使用默认" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="playerForm.api_key" placeholder="API密钥" show-password />
        </el-form-item>
        <el-form-item label="自定义系统提示词（可选）">
          <el-input v-model="playerForm.system_prompt" type="textarea" :rows="3" placeholder="留空使用默认交易策略" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddPlayer = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="savePlayer" :disabled="!playerForm.name || !playerForm.provider" round>{{ editingPlayerId ? '保存' : '添加' }}</el-button>
      </template>
    </el-dialog>
  </MainLayout>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, ArrowLeft, ArrowRight, VideoPlay, VideoPause,
  User, Edit, Delete, CircleCloseFilled, Refresh, Close
} from '@element-plus/icons-vue'
import MainLayout from '../../layout/MainLayout.vue'
import { labApi } from '../../api'
import * as echarts from 'echarts'

const competitions = ref([])
const loadingList = ref(false)
const selected = ref(null)
const players = ref([])
const actionLoading = ref(false)
const tradeAllLoading = ref(false)
const tradingPlayerId = ref(null)
const removingPlayerId = ref(null)

const messages = ref([])
const allTrades = ref([])
const chatInput = ref('')
const chatBoxRef = ref(null)

const statsData = ref({})
const statsLoaded = ref(false)

const showCreateDialog = ref(false)
const compForm = ref({ name: '', description: '', initial_capital: 100000, max_position_pct: 30, max_positions: 10, trading_fee: 0.0003 })
const poolInput = ref('')

const showEditDialog = ref(false)
const editForm = ref({ name: '', description: '', initial_capital: 100000, max_position_pct: 30, max_positions: 10, trading_fee: 0.0003 })
const editPoolInput = ref('')

const showAddPlayer = ref(false)
const editingPlayerId = ref(null)
const playerForm = ref({
  name: '', avatar: '🤖', provider: 'deepseek',
  api_base: '', api_key: '', model_name: '', system_prompt: '',
})

const emojiList = ['🤖','🧠','🦊','🐯','🦁','🐻','🐲','🦅','🐺','🐗','🐴','🦄','🐔','🐧','🐦','🐤','🦆','🦅','🦉','🦇','🐝','🐛','🦋','🐌','🐞','🐜','🐢','🐍','🦎','🦖','🦕','🐙','🦑','🦐','🦞','🦀','🐡','🐠','🐟','🐬','🐳','🐋','🦈','🐊','🐅','🐆','🦓','🦍','🐘','🐪','🐫','🦒','🦘','🐃','🐂','🐄','🐎','🐖','🐏','🐑','🦙','🐐','🦌','🐕','🐩','🐈','🐓','🦚','🦜','🦢','🦩','🐇']

const curlInput = ref('')
const curlParsing = ref(false)
const curlResult = ref('')
const curlOk = ref(false)
const modelsLoading = ref(false)
const modelList = ref([])

const chartRef = ref(null)
let equityChart = null

const posTooltip = ref({ show: false, x: 0, y: 0, player: '', positions: [] })

const avgReturn = computed(() => {
  if (!players.value.length) return '0.00'
  const sum = players.value.reduce((acc, p) => acc + (p.total_return || 0), 0)
  return ((sum / players.value.length) * 100).toFixed(2)
})

const avgReturnClass = computed(() => {
  return parseFloat(avgReturn.value) >= 0 ? 'profit' : 'loss'
})

const bestPlayerName = computed(() => {
  if (!players.value.length) return '-'
  const sorted = [...players.value].sort((a, b) => (b.total_return || 0) - (a.total_return || 0))
  return sorted[0]?.name || '-'
})

function statusLabel(s) {
  const map = { setup: '筹备中', active: '进行中', paused: '已暂停', finished: '已结束' }
  return map[s] || s
}

function statusTagType(s) {
  const map = { setup: 'warning', active: 'success', paused: 'info', finished: 'info' }
  return map[s] || 'info'
}

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatDate(t) {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatMoney(v) {
  if (!v) return '0'
  if (v >= 10000) return (v / 10000).toFixed(0) + '万'
  return v.toLocaleString()
}

async function loadCompetitions() {
  loadingList.value = true
  try {
    const res = await labApi.competitions()
    competitions.value = Array.isArray(res) ? res : (res.data || [])
  } catch { competitions.value = [] }
  loadingList.value = false
}

async function enterCompetition(c) {
  try {
    const res = await labApi.getCompetition(c.id)
    selected.value = res.data || res
    players.value = selected.value.participants || []
    await loadStats()
    await loadChat()
    await loadAllTrades()
    await loadEquityCurve()
  } catch (e) {
    selected.value = c
    players.value = c.participants || []
  }
}

function leaveArena() {
  selected.value = null
  players.value = []
  messages.value = []
  allTrades.value = []
  statsLoaded.value = false
  statsData.value = {}
  if (equityChart) {
    equityChart.dispose()
    equityChart = null
  }
}

async function loadStats() {
  if (!selected.value) return
  try {
    const res = await labApi.competitionStats(selected.value.id)
    statsData.value = res.data || res
    statsLoaded.value = true
  } catch {
    statsLoaded.value = true
  }
}

async function loadChat() {
  if (!selected.value) return
  try {
    const res = await labApi.chat(selected.value.id)
    messages.value = Array.isArray(res) ? res : (res.data || [])
    await nextTick()
    if (chatBoxRef.value) chatBoxRef.value.scrollTop = chatBoxRef.value.scrollHeight
  } catch { messages.value = [] }
}

async function loadAllTrades() {
  if (!players.value.length) { allTrades.value = []; return }
  const all = []
  for (const p of players.value) {
    try {
      const res = await labApi.participantTrades(p.id)
      const list = Array.isArray(res) ? res : (res.data || [])
      list.forEach(t => {
        t.participant_avatar = p.avatar
        t.participant_name = p.name
      })
      all.push(...list)
    } catch {}
  }
  all.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  allTrades.value = all
}

async function loadEquityCurve() {
  if (!selected.value) return
  try {
    const res = await labApi.equityCurve(selected.value.id)
    const data = res.data || res
    await nextTick()
    renderChart(data)
  } catch {}
}

function renderChart(data) {
  if (!chartRef.value) return
  if (equityChart) equityChart.dispose()
  equityChart = echarts.init(chartRef.value)

  const colors = ['#409eff', '#ef232a', '#14b143', '#e6a23c', '#909399', '#f56c6c', '#67c23a', '#b37feb']
  const series = []
  if (data && data.players) {
    data.players.forEach((p, i) => {
      series.push({
        name: p.name,
        type: 'line',
        data: p.equity || [],
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2.5 },
        itemStyle: { color: colors[i % colors.length] },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: colors[i % colors.length] + '20' },
          { offset: 1, color: colors[i % colors.length] + '02' },
        ])},
      })
    })
  }
  const xData = data?.dates || []

  equityChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#ebeef5',
      textStyle: { fontSize: 12 },
    },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: 16, top: 35, bottom: 24 },
    xAxis: { type: 'category', data: xData, boundaryGap: false, axisLabel: { fontSize: 10 }, axisLine: { lineStyle: { color: '#dcdfe6' } } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: v => (v / 10000).toFixed(1) + '万' }, splitLine: { lineStyle: { type: 'dashed', color: '#ebeef5' } } },
    series,
  })
}

function openCreateDialog() {
  compForm.value = { name: '', description: '', initial_capital: 100000, max_position_pct: 30, max_positions: 10, trading_fee: 0.0003 }
  poolInput.value = ''
  showCreateDialog.value = true
}

function openEditDialog() {
  if (!selected.value) return
  editForm.value = {
    name: selected.value.name || '',
    description: selected.value.description || '',
    initial_capital: selected.value.initial_capital || 100000,
    max_position_pct: selected.value.max_position_pct || 30,
    max_positions: selected.value.max_positions || 10,
    trading_fee: selected.value.trading_fee || 0.0003,
  }
  const pool = selected.value.stock_pool
  editPoolInput.value = Array.isArray(pool) ? pool.join('\n') : (pool || '')
  showEditDialog.value = true
}

async function createCompetition() {
  actionLoading.value = true
  try {
    const pool = poolInput.value.trim()
      ? poolInput.value.split('\n').map(s => s.trim()).filter(Boolean)
      : null
    await labApi.createCompetition({ ...compForm.value, stock_pool: pool })
    ElMessage.success('创建成功')
    showCreateDialog.value = false
    await loadCompetitions()
  } finally { actionLoading.value = false }
}

async function updateCompetition() {
  actionLoading.value = true
  try {
    const pool = editPoolInput.value.trim()
      ? editPoolInput.value.split('\n').map(s => s.trim()).filter(Boolean)
      : null
    await labApi.updateCompetition(selected.value.id, { ...editForm.value, stock_pool: pool })
    ElMessage.success('保存成功')
    showEditDialog.value = false
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function deleteCompetition() {
  try {
    await ElMessageBox.confirm('确定删除该比赛？此操作不可恢复。', '删除确认', { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' })
  } catch { return }
  actionLoading.value = true
  try {
    await labApi.deleteCompetition(selected.value.id)
    ElMessage.success('已删除')
    await leaveArena()
    await loadCompetitions()
  } finally { actionLoading.value = false }
}

async function startCompetition() {
  actionLoading.value = true
  try {
    await labApi.startCompetition(selected.value.id)
    ElMessage.success('比赛已开始')
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function pauseCompetition() {
  actionLoading.value = true
  try {
    await labApi.pauseCompetition(selected.value.id)
    ElMessage.success('比赛已暂停')
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function resumeCompetition() {
  actionLoading.value = true
  try {
    await labApi.resumeCompetition(selected.value.id)
    ElMessage.success('比赛已恢复')
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function finishCompetition() {
  try {
    await ElMessageBox.confirm('确定结束比赛？', '确认', { type: 'warning' })
  } catch { return }
  actionLoading.value = true
  try {
    await labApi.finishCompetition(selected.value.id)
    ElMessage.success('比赛已结束')
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function tradeAll() {
  tradeAllLoading.value = true
  try {
    await labApi.tradeAll(selected.value.id)
    ElMessage.success('交易指令已发送')
    await enterCompetition(selected.value)
  } finally { tradeAllLoading.value = false }
}

async function addPlayer() {
  actionLoading.value = true
  try {
    await labApi.addParticipant(selected.value.id, playerForm.value)
    ElMessage.success('添加成功')
    showAddPlayer.value = false
    resetPlayerForm()
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function removePlayer(p) {
  try {
    await ElMessageBox.confirm(`确定移除选手「${p.name}」？`, '移除确认', { type: 'warning' })
  } catch { return }
  removingPlayerId.value = p.id
  try {
    await labApi.removeParticipant(p.id)
    ElMessage.success('已移除')
    await enterCompetition(selected.value)
  } finally { removingPlayerId.value = null }
}

async function triggerPlayerTrade(p) {
  tradingPlayerId.value = p.id
  try {
    await labApi.triggerParticipantTrade(selected.value.id, p.id)
    ElMessage.success(`${p.name} 交易指令已发送`)
    await enterCompetition(selected.value)
  } finally { tradingPlayerId.value = null }
}

function resetPlayerForm() {
  editingPlayerId.value = null
  playerForm.value = {
    name: '', avatar: '🤖', provider: 'deepseek',
    api_base: '', api_key: '', model_name: '', system_prompt: '',
  }
  curlInput.value = ''
  curlResult.value = ''
}

function openEditPlayer(p) {
  editingPlayerId.value = p.id
  playerForm.value = {
    name: p.name, avatar: p.avatar || '🤖', provider: p.provider || 'deepseek',
    api_base: p.api_base || '', api_key: p.api_key || '', model_name: p.model_name || '',
    system_prompt: p.system_prompt || '',
  }
  showAddPlayer.value = true
}

async function savePlayer() {
  actionLoading.value = true
  try {
    if (editingPlayerId.value) {
      await labApi.updateParticipant(editingPlayerId.value, playerForm.value)
      ElMessage.success('保存成功')
    } else {
      await labApi.addParticipant(selected.value.id, playerForm.value)
      ElMessage.success('添加成功')
    }
    showAddPlayer.value = false
    resetPlayerForm()
    await enterCompetition(selected.value)
  } finally { actionLoading.value = false }
}

async function fetchModels() {
  if (!playerForm.value.api_base) { ElMessage.warning('请先填写 API 地址'); return }
  modelsLoading.value = true
  modelList.value = []
  try {
    const r = await labApi.fetchModels({ api_base: playerForm.value.api_base, api_key: playerForm.value.api_key })
    if (r.models?.length) {
      modelList.value = r.models
      ElMessage.success(`获取到 ${r.models.length} 个模型`)
    } else {
      ElMessage.warning(r.error || '未获取到模型列表')
    }
  } catch (e) {
    ElMessage.error('获取模型列表失败')
  } finally {
    modelsLoading.value = false
  }
}

async function sendChat() {
  if (!chatInput.value.trim()) return
  await labApi.sendChat(selected.value.id, chatInput.value)
  chatInput.value = ''
  await loadChat()
}

async function parseCurl() {
  if (!curlInput.value.trim()) return
  curlParsing.value = true
  curlResult.value = ''
  try {
    const data = await labApi.parseCurl(curlInput.value.trim())
    if (data.api_key) {
      if (data.api_base || data.base_url) playerForm.value.api_base = data.base_url || data.api_base
      if (data.api_key) playerForm.value.api_key = data.api_key
      if (data.model_name || data.model) playerForm.value.model_name = data.model_name || data.model
      if (data.provider) playerForm.value.provider = data.provider
      curlResult.value = '解析成功！已自动填充配置'
      curlOk.value = true
    } else {
      curlResult.value = '解析完成，未检测到有效配置'
      curlOk.value = false
    }
  } catch (e) {
    curlResult.value = '解析失败：' + (e.response?.data?.detail || e.message)
    curlOk.value = false
  }
  curlParsing.value = false
}

async function showPosTooltip(player, event) {
  const rect = event.currentTarget.getBoundingClientRect()
  posTooltip.value = { show: true, x: rect.left, y: rect.bottom + 8, player: player.name, positions: [] }
  try {
    const res = await labApi.participantPositions(player.id)
    posTooltip.value.positions = Array.isArray(res) ? res : (res.data || [])
  } catch { posTooltip.value.positions = [] }
}

function hidePosTooltip() {
  posTooltip.value.show = false
}

function onResize() { equityChart?.resize() }

onMounted(() => {
  loadCompetitions()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (equityChart) { equityChart.dispose(); equityChart = null }
})
</script>

<style scoped>
.page {
  height: 100%;
  --panel-bg: var(--el-bg-color);
  --panel-border: var(--el-border-color-lighter);
  --panel-radius: 12px;
  --hero-bg: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
}

/* ===== Selection Layer ===== */
.selection-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 24px;
}
.page-title {
  font-size: 22px;
  font-weight: 800;
  margin: 0;
  letter-spacing: -0.3px;
}
.page-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 4px 0 0 0;
}

/* Competition Cards Grid */
.comp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.comp-card {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.3s ease;
}
.comp-card:hover {
  border-color: transparent;
  box-shadow: 0 8px 30px rgba(0,0,0,0.1);
  transform: translateY(-3px);
}
.comp-card:hover .comp-card-footer { color: var(--el-color-primary); }
.comp-card:hover .comp-card-footer el-icon { transform: translateX(3px); }

.comp-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 12px;
}
.comp-card-icon { font-size: 24px; }
.comp-card-body { padding: 0 18px 14px; }
.comp-card-name {
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 6px;
}
.comp-card-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.comp-card-meta {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}
.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.comp-card-footer {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 18px;
  border-top: 1px solid var(--panel-border);
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  transition: color 0.2s;
}
.comp-card-footer el-icon { transition: transform 0.2s; }

/* Empty state */
.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 60px 20px;
  background: var(--panel-bg);
  border: 2px dashed var(--panel-border);
  border-radius: 12px;
}
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty-text { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
.empty-hint { font-size: 13px; color: var(--el-text-color-placeholder); }

/* ===== Arena Layer ===== */
.arena-layer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Arena Hero Header */
.arena-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--hero-bg);
  border-radius: var(--panel-radius);
  padding: 16px 24px;
  color: #fff;
}
.arena-hero-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.back-btn { color: rgba(255,255,255,0.8); font-size: 18px; }
.back-btn:hover { color: #fff; }
.arena-hero-info {
  display: flex;
  align-items: center;
  gap: 10px;
}
.arena-hero-title {
  font-size: 20px;
  font-weight: 700;
  margin: 0;
}
.arena-hero-right {
  display: flex;
  gap: 8px;
}

/* Stats Row */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.stat-card {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 20px;
  text-align: center;
  transition: all 0.2s;
}
.stat-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
.stat-value {
  font-size: 28px;
  font-weight: 800;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
  letter-spacing: -0.5px;
}
.stat-value.profit { color: #ef232a; }
.stat-value.loss { color: #14b143; }
.stat-value.best {
  font-size: 18px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.stat-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* Players Dashboard */
.players-dashboard {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 16px;
}
.dashboard-label {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 12px;
}
.players-scroll {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding: 4px 0;
  scrollbar-width: thin;
}
.player-card {
  position: relative;
  min-width: 180px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 14px 16px;
  flex-shrink: 0;
  cursor: default;
  transition: all 0.2s;
}
.player-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  border-color: var(--el-color-primary-light-5);
}
.player-card.is-top {
  border-color: var(--el-color-warning-light-5);
  background: linear-gradient(135deg, var(--panel-bg) 0%, #fdf6ec 100%);
}
.player-card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.player-rank {
  font-size: 11px;
  font-weight: 700;
  color: var(--el-text-color-placeholder);
}
.player-remove-btn {
  opacity: 0;
  transition: opacity 0.2s;
}
.player-edit-btn {
  opacity: 0;
  transition: opacity 0.2s;
}
.player-card:hover .player-remove-btn,
.player-card:hover .player-edit-btn {
  opacity: 1;
}
.player-main {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.player-avatar-wrap {
  width: 40px;
  height: 40px;
  background: var(--el-fill-color-lighter);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.player-avatar { font-size: 22px; }
.player-info { flex: 1; min-width: 0; }
.player-name {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.player-model {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.player-return {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.5px;
  margin-bottom: 4px;
}
.return-sign { font-size: 14px; }
.player-trades {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-bottom: 8px;
}
.player-trade-btn { width: 100%; }

.add-player-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-style: dashed;
  cursor: pointer;
  min-height: 180px;
}
.add-player-card:hover {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.add-player-text {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}

/* Position Tooltip */
.pos-tooltip {
  position: fixed;
  background: #fff;
  border-radius: 10px;
  padding: 14px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.15);
  z-index: 2000;
  min-width: 200px;
  max-width: 300px;
}
.pos-tooltip-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--panel-border);
}
.pos-tooltip-title { font-size: 14px; font-weight: 700; }
.pos-tooltip-sub { font-size: 11px; color: var(--el-text-color-placeholder); }
.pos-tooltip-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 12px;
}
.pos-symbol { font-weight: 600; }
.pos-qty { color: var(--el-text-color-secondary); }
.pos-pnl { font-weight: 700; }
.pos-tooltip-empty {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  text-align: center;
  padding: 8px 0;
}

/* ===== Main Grid ===== */
.arena-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  min-height: 0;
}
.grid-chart, .grid-chat {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 16px;
  min-width: 0;
}

/* Panel Header */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.panel-title {
  font-size: 15px;
  font-weight: 700;
}
.panel-badge {
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}

/* Chart */
.equity-chart {
  width: 100%;
  height: 320px;
}

/* Chat */
.chat-box {
  display: flex;
  flex-direction: column;
  height: 320px;
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}
.chat-msg {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.sys-msg { justify-content: center; }
.sys-msg .chat-content {
  color: var(--el-text-color-secondary);
  font-style: italic;
  font-size: 12px;
  background: none;
  padding: 0;
}
.chat-avatar {
  font-size: 20px;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}
.chat-body { flex: 1; min-width: 0; }
.chat-name {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 3px;
  color: var(--el-text-color-regular);
}
.chat-content {
  font-size: 13px;
  line-height: 1.6;
  background: var(--el-fill-color-lighter);
  padding: 8px 12px;
  border-radius: 10px;
  border-top-left-radius: 2px;
  white-space: pre-wrap;
  word-break: break-word;
}
.chat-time {
  font-size: 10px;
  color: var(--el-text-color-placeholder);
  margin-top: 3px;
}
.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 40px 0;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}
.chat-input-wrap {
  border-top: 1px solid var(--panel-border);
  padding-top: 10px;
}

/* ===== Trades Panel ===== */
.trades-panel {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 16px;
}
.trades-table { border-radius: 8px; }
.trade-player {
  display: flex;
  align-items: center;
  gap: 6px;
}
.trade-player-name { font-size: 12px; font-weight: 500; }
.trade-time { font-size: 12px; color: var(--el-text-color-secondary); }
.trade-symbol { font-weight: 600; font-size: 13px; }
.trade-price, .trade-amount { font-size: 13px; }

/* Profit / Loss */
.profit { color: #ef232a; }
.loss { color: #14b143; }

/* ===== Curl Section ===== */
.curl-section {
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--panel-border);
  border-radius: 10px;
  padding: 14px;
}
.curl-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.curl-icon { font-size: 16px; }
.curl-title { font-weight: 600; font-size: 13px; }
.curl-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
}
.curl-msg {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
}
.curl-msg.ok { color: #67c23a; background: #f0f9eb; }
.curl-msg.err { color: #f56c6c; background: #fef0f0; }

/* Avatar Picker */
.avatar-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.avatar-selected {
  width: 48px;
  height: 48px;
  font-size: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-lighter);
  border: 2px solid var(--el-border-color);
  border-radius: 10px;
}
.avatar-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  max-height: 100px;
  overflow-y: auto;
  padding: 6px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}
.avatar-emoji {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s;
}
.avatar-emoji:hover {
  background: var(--el-border-color-lighter);
  transform: scale(1.15);
}
.avatar-emoji.active {
  background: var(--el-color-primary-light-9);
  outline: 2px solid var(--el-color-primary);
}

@media (max-width: 800px) {
  .arena-grid { grid-template-columns: 1fr; }
  .comp-grid { grid-template-columns: 1fr; }
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .arena-hero { flex-direction: column; gap: 12px; align-items: flex-start; }
  .arena-hero-right { flex-wrap: wrap; }
}
.model-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
  max-height: 120px;
  overflow-y: auto;
}
.model-tag {
  cursor: pointer;
  transition: all 0.15s;
}
.model-tag:hover {
  opacity: 0.8;
}
</style>
