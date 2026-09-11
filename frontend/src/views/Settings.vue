<template>
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

      <!-- RSSHub 订阅 -->
      <el-tab-pane label="RSSHub 订阅" name="rss">
        <el-card shadow="never" class="panel">
          <template #header>
            <div class="panel-head">
              <span>订阅源管理（本地 RSSHub 实例，微博 / 公众号 / 股吧 等平台的推送消息，自动存库</span>
              <span style="margin:0 12px 0 4px;color:#909399;font-weight:400">近实时，限频轮询）</span>
              <div class="panel-actions">
                <el-button size="small" @click="pollNow" :loading="polling">
                  <el-icon style="margin-right:4px"><Refresh /></el-icon>立即轮询
                </el-button>
                <el-button size="small" type="primary" @click="openDialog()">新增订阅源</el-button>
              </div>
            </div>
          </template>

          <div class="rss-status">
            <el-tag :type="rssStatus.enabled ? 'success' : 'info'" size="small">
              {{ rssStatus.enabled ? 'RSSHub 已启用' : 'RSSHub 未启用' }}
            </el-tag>
            <span class="form-tip">实例：{{ rssStatus.base || '未设置' }} · 订阅源 {{ sources.length }} 个 · 入库消息 {{ itemTotal }} 条 · 上次轮询结果：{{ lastPollText }}</span>
          </div>

          <el-table :data="sources" size="small" empty-text="暂无订阅源" class="rss-table">
            <el-table-column prop="name" label="名称" min-width="120" />
            <el-table-column prop="platform" label="平台" width="90">
              <template #default="{ row }">{{ platformLabel(row.platform) }}</template>
            </el-table-column>
            <el-table-column label="订阅地址" min-width="240">
              <template #default="{ row }">
                <span class="route">{{ row.url || (rssStatus.base || '') + (row.route || '') }}</span>
              </template>
            </el-table-column>
            <el-table-column label="关注标签" min-width="140">
              <template #default="{ row }">
                <el-tag v-for="t in (row.tags || [])" :key="t" size="small" type="info" class="tag-gap" style="margin-right:4px">{{ t }}</el-tag>
                <span v-if="!row.tags || !row.tags.length" style="color:#c0c4cc">-</span>
              </template>
            </el-table-column>
            <el-table-column label="间隔(秒)" prop="interval_sec" width="86" />
            <el-table-column label="启用" width="70">
              <template #default="{ row }">
                <el-switch :model-value="row.enabled" size="small" @change="(v) => toggle(row, v)" />
              </template>
            </el-table-column>
            <el-table-column label="最近轮询" width="150">
              <template #default="{ row }">
                <span class="form-tip" :class="row.last_status ? (row.last_status.startsWith('ok') ? 'ok' : 'err') : ''">
                  {{ row.last_poll ? row.last_poll.slice(5, 16) : '未轮询' }}
                  <template v-if="row.last_status">{{ row.last_status }}</template>
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
                <el-button link type="danger" size="small" @click="removeSource(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="items-head">
            <span>已订阅推送（最新 {{ previewItems.length }} 条）</span>
          </div>
          <div class="rss-items">
            <div v-for="it in previewItems" :key="it.id" class="rss-item">
              <span class="rss-item-tag">{{ sourceName(it.source_id) }}</span>
              <a class="rss-item-title" v-if="it.link" :href="it.link" target="_blank" rel="noopener">{{ it.title }}</a>
              <span v-else class="rss-item-title">{{ it.title }}</span>
              <span class="rss-item-time">{{ fmtTime(it.pub_time) }}</span>
            </div>
            <el-empty v-if="!previewItems.length" description="暂无推送消息，请新增订阅源后点击「立即轮询」" :image-size="70" />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 新增/编辑订阅源 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑订阅源' : '新增订阅源'" width="560px">
      <el-form label-width="90px" label-position="left">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：某游资微博 / 某公众号" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="form.platform" @change="onPlatform">
            <el-option v-for="(p, key) in platformMap" :key="key" :label="p.label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="RSSHub 路径">
          <el-input v-model="form.route" placeholder="/weibo/user/1234567890（将拼接到 RSSHUB_BASE）" />
        </el-form-item>
        <el-form-item label="完整 URL">
          <el-input v-model="form.url" placeholder="可选，若填写则优先使用完整 URL" />
          <div class="form-tip" style="width:100%">
            微博用户 <code>/weibo/user/{uid}</code> · 微博热搜 <code>/weibo/search/hot</code> ·
            公众号(搜狗) <code>/wechat/sogou/{关键词}</code> · 东财股吧 <code>/eastmoney/guba/{代码}</code>，
            具体路由以实际部署的 RSSHub /routes 为准
          </div>
        </el-form-item>
        <el-form-item label="关注标签">
          <el-input v-model="form.tagsText" :placeholder="'逗号分隔，如：600519,茅台,跟单'" />
        </el-form-item>
        <el-form-item label="轮询间隔">
          <el-input-number v-model="form.interval_sec" :min="10" :max="1800" :step="10" />
          <span class="form-tip" style="margin-left:10px">秒，最小 10 秒，限频保护</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="过滤 ST">
          <el-switch v-model="form.filter_st" />
          <span class="form-tip" style="margin-left:10px">自动过滤标题含 ST / *ST 的消息</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="form.url || form.route" @click="testFeed" :loading="testing">
          测试订阅地址
        </el-button>
        <span v-if="testResult" class="form-tip" :class="testResult.ok ? 'ok' : 'err'" style="margin-right:10px">
          {{ testResult.ok ? '可解析 ' + testResult.count + ' 条' : '失败：' + testResult.error }}
        </span>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSourceDialog">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { settingsApi, rssApi, systemApi } from '../api'

