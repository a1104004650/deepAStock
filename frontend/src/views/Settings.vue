<template>
  <MainLayout>
    <div class="page settings-page">
    <h2 class="page-title">系统设置</h2>
    <el-tabs v-model="tab" class="settings-tabs">
      <!-- 数据源 -->
      <el-tab-pane label="数据源" name="source">
        <el-card shadow="never" class="panel">
          <template #header>
            <div class="panel-head">
              <span>数据源配置（主源 + 备用源 1/2/3 顺序回退）</span>
              <el-button type="primary" size="small" :loading="savingSource" @click="saveSource">保存数据源配置</el-button>
            </div>
          </template>
          <el-form label-width="110px" label-position="left">
            <el-form-item label="主数据源">
              <el-select v-model="sourceForm.primary_source" placeholder="主数据源">
                <el-option v-for="s in sourceOptions" :key="s" :label="sourceLabel(s)" :value="s" />
              </el-select>
              <span class="form-tip">支持组合写法（如 sina+tencent），失败自动切换下一优先级</span>
            </el-form-item>
            <el-form-item v-for="i in 3" :key="i" :label="'备用数据源' + i">
              <el-select v-model="sourceForm['backup_source_' + i]" clearable placeholder="未设置">
                <el-option v-for="s in sourceOptions" :key="s" :label="sourceLabel(s)" :value="s" />
              </el-select>
            </el-form-item>
            <el-form-item label="单源超时(秒)">
              <el-input-number v-model="sourceTimeout" :min="1" :max="60" :step="1" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- 数据库 -->
      <el-tab-pane label="数据库" name="database">
        <el-card shadow="never" class="panel">
          <template #header>
            <div class="panel-head"><span>数据库配置</span></div>
          </template>
          <el-form label-width="110px" label-position="left">
            <el-form-item label="数据库地址">
              <el-input v-model="dbForm.database_url" placeholder="sqlite+aiosqlite:///... 或 postgresql+asyncpg://user:pass@host:port/db" />
            </el-form-item>
            <el-form-item label=" ">
              <el-button @click="testDb" :loading="testingDb">测试连接</el-button>
              <span v-if="dbTest" class="form-tip" :class="dbTest.ok ? 'ok' : 'err'">
                {{ dbTest.ok ? '连接成功' : '连接失败：' + dbTest.error }}
              </span>
            </el-form-item>
            <el-form-item label=" ">
              <el-button type="primary" @click="saveDb" :loading="savingSource">保存数据库配置</el-button>
              <span class="form-tip warn">修改数据库地址后需重启后端生效；重启前请确认目标库表结构已初始化。</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- 关于 / 版本信息 -->
      <el-tab-pane label="关于" name="about">
        <el-card shadow="never" class="panel">
          <template #header>
            <div class="panel-head"><span>版本信息与更新日志</span></div>
          </template>
          <template v-if="aboutInfo">
            <div class="about-row"><span class="about-label">{{ aboutInfo.app }}</span></div>
            <div class="about-row">
              <span class="about-label">当前版本</span>
              <span class="about-val mono">v{{ aboutInfo.version }}</span>
              <el-button size="small" link type="primary" :loading="aboutLoading" @click="loadAbout" style="margin-left:8px">刷新</el-button>
            </div>
            <div class="about-tip">更新日志来源：项目根目录 CHANGELOG.md（按时间倒序）</div>
          </template>
          <el-empty v-else-if="!aboutLoading" description="版本信息加载失败" :image-size="60" />
          <div class="changelog-box">
            <div v-for="sec in parsed" :key="sec.title" class="chg-sec">
              <div class="chg-title">{{ sec.title }}</div>
              <div v-for="(l, i) in sec.lines" :key="i" class="chg-line" :class="{ 'chg-head': l.startsWith('### '), 'chg-bullet': l.trim().startsWith('- '), 'chg-quote': l.trim().startsWith('> ') }">
                {{ l.trim().startsWith('- ') ? l.trim().slice(2) : (l.startsWith('### ') ? l.slice(4) : l) }}
              </div>
            </div>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import MainLayout from '../layout/MainLayout.vue'
import { settingsApi, systemApi } from '../api'

