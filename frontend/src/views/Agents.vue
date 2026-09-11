<template>
  <MainLayout>
    <div class="page">
      <div class="flex gap" style="align-items:center;margin-bottom:10px">
        <h2 style="font-size:18px">智能体中心</h2>
        <el-button size="small" type="primary" @click="openCreate"><el-icon><Plus /></el-icon>自定义智能体</el-button>
      </div>

      <el-alert
        type="success"
        :closable="false"
        show-icon
        title="已预置 AMD DeepSeek-V4-Flash 端点，三个默认智能体（投研 / 短线 / 波段）可直接使用；如需换用其他 OpenAI 兼容 API（DeepSeek / 通义 / 智谱 / Ollama / OpenAI）或 Gemini / Claude，在下方配置中选择对应服务商并按格式填写即可。"
        class="mb8"
      />

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="智能体类型说明：research=价值/基本面投研；short_term=短线情绪；swing=波段趋势；custom=完全由你的系统提示词驱动的自定义智能体，可用于个股AI分析、每日复盘、选股池与模拟交易账户绑定。AI 大盘分析入口已移至大盘看板。"
        class="mb8"
      />

      <el-row :gutter="10">
        <el-col v-for="a in agents" :key="a.id" :xs="24" :sm="12" :md="8">
          <div class="card">
            <div class="flex between" style="align-items:center">
              <span class="fs14 bold">{{ a.icon ? a.icon + ' ' : '' }}{{ a.name }}</span>
              <el-tag size="small" :type="a.is_active ? 'success' : 'info'">{{ a.is_active ? '启用' : '停用' }}</el-tag>
            </div>
            <div class="fs12" style="color:#909399">{{ a.agent_type }}</div>
            <div class="fs12 mt8" style="color:#606266;min-height:60px">{{ a.system_prompt_slice || (a.system_prompt || '').slice(0, 80) }}…</div>
            <el-divider style="margin:8px 0" />
            <div class="flex between">
              <span class="fs12" style="color:#909399">模型：{{ a.model_name || 'deepseek-chat' }}</span>
              <div class="flex gap">
                <el-button size="small" type="primary" link @click="openEdit(a)"><el-icon><Edit /></el-icon>配置</el-button>
                <el-popconfirm title="删除该智能体？" @confirm="removeAgent(a)">
                  <template #reference>
                    <el-button size="small" type="danger" link>删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      <el-card shadow="never" class="mt8">
        <template #header>运行记录</template>
        <el-table :data="runs" size="small">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="agent_config_id" label="Agent ID" width="90" />
          <el-table-column prop="task_type" label="任务" width="130" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'success' ? 'success' : 'danger'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="duration_ms" label="耗时(ms)" width="100" align="right" />
          <el-table-column prop="created_at" label="时间" />
        </el-table>
      </el-card>

      <!-- 调用次数图表：周维度 / 小时维度 -->
      <el-row :gutter="10" class="mt8" v-if="statsTotal > 0">
        <el-col :xs="24" :sm="12">
          <el-card shadow="never">
            <template #header>近 {{ statsDays }} 天调用次数 · 按星期（共 {{ statsTotal }} 次）</template>
            <BarChart :data="stats.by_weekday || []" height="220px" />
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-card shadow="never">
            <template #header>近 {{ statsDays }} 天调用次数 · 按小时</template>
            <BarChart :data="stats.by_hour || []" height="220px" />
          </el-card>
        </el-col>
      </el-row>

      <!-- 配置弹窗 -->
      <el-dialog :title="editingId ? '编辑智能体配置' : '创建自定义智能体'" v-model="dialog" width="560">
        <el-form label-width="110px">
          <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="类型">
            <el-select v-model="form.agent_type" style="width:100%">
              <el-option value="research" label="research（投研：价值/基本面）" />
              <el-option value="short_term" label="short_term（短线：情绪/题材）" />
              <el-option value="swing" label="swing（波段：趋势/形态）" />
              <el-option value="custom" label="custom（自定义：全由你的系统提示词驱动）" />
            </el-select>
          </el-form-item>
          <el-form-item label="服务商">
            <el-select v-model="form.provider" style="width:100%" @change="applyProviderPreset">
              <el-option value="" label="自动识别（按 API 地址/模型名推断）" />
              <el-option value="deepseek" label="DeepSeek（api.deepseek.com）" />
              <el-option value="qwen" label="通义千问 DashScope（dashscope.aliyuncs.com）" />
              <el-option value="zhipu" label="智谱 GLM（open.bigmodel.cn）" />
              <el-option value="openai" label="OpenAI / OpenRouter 兼容" />
              <el-option value="ollama" label="Ollama 本地（无需 Key）" />
              <el-option value="gemini" label="Google Gemini（原生接口）" />
              <el-option value="claude" label="Anthropic Claude（原生接口）" />
            </el-select>
          </el-form-item>
          <el-form-item label="API 地址 (Base URL)"><el-input v-model="form.api_base" placeholder="如 https://api.deepseek.com/v1" /></el-form-item>
          <el-form-item label="API Key"><el-input v-model="form.api_key" type="password" show-password placeholder="sk-...（Ollama 可留空）" /></el-form-item>
          <el-form-item label="模型"><el-input v-model="form.model_name" placeholder="deepseek-chat" /></el-form-item>
          <el-form-item label="温度"><el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" /></el-form-item>
          <el-form-item label="系统提示词">
            <el-input v-model="form.system_prompt" type="textarea" :rows="5" placeholder="可留空使用默认提示词" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialog = false">取消</el-button>
          <el-button type="primary" @click="save">保存</el-button>
        </template>
      </el-dialog>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import MainLayout from '../layout/MainLayout.vue'