const tab = ref('source')
const sourceOptions = ref(['sina', 'tencent'])
const sourceLabel = (s) => (s === 'sina' ? '新浪财经 (sina)' : '腾讯证券 (tencent)')
const sourceForm = ref({ primary_source: 'sina', backup_source_1: '', backup_source_2: '', backup_source_3: '' })
const sourceTimeout = ref(5)
const savingSource = ref(false)

const dbForm = ref({ database_url: '' })
const dbTest = ref(null)
const testingDb = ref(false)

const platformMap = {
  weibo: { label: '微博', route: '/weibo/user/{uid}' },
  wechat: { label: '微信公众号', route: '/wechat/sogou/{关键词}' },
  guba: { label: '东方财富股吧', route: '/eastmoney/guba/{代码}' },
  generic: { label: '其他 / 自定义', route: '' }
}
const platformLabel = (p) => (platformMap[p] || platformMap.generic).label

const sources = ref([])
const previewItems = ref([])
const itemTotal = ref(0)
const rssStatus = ref({ enabled: true, base: '' })
const lastPollText = ref('待轮询')
const polling = ref(false)

const dialogVisible = ref(false)
const editing = ref(false)
const form = ref({ name: '', platform: 'weibo', route: '', url: '', tagsText: '', interval_sec: 30, enabled: true, filter_st: true })
const testing = ref(false)
const testResult = ref(null)
const firstLoad = ref(false)

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
  rssStatus.value = { enabled: eff.rsshub_enabled === '1', base: eff.rsshub_base || '', poll: eff.rsshub_poll_seconds || '30' }
}