const tab = ref('source')
const sourceOptions = ref(['sina', 'tencent'])
const sourceLabel = (s) => (s === 'sina' ? '新浪财经 (sina)' : '腾讯证券 (tencent)')
const sourceForm = ref({ primary_source: 'sina', backup_source_1: '', backup_source_2: '', backup_source_3: '' })
const sourceTimeout = ref(5)
const savingSource = ref(false)

const dbForm = ref({ database_url: '' })
const dbTest = ref(null)
const testingDb = ref(false)

const aboutInfo = ref(null)
const aboutLoading = ref(false)

async function loadSettings() {
  const s = await settingsApi.get()
  sourceOptions.value = s.source_options || sourceOptions.value
  const eff = s.effective || {}
  sourceForm.value = {
    primary_source: eff.primary_source || 'sina',
    backup_source_1: eff.backup_source_1 || '',
    backup_source_2: eff.backup_source_2 || '',
    backup_source_3: eff.backup_source_3 || ''
  }
  sourceTimeout.value = Number(eff.source_timeout || 5)
  dbForm.value.database_url = eff.database_url || ''
}

async function saveSource() {
  savingSource.value = true
  try {
    await settingsApi.save({
      ...sourceForm.value,
      source_timeout: String(sourceTimeout.value)
    })
    ElMessage.success('数据源配置已保存并生效')
  } finally {
    savingSource.value = false
  }
}

async function saveDb() {
  savingSource.value = true
  try {
    await settingsApi.save({ database_url: dbForm.value.database_url })
    ElMessage.success('数据库地址已保存（重启后生效）')
  } finally {
    savingSource.value = false
  }
}

async function testDb() {
  testingDb.value = true
  try {
    dbTest.value = await settingsApi.testDatabase(dbForm.value.database_url)
  } finally {
    testingDb.value = false
  }
}

async function loadAbout() {
  aboutLoading.value = true
  try {
    aboutInfo.value = await systemApi.changelog()
  } catch {
    aboutInfo.value = null
  } finally {
    aboutLoading.value = false
  }
}

const parsed = computed(() => {
  const txt = (aboutInfo.value && aboutInfo.value.changelog) || ''
  const sections = []
  let cur = null
  for (const raw of txt.split('\n')) {
    const line = raw.replace(/\r$/, '')
    if (line.startsWith('## ')) {
      cur = { title: line.slice(3).trim(), lines: [] }
      sections.push(cur)
    } else if (cur && line.trim()) {
      cur.lines.push(line)
    }
  }
  return sections
})

onMounted(() => {
  loadSettings()
  loadAbout()
})
</script>

<style scoped>
.page { padding: 20px; max-width: 1200px; }
.page-title { font-size: 18px; font-weight: 700; margin: 0 0 16px; }
.panel { border-radius: 10px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; }
.panel-actions { display: flex; gap: 8px; }
.form-tip { color: #909399; font-size: 12px; margin-left: 10px; }
.form-tip.ok { color: #67c23a; }
.form-tip.err { color: #f56c6c; }
.form-tip.warn { color: #e6a23c; }
.mono { font-family: 'Consolas', 'SF Mono', monospace; }

.about-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 14px; }
.about-label { color: #606266; }
.about-val { font-weight: 700; color: #409eff; }
.about-tip { color: #909399; font-size: 12px; margin: 4px 0 12px; }
.changelog-box {
  max-height: 480px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px 16px;
  background: #fafbfc;
}
.chg-sec { margin-bottom: 16px; }
.chg-sec:last-child { margin-bottom: 0; }
.chg-title { font-size: 15px; font-weight: 700; color: #303133; margin-bottom: 6px; }
.chg-head { font-size: 13px; font-weight: 600; color: #409eff; margin-top: 8px; }
.chg-line { font-size: 13px; color: #606266; line-height: 1.75; }
.chg-bullet { padding-left: 14px; position: relative; }
.chg-bullet::before { content: ''; position: absolute; left: 2px; top: 10px; width: 5px; height: 5px; border-radius: 50%; background: #c0c4cc; }
.chg-quote { color: #909399; font-size: 12px; border-left: 2px solid #dcdfe6; padding-left: 8px; margin: 4px 0; }
</style>