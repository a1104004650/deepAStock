<template>
  <MainLayout>
    <div class="research-page">
      <div class="page-header">
        <h2 class="page-title">AI投研团队</h2>
        <p class="page-subtitle">多角色AI分析师协作研究，独立分析 → 交叉质询 → 综合报告</p>
      </div>

      <div class="two-col">
        <!-- 左侧：分析师管理 -->
        <div class="col-left">
          <div class="col-header">
            <span class="col-title"><span class="col-title-dot" :style="{ background: 'var(--el-color-primary)' }"></span>分析师管理</span>
            <div class="flex gap4">
              <el-tag size="small" type="info" round>{{ analysts.length }}</el-tag>
              <el-button type="primary" size="small" @click="openAddAnalyst">
                <el-icon><Plus /></el-icon>添加
              </el-button>
            </div>
          </div>
          <div class="analyst-list" v-loading="analystsLoading">
            <div v-for="a in analysts" :key="a.id" class="analyst-card" :class="{ inactive: !a.is_active }">
              <div class="analyst-card-body">
                <div class="analyst-avatar" :style="{ background: roleBg(a.role) }">
                  <span class="analyst-avatar-emoji">{{ a.avatar || '🤖' }}</span>
                  <span class="analyst-role-dot" :style="{ background: roleColor(a.role) }"></span>
                </div>
                <div class="analyst-info">
                  <div class="analyst-name">{{ a.name }}</div>
                  <div class="analyst-role-row">
                    <span class="analyst-role-dot-inline" :style="{ background: roleColor(a.role) }"></span>
                    <span class="analyst-role-text">{{ roleLabel(a.role) }}</span>
                  </div>
                  <div class="analyst-meta">{{ a.provider }} / {{ a.model_name }}</div>
                </div>
              </div>
              <div class="analyst-card-actions">
                <el-switch
                  v-model="a.is_active"
                  size="small"
                  @change="toggleActive(a)"
                />
                <el-button text size="small" @click="openEditAnalyst(a)">
                  <el-icon><Edit /></el-icon>
                </el-button>
                <el-button text type="danger" size="small" @click="deleteAnalyst(a)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
            </div>
            <div v-if="!analysts.length" class="analyst-empty">
              <div class="analyst-empty-icon">🤖</div>
              <div class="analyst-empty-text">暂无分析师</div>
              <div class="analyst-empty-hint">点击上方按钮添加您的第一位分析师</div>
            </div>
          </div>
        </div>

        <!-- 右侧：研究任务 -->
        <div class="col-right">
          <div class="col-header">
            <span class="col-title"><span class="col-title-dot" :style="{ background: 'var(--el-color-success)' }"></span>研究任务</span>
            <el-button type="primary" size="small" @click="showCreateResearch = true">
              <el-icon><Plus /></el-icon>发起研究
            </el-button>
          </div>

          <el-table :data="tasks" size="small" stripe class="task-table" highlight-current-row @current-change="onRowClick" v-loading="tasksLoading">
            <el-table-column label="股票" min-width="120">
              <template #default="{ row }">
                <span class="bold">{{ row.symbol }}</span>
                <span style="color:var(--el-text-color-secondary);margin-left:4px">{{ row.stock_name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small" round>{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="进度" width="130">
              <template #default="{ row }">
                <el-progress :percentage="row.progress || 0" :status="row.status === 'completed' ? 'success' : ''" :stroke-width="6" />
              </template>
            </el-table-column>
            <el-table-column label="阶段" width="100">
              <template #default="{ row }">{{ stageLabel(row.stage) }}</template>
            </el-table-column>
            <el-table-column label="创建时间" width="150">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button size="small" type="primary" link @click="viewReport(row)">查看</el-button>
                <el-button
                  v-if="row.status === 'pending'"
                  size="small" type="success" link
                  :loading="runningId === row.id"
                  @click="runResearch(row)"
                >执行</el-button>
                <el-button size="small" type="danger" link @click="deleteTask(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 研究报告详情 -->
          <div v-if="currentTask" class="report-section">
            <div class="report-section-header">
              <div class="report-section-title-row">
                <span class="reports-title">{{ currentTask.symbol }}</span>
                <span class="reports-stock-name">{{ currentTask.stock_name }}</span>
                <span class="reports-label">研究报告</span>
              </div>
              <el-tag :type="statusTagType(currentTask.status)" size="small" round>{{ statusLabel(currentTask.status) }}</el-tag>
            </div>

            <!-- 工作流进度 -->
            <div class="workflow-bar">
              <div
                v-for="(s, i) in workflowStages"
                :key="i"
                :class="['stage', { active: currentTask.stage === s.key, done: isStageDone(s.key) }]"
              >
                <div class="stage-icon">{{ isStageDone(s.key) && currentTask.stage !== s.key ? '✓' : i + 1 }}</div>
                <div class="stage-label">{{ s.label }}</div>
                <div v-if="i < workflowStages.length - 1" class="stage-line" :class="{ done: isStageDone(s.key) }"></div>
              </div>
            </div>

            <el-progress
              v-if="currentTask.status === 'running'"
              :percentage="currentTask.progress || 0"
              :stroke-width="8"
              style="margin-bottom:16px"
            />

            <!-- 分析师报告 -->
            <div v-if="analystReports.length" class="reports-grid">
              <div class="reports-subtitle">
                <span class="reports-subtitle-icon">📊</span>分析师报告
              </div>
              <div class="reports-columns">
                <div v-for="r in analystReports" :key="r.id" class="report-card">
                  <div class="report-header">
                    <div class="report-header-left">
                      <span class="report-role-dot" :style="{ background: roleColor(r.analyst_role) }"></span>
                      <span :class="['report-role', r.analyst_role]">{{ r.analyst_name }}</span>
                    </div>
                    <el-tag size="small" :type="r.stage === 'discuss' ? 'warning' : 'info'" round>
                      {{ r.stage === 'research' ? '独立研究' : '交叉质询' }}
                    </el-tag>
                  </div>
                  <div class="report-view">{{ r.content?.view || r.content?.comments || '' }}</div>
                  <div v-if="r.content?.score" class="report-score">
                    评分: <span class="score-value">{{ r.content.score }}</span><span class="score-max">/10</span>
                  </div>
                  <div v-if="r.content?.concerns?.length" class="report-concerns">
                    <div class="concerns-title">⚠ 风险关注</div>
                    <div v-for="(c, i) in r.content.concerns" :key="i" class="concern-item">{{ c }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 最终报告 -->
            <div v-if="finalReport" class="final-report">
              <div class="reports-subtitle">
                <span class="reports-subtitle-icon">🏆</span>综合研究报告
              </div>
              <div class="scores-grid">
                <div class="score-card">
                  <div class="score-label">基本面</div>
                  <div class="score-num" :style="{color: scoreColor(finalReport.fundamental_score)}">{{ finalReport.fundamental_score }}</div>
                </div>
                <div class="score-card">
                  <div class="score-label">技术面</div>
                  <div class="score-num" :style="{color: scoreColor(finalReport.technical_score)}">{{ finalReport.technical_score }}</div>
                </div>
                <div class="score-card">
                  <div class="score-label">情绪面</div>
                  <div class="score-num" :style="{color: scoreColor(finalReport.sentiment_score)}">{{ finalReport.sentiment_score }}</div>
                </div>
                <div class="score-card overall">
                  <div class="score-label">综合评分</div>
                  <div class="score-num" :style="{color: scoreColor(finalReport.overall_score)}">{{ finalReport.overall_score }}</div>
                </div>
              </div>

              <div class="recommendation-row">
                <div class="rec-item">
                  <span class="rec-label">综合建议</span>
                  <el-tag :type="recType(finalReport.recommendation)" round>{{ finalReport.recommendation }}</el-tag>
                </div>
                <div class="rec-item">
                  <span class="rec-label">目标价区间</span>
                  <span class="rec-value">{{ finalReport.target_price_low ? `¥${finalReport.target_price_low} - ¥${finalReport.target_price_high}` : '未给出' }}</span>
                </div>
              </div>

              <div v-if="finalReport.consensus?.length" class="report-section-inner">
                <div class="section-title section-title-consensus">✓ 共识点</div>
                <div v-for="(c, i) in finalReport.consensus" :key="i" class="section-item consensus">{{ c }}</div>
              </div>
              <div v-if="finalReport.divergences?.length" class="report-section-inner">
                <div class="section-title section-title-divergence">⚡ 分歧点</div>
                <div v-for="(d, i) in finalReport.divergences" :key="i" class="section-item divergence">{{ d }}</div>
              </div>
              <div v-if="finalReport.risk_factors?.length" class="report-section-inner">
                <div class="section-title section-title-risk">⚠ 风险因素</div>
                <div v-for="(r, i) in finalReport.risk_factors" :key="i" class="section-item risk">{{ r }}</div>
              </div>
              <div v-if="finalReport.full_report" class="full-report-box">
                <div class="section-title">完整报告</div>
                <div class="report-markdown">{{ finalReport.full_report }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加/编辑分析师弹窗 -->
    <el-dialog
      v-model="showAnalystDialog"
      :title="editingAnalystId ? '编辑分析师' : '添加分析师'"
      width="560px"
      destroy-on-close
    >
      <div class="curl-section">
        <div class="curl-section-header">
          <span class="curl-icon">🔗</span>
          <span class="curl-section-title">CURL一键导入</span>
        </div>
        <el-input
          v-model="curlInput"
          type="textarea"
          :rows="3"
          placeholder="粘贴 curl 命令，自动解析 API 配置..."
        />
        <div class="curl-actions">
          <el-button
            size="small"
            type="primary"
            :loading="curlParsing"
            @click="parseCurl"
          >解析curl</el-button>
          <span v-if="curlResult" :class="['curl-msg', curlOk ? 'ok' : 'err']">{{ curlResult }}</span>
        </div>
      </div>

      <el-form label-position="top" size="small" style="margin-top:16px">
        <el-form-item label="名称" required>
          <el-input v-model="analystForm.name" placeholder="如：巴菲特" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="角色">
              <el-select v-model="analystForm.role" style="width:100%">
                <el-option label="价值投资" value="value" />
                <el-option label="短线博弈" value="game" />
                <el-option label="技术分析" value="tech" />
                <el-option label="量化分析" value="quant" />
                <el-option label="综合首席" value="overall" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="头像">
              <div class="avatar-picker">
                <div class="avatar-selected" :style="{ background: roleBg(analystForm.role) }">{{ analystForm.avatar }}</div>
                <div class="avatar-grid">
                  <span v-for="e in emojiList" :key="e" class="avatar-emoji" :class="{active: analystForm.avatar===e}" @click="analystForm.avatar=e">{{ e }}</span>
                </div>
              </div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="模型来源">
              <el-select v-model="analystForm.provider" style="width:100%">
                <el-option label="DeepSeek" value="deepseek" />
                <el-option label="OpenAI" value="openai" />
                <el-option label="通义千问" value="qwen" />
                <el-option label="智谱" value="zhipu" />
                <el-option label="Claude" value="claude" />
                <el-option label="Gemini" value="gemini" />
                <el-option label="Ollama" value="ollama" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="模型名称">
              <el-input v-model="analystForm.model_name" placeholder="deepseek-chat">
                <template #append>
                  <el-button :loading="modelsLoading" @click="fetchModels" title="获取模型列表">
                    <el-icon><Refresh /></el-icon>
                  </el-button>
                </template>
              </el-input>
              <div v-if="modelList.length" class="model-list">
                <el-tag v-for="m in modelList" :key="m" size="small" :type="m === analystForm.model_name ? 'primary' : 'info'" class="model-tag" @click="analystForm.model_name = m">{{ m }}</el-tag>
              </div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="API Base">
          <el-input v-model="analystForm.api_base" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="analystForm.api_key" type="password" show-password placeholder="sk-..." />
        </el-form-item>
        <el-form-item label="系统提示词">
          <el-input v-model="analystForm.system_prompt" type="textarea" :rows="4" placeholder="你是一位资深投资分析师..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAnalystDialog = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="saveAnalyst">保存</el-button>
      </template>
    </el-dialog>

    <!-- 发起研究弹窗 -->
    <el-dialog v-model="showCreateResearch" title="发起研究" width="420px" destroy-on-close>
      <el-form label-position="top" size="small">
        <el-form-item label="股票代码" required>
          <el-input v-model="researchForm.symbol" placeholder="例如：600519" />
        </el-form-item>
        <el-form-item label="股票名称">
          <el-input v-model="researchForm.stock_name" placeholder="例如：贵州茅台" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateResearch = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="createResearch" :disabled="!researchForm.symbol">创建</el-button>
      </template>
    </el-dialog>
  </MainLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import MainLayout from '../../layout/MainLayout.vue'
import { labApi } from '../../api'

const analysts = ref([])
const tasks = ref([])
const currentTask = ref(null)
const analystReports = ref([])
const finalReport = ref(null)
const actionLoading = ref(false)
const runningId = ref(null)

const showAnalystDialog = ref(false)
const editingAnalystId = ref(null)
const analystForm = ref({
  name: '', role: 'value', avatar: '', provider: 'deepseek',
  api_base: '', api_key: '', model_name: '', system_prompt: '', is_active: true,
})

const emojiList = ['📊','📈','📉','💰','🏦','💼','🎯','🔮','🧠','💡','📚','🎓','🔍','⚡','🚀','🌙','⭐','🌟','💎','🏆','🎖','🥇','🥈','🥉','🏅','🎯','🎲','🎮','🕹','🎰','🧩','🎭','🎨','🎬','🎤','🎧','🎼','🎹','🥁','🎷','🎺','🎸','🪕','🎻','🏰','🗼','🗽','⛪','🕌','🛕','🕍','⛩','🕋','⛲','⛺','🌁','🌃','🏙','🌄','🌅','🌆','🌇','🌉','🌌']

const showCreateResearch = ref(false)
const researchForm = ref({ symbol: '', stock_name: '' })

const curlInput = ref('')
const curlParsing = ref(false)
const curlResult = ref('')
const curlOk = ref(false)
const modelsLoading = ref(false)
const modelList = ref([])

const workflowStages = [
  { key: 'init', label: '初始化' },
  { key: 'research', label: '独立研究' },
  { key: 'discuss', label: '交叉质询' },
  { key: 'report', label: '综合报告' },
  { key: 'done', label: '完成' },
]
const stageOrder = ['init', 'research', 'discuss', 'report', 'done']

const ROLE_COLORS = {
  value: '#e6a23c',
  game: '#f56c6c',
  tech: '#409eff',
  quant: '#909399',
  overall: '#67c23a',
}
const ROLE_LABELS = { value: '价值投资', game: '短线博弈', tech: '技术分析', quant: '量化分析', overall: '综合首席' }

function roleLabel(r) { return ROLE_LABELS[r] || r }
function roleColor(r) { return ROLE_COLORS[r] || '#909399' }
function roleBg(r) { return roleColor(r) + '18' }

function statusLabel(s) {
  return s === 'pending' ? '待执行' : s === 'running' ? '研究中' : s === 'completed' ? '已完成' : '失败'
}
function statusTagType(s) {
  return s === 'completed' ? 'success' : s === 'running' ? 'primary' : s === 'failed' ? 'danger' : 'info'
}
function stageLabel(s) {
  return s === 'research' ? '独立研究' : s === 'discuss' ? '交叉质询' : s === 'report' ? '综合报告' : s === 'done' ? '完成' : '初始化'
}
function formatDate(t) { return t ? new Date(t).toLocaleString() : '' }
function scoreColor(s) { return s >= 7 ? '#67c23a' : s >= 5 ? '#e6a23c' : '#f56c6c' }
function recType(r) {
  if (!r) return 'info'
  if (r.includes('强烈推荐') || r.includes('推荐')) return 'success'
  if (r.includes('回避') || r.includes('谨慎')) return 'danger'
  return 'warning'
}

function isStageDone(key) {
  if (!currentTask.value) return false
  const currentIdx = stageOrder.indexOf(currentTask.value.stage)
  const checkIdx = stageOrder.indexOf(key)
  return checkIdx < currentIdx || currentTask.value.status === 'completed'
}

function onRowClick(row) {
  if (row) viewReport(row)
}

const analystsLoading = ref(false)
const tasksLoading = ref(false)

async function loadAnalysts() {
  analystsLoading.value = true
  try { analysts.value = await labApi.analysts() } catch { analysts.value = [] }
  finally { analystsLoading.value = false }
}

async function loadTasks() {
  tasksLoading.value = true
  try { tasks.value = await labApi.researchList() } catch { tasks.value = [] }
  finally { tasksLoading.value = false }
}

function openAddAnalyst() {
  editingAnalystId.value = null
  analystForm.value = {
    name: '', role: 'value', avatar: '', provider: 'deepseek',
    api_base: '', api_key: '', model_name: '', system_prompt: '', is_active: true,
  }
  curlInput.value = ''
  curlResult.value = ''
  showAnalystDialog.value = true
}

function openEditAnalyst(a) {
  editingAnalystId.value = a.id
  analystForm.value = { ...a }
  curlInput.value = ''
  curlResult.value = ''
  showAnalystDialog.value = true
}

async function saveAnalyst() {
  if (!analystForm.value.name) return ElMessage.warning('请输入名称')
  actionLoading.value = true
  try {
    if (editingAnalystId.value) {
      await labApi.updateAnalyst(editingAnalystId.value, analystForm.value)
    } else {
      await labApi.createAnalyst(analystForm.value)
    }
    ElMessage.success('保存成功')
    showAnalystDialog.value = false
    await loadAnalysts()
  } finally { actionLoading.value = false }
}

async function toggleActive(a) {
  try {
    await labApi.updateAnalyst(a.id, { is_active: a.is_active })
  } catch {
    a.is_active = !a.is_active
  }
}

async function fetchModels() {
  if (!analystForm.value.api_base) { ElMessage.warning('请先填写 API 地址'); return }
  modelsLoading.value = true
  modelList.value = []
  try {
    const r = await labApi.fetchModels({ api_base: analystForm.value.api_base, api_key: analystForm.value.api_key })
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

async function deleteAnalyst(a) {
  try { await ElMessageBox.confirm(`确定删除「${a.name}」？`, '确认', { type: 'warning' }) } catch { return }
  await labApi.deleteAnalyst(a.id)
  ElMessage.success('已删除')
  await loadAnalysts()
}

async function viewReport(row) {
  const detail = await labApi.researchDetail(row.id)
  currentTask.value = detail
  analystReports.value = detail.analyst_reports || []
  finalReport.value = detail.final_report || null
}

async function runResearch(row) {
  runningId.value = row.id
  ElMessage.info('研究开始，多个AI分析师正在协作分析...')
  try {
    const d = await labApi.runResearch(row.id)
    if (d.success) {
      ElMessage.success('研究完成')
    } else {
      ElMessage.error(d.error || '研究失败')
    }
    await loadTasks()
    await viewReport(row)
  } finally { runningId.value = null }
}

async function deleteTask(row) {
  try { await ElMessageBox.confirm('确定删除该研究任务？', '确认', { type: 'warning' }) } catch { return }
  await labApi.deleteResearch(row.id)
  ElMessage.success('已删除')
  if (currentTask.value?.id === row.id) {
    currentTask.value = null
    analystReports.value = []
    finalReport.value = null
  }
  await loadTasks()
}

async function createResearch() {
  actionLoading.value = true
  try {
    const d = await labApi.createResearch(researchForm.value)
    ElMessage.success('任务已创建')
    showCreateResearch.value = false
    researchForm.value = { symbol: '', stock_name: '' }
    await loadTasks()
    if (d.id) await viewReport({ id: d.id })
  } finally { actionLoading.value = false }
}

async function parseCurl() {
  if (!curlInput.value.trim()) return
  curlParsing.value = true
  curlResult.value = ''
  try {
    const data = await labApi.parseCurl(curlInput.value.trim())
    if (data.api_key) {
      if (data.api_base) analystForm.value.api_base = data.api_base
      if (data.api_key) analystForm.value.api_key = data.api_key
      if (data.model_name || data.model) analystForm.value.model_name = data.model_name || data.model
      if (data.base_url) analystForm.value.api_base = data.base_url
      if (data.provider) analystForm.value.provider = data.provider
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

onMounted(async () => {
  await Promise.all([loadAnalysts(), loadTasks()])
})
</script>

<style scoped>
.research-page {
  --r-radius: 12px;
  --r-radius-sm: 8px;
  --r-shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04);
  --r-shadow-md: 0 2px 12px rgba(0, 0, 0, 0.06);
  --r-shadow-lg: 0 4px 20px rgba(0, 0, 0, 0.08);
  --r-transition: all 0.2s ease;

  height: 100%;
  display: flex;
  flex-direction: column;
}

.page-header {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.page-title {
  font-size: 22px;
  margin: 0;
  font-weight: 700;
  color: var(--el-text-color-primary);
  letter-spacing: -0.3px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 4px 0 0;
  letter-spacing: 0.2px;
}

.two-col {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

/* ---- 通用面板头 ---- */
.col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
.col-title {
  font-weight: 600;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.col-title-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* ---- 左侧 ---- */
.col-left {
  width: 30%;
  min-width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--r-radius);
  overflow: hidden;
}
.analyst-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}
.analyst-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--r-radius);
  padding: 14px;
  margin-bottom: 8px;
  transition: var(--r-transition);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  background: var(--el-bg-color);
}
.analyst-card:hover {
  box-shadow: var(--r-shadow-md);
  border-color: var(--el-border-color);
  transform: translateY(-1px);
}
.analyst-card.inactive {
  opacity: 0.55;
}
.analyst-card-body {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.analyst-avatar {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
  position: relative;
}
.analyst-avatar-emoji {
  position: relative;
  z-index: 1;
}
.analyst-role-dot {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid var(--el-bg-color);
  z-index: 2;
}
.analyst-info {
  min-width: 0;
}
.analyst-name {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.analyst-role-row {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 2px;
}
.analyst-role-dot-inline {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.analyst-role-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.analyst-meta {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-top: 1px;
}
.analyst-card-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.analyst-empty {
  text-align: center;
  padding: 40px 20px;
}
.analyst-empty-icon {
  font-size: 40px;
  margin-bottom: 10px;
  opacity: 0.5;
}
.analyst-empty-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.analyst-empty-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

/* ---- 右侧 ---- */
.col-right {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.task-table {
  margin-bottom: 16px;
}
.bold {
  font-weight: 600;
}

/* ---- 报告区域 ---- */
.report-section {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--r-radius);
  padding: 24px;
  flex: 1;
  overflow-y: auto;
}
.report-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.report-section-title-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.reports-title {
  font-weight: 700;
  font-size: 18px;
  color: var(--el-text-color-primary);
}
.reports-stock-name {
  font-weight: 500;
  font-size: 15px;
  color: var(--el-text-color-secondary);
}
.reports-label {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}
.reports-subtitle {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.reports-subtitle-icon {
  font-size: 15px;
}

/* ---- 工作流进度条 ---- */
.workflow-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  background: var(--el-fill-color-lighter);
  border-radius: var(--r-radius);
  padding: 22px 28px;
  margin-bottom: 20px;
  position: relative;
}
.stage {
  text-align: center;
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.stage-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-bg-color);
  font-weight: 700;
  font-size: 13px;
  border: 2px solid var(--el-border-color);
  transition: all 0.3s;
  position: relative;
  z-index: 1;
}
.stage.active .stage-icon {
  background: var(--el-color-primary);
  color: #fff;
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 5px var(--el-color-primary-light-8);
}
.stage.done .stage-icon {
  background: var(--el-color-success);
  color: #fff;
  border-color: var(--el-color-success);
}
.stage-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 500;
}
.stage.active .stage-label {
  color: var(--el-color-primary);
  font-weight: 700;
}
.stage.done .stage-label {
  color: var(--el-color-success);
}
.stage-line {
  position: absolute;
  top: 18px;
  left: calc(50% + 18px);
  right: calc(-50% + 18px);
  height: 2px;
  background: var(--el-border-color);
  z-index: 0;
}
.stage-line.done {
  background: var(--el-color-success);
}

/* ---- 分析师报告 ---- */
.reports-grid {
  margin-bottom: 24px;
}
.reports-columns {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.report-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--r-radius);
  padding: 16px;
  background: var(--el-bg-color);
  transition: var(--r-transition);
}
.report-card:hover {
  box-shadow: var(--r-shadow-sm);
  border-color: var(--el-border-color);
}
.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.report-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}
.report-role-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.report-role {
  font-weight: 600;
  font-size: 14px;
}
.report-role.value { color: #e6a23c; }
.report-role.game { color: #f56c6c; }
.report-role.tech { color: #409eff; }
.report-role.quant { color: #909399; }
.report-role.overall { color: #67c23a; }
.report-view {
  font-size: 13px;
  line-height: 1.8;
  margin-bottom: 10px;
  color: var(--el-text-color-regular);
}
.report-score {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.score-value {
  font-weight: 700;
  font-size: 17px;
  color: var(--el-color-primary);
}
.score-max {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
.report-concerns {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.concerns-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  font-weight: 500;
}
.concern-item {
  font-size: 12px;
  color: var(--el-color-warning);
  line-height: 1.8;
}

/* ---- 最终报告 ---- */
.final-report {
  border: 2px solid var(--el-color-primary-light-5);
  border-radius: var(--r-radius);
  padding: 24px;
  background: var(--el-bg-color);
}
.scores-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 20px;
}
.score-card {
  text-align: center;
  padding: 20px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: var(--r-radius);
  transition: var(--r-transition);
}
.score-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--r-shadow-sm);
}
.score-card.overall {
  background: var(--el-color-primary-light-9);
}
.score-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  font-weight: 500;
}
.score-num {
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
}
.recommendation-row {
  display: flex;
  gap: 28px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  padding: 14px 16px;
  background: var(--el-fill-color-lighter);
  border-radius: var(--r-radius-sm);
}
.rec-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rec-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  font-weight: 500;
}
.rec-value {
  font-size: 14px;
  font-weight: 600;
}
.report-section-inner {
  margin-bottom: 16px;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.section-title-consensus { color: #67c23a; }
.section-title-divergence { color: #e6a23c; }
.section-title-risk { color: #f56c6c; }
.section-item {
  font-size: 13px;
  line-height: 2;
  padding-left: 4px;
}
.section-item.consensus {
  color: #67c23a;
}
.section-item.divergence {
  color: #e6a23c;
}
.section-item.risk {
  color: #f56c6c;
}
.full-report-box {
  margin-top: 18px;
}
.report-markdown {
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
  background: var(--el-fill-color-lighter);
  padding: 18px;
  border-radius: var(--r-radius);
  max-height: 500px;
  overflow-y: auto;
}

/* ---- CURL 导入 ---- */
.curl-section {
  background: var(--el-fill-color-lighter);
  border-radius: var(--r-radius);
  padding: 16px;
}
.curl-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.curl-icon {
  font-size: 16px;
}
.curl-section-title {
  font-weight: 600;
  font-size: 13px;
}
.curl-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}
.curl-msg {
  font-size: 12px;
}
.curl-msg.ok { color: #67c23a; }
.curl-msg.err { color: #f56c6c; }

@media (max-width: 820px) {
  .two-col {
    flex-direction: column;
  }
  .col-left {
    width: 100%;
    min-width: 0;
    max-height: 300px;
  }
  .reports-columns {
    grid-template-columns: 1fr;
  }
  .scores-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Avatar picker */
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
  border: 2px solid var(--el-border-color);
  border-radius: 12px;
  transition: var(--r-transition);
}
.avatar-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  max-height: 120px;
  overflow-y: auto;
  padding: 4px;
  background: var(--el-fill-color-lighter);
  border-radius: var(--r-radius-sm);
}
.avatar-emoji {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.15s;
}
.avatar-emoji:hover {
  background: var(--el-border-color-lighter);
  transform: scale(1.2);
}
.avatar-emoji.active {
  background: var(--el-color-primary-light-9);
  outline: 2px solid var(--el-color-primary);
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