async function saveSource() {
  savingSource.value = true
  try {
    await settingsApi.save({
      ...sourceForm.value,
      source_timeout: String(sourceTimeout.value),
      rsshub_enabled: rssStatus.value.enabled ? '1' : '0',
      rsshub_base: rssStatus.value.base
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

function onPlatform() {
  form.value.route = platformMap[form.value.platform].route
}
function openDialog(row) {
  editing.value = !!row
  testResult.value = null
  form.value = {
    name: row?.name || '',
    platform: row?.platform || 'weibo',
    route: row?.route || '',
    url: row?.url || '',
    tagsText: (row?.tags || []).join(','),
    interval_sec: row?.interval_sec || 30,
    enabled: row?.enabled ?? true,
    filter_st: row?.filter_st ?? true
  }
  dialogVisible.value = true
}

function testUrl() {
  return form.value.url || ((rssStatus.value.base || '') + (form.value.route || ''))
}

async function testFeed() {
  const u = testUrl()
  if (!u) { ElMessage.warning('请先填写订阅地址'); return }
  testing.value = true
  try {
    testResult.value = await rssApi.testFeed(u)
  } finally {
    testing.value = false
  }
}

async function saveSourceDialog() {
  if (!form.value.name) { ElMessage.warning('请填写订阅源名称'); return }
  if (!form.value.route && !form.value.url) { ElMessage.warning('请填写 RSSHub 路径或完整 URL'); return }
  const payload = {
    name: form.value.name,
    platform: form.value.platform,
    route: form.value.route || null,
    url: form.value.url || null,
    tags: form.value.tagsText.split(/[,，\s]+/).filter(Boolean),
    interval_sec: form.value.interval_sec,
    enabled: form.value.enabled,
    filter_st: form.value.filter_st
  }
  if (editing.value) {
    await rssApi.updateSource(editing.value.id, payload)
    ElMessage.success('订阅源已更新')
  } else {
    await rssApi.createSource(payload)
    ElMessage.success('订阅源已创建')
  }
  dialogVisible.value = false
  await loadRss()
}

async function toggle(row, v) {
  await rssApi.updateSource(row.id, { enabled: v })
  ElMessage.success(v ? '订阅源已启用' : '订阅源已停用')
  await loadRss()
}

async function removeSource(row) {
  await ElMessageBox.confirm(`确认删除订阅源「${row.name}」及其已入库消息？`, '删除确认', { type: 'warning' })
  await rssApi.deleteSource(row.id)
  ElMessage.success('已删除')
  await loadRss()
}

async function pollNow() {
  polling.value = true
  try {
    const r = await rssApi.poll()
    lastPollText.value = `轮询 ${r.polled} 个源，新增 ${r.added} 条${r.errors && r.errors.length ? '，' + r.errors.length + ' 个失败' : ''}`
    ElMessage.success(lastPollText.value)
    await loadRss()
  } finally {
    polling.value = false
  }
}

const sourceName = (id) => {
  const s = sources.value.find((x) => x.id === id)
  return s ? s.name : ('#' + id)
}

const fmtTime = (t) => (t ? t.slice(5, 16) : '')

async function loadRss() {
  sources.value = await rssApi.sources()
  const sys = await systemApi.status().catch(() => null)
  if (sys && sys.rsshub) rssStatus.value = { enabled: sys.rsshub.enabled, base: sys.rsshub.base }
  previewItems.value = await rssApi.items({ limit: 30 })
  itemTotal.value = 30
}

let timer = null
onMounted(async () => {
  await loadSettings()
  await loadRss()
  timer = setInterval(loadRss, 60000)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
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
.rss-status { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.rss-table { margin-bottom: 12px; }
.route { font-family: Consolas, monospace; font-size: 12px; color: #606266; word-break: break-all; }
.tag-gap { margin-right: 4px; }
.items-head { font-size: 14px; font-weight: 600; margin: 10px 0 8px; }
.rss-items { max-height: 320px; overflow-y: auto; border: 1px solid #ebeef5; border-radius: 8px; padding: 4px 10px; }
.rss-item { display: flex; align-items: baseline; gap: 10px; padding: 7px 0; border-bottom: 1px dashed #f0f2f5; font-size: 13px; }
.rss-item:last-child { border-bottom: none; }
.rss-item-tag { flex-shrink: 0; color: #409eff; font-size: 12px; background: rgba(64,158,255,.08); border-radius: 4px; padding: 1px 6px; max-width: 120px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.rss-item-title { flex: 1; color: #303133; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; text-decoration: none; }
.rss-item-title:hover { color: #409eff; }
.rss-item-time { flex-shrink: 0; color: #909399; font-size: 12px; }
</style>