import BarChart from '../components/BarChart.vue'
import { agentApi } from '../api'

const agents = ref([])
const runs = ref([])
const stats = ref({ by_weekday: [], by_hour: [] })
const statsTotal = computed(() => stats.value.total || 0)
const statsDays = computed(() => stats.value.days || 30)
const dialog = ref(false)
const editingId = ref(null)
const form = ref(defaultForm())

const PROVIDER_PRESETS = {
  deepseek: { api_base: 'https://api.deepseek.com/v1', model_name: 'deepseek-chat' },
  qwen: { api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model_name: 'qwen-max' },
  zhipu: { api_base: 'https://open.bigmodel.cn/api/paas/v4', model_name: 'glm-4-flash' },
  openai: { api_base: 'https://api.openai.com/v1', model_name: 'gpt-4o-mini' },
  ollama: { api_base: 'http://localhost:11434', model_name: 'qwen2.5:14b' },
  gemini: { api_base: 'https://generativelanguage.googleapis.com', model_name: 'gemini-1.5-flash' },
  claude: { api_base: 'https://api.anthropic.com', model_name: 'claude-sonnet-4-20250514' }
}

function defaultForm() {
  return {
    name: '',
    agent_type: 'custom',
    provider: '',
    api_base: '',
    api_key: '',
    model_name: 'deepseek-chat',
    system_prompt: '',
    temperature: 0.3
  }
}

function applyProviderPreset(p) {
  const preset = PROVIDER_PRESETS[p]
  if (!preset) return
  form.value.api_base = preset.api_base
  form.value.model_name = preset.model_name
}

async function load() {
  const list = await agentApi.list()
  agents.value = list.map((a) => ({ ...a, system_prompt_slice: (a.system_prompt || '').slice(0, 80) }))
  runs.value = await agentApi.runs()
  try { stats.value = await agentApi.runsStats() } catch { stats.value = { by_weekday: [], by_hour: [] } }
}

function openCreate() {
  editingId.value = null
  form.value = defaultForm()
  dialog.value = true
}

function openEdit(a) {
  editingId.value = a.id
  form.value = {
    name: a.name || '',
    agent_type: a.agent_type || 'custom',
    provider: a.provider || '',
    api_base: a.api_base || '',
    api_key: a.api_key || '',
    model_name: a.model_name || 'deepseek-chat',
    system_prompt: a.system_prompt || '',
    temperature: a.temperature ?? 0.3
  }
  dialog.value = true
}

async function save() {
  const payload = { ...form.value, system_prompt: form.value.system_prompt || null }
  if (editingId.value) {
    await agentApi.update(editingId.value, payload)
  } else {
    await agentApi.create(payload)
  }
  ElMessage.success('已保存')
  dialog.value = false
  await load()
}

async function removeAgent(a) {
  await agentApi.remove(a.id)
  await load()
}

onMounted(load)
</script>
<style>
.wide-alert {
  width: 480px;
  white-space: pre-wrap;
}
</style>