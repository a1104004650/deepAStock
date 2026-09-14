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

      <!-- RSSHub 订阅 -->
      <el-tab-pane label="RSSHub 订阅" name="rss">
        <el-card shadow="never" class="panel">
          <template #header>
            <div class="panel-head">
              <span>订阅源管理（HTTP 直连 / RSSHub 本地，按分钟轮询增量入库，新消息全局通知）</span>
              <div class="panel-actions">
                <el-button size="small" @click="pollNow" :loading="polling">
                  <el-icon style="margin-right:4px"><Refresh /></el-icon>立即轮询
                </el-button>
                <el-button size="small" type="primary" @click="openDialog()">新增订阅源</el-button>
              </div>
            </div>
          </template>

          <div class="rss-status">
            <div class="rss-base-line">
              <span class="form-tip" style="margin-left:0">本地 RSSHub 参考地址</span>
              <span class="route" style="line-height:28px">http://127.0.0.1:11200（Docker 内 http://rsshub:1200）</span>
            </div>
            <div class="rss-base-line">
              <span class="form-tip" style="margin-left:0">RSSHub 路由文档</span>
              <a class="doc-link" href="https://rsshub-doc.pages.dev/traditional-media.html#cai-xin-wang" target="_blank" rel="noopener">
                https://rsshub-doc.pages.dev/traditional-media.html#cai-xin-wang
              </a>
            </div>
            <div class="rss-base-line">
              <span class="form-tip" style="margin-left:0">微博 Cookie</span>
              <el-input v-model="weiboCookie" size="small" type="textarea" :rows="2" style="width:520px" placeholder="浏览器登录 m.weibo.cn 后 F12 复制任一请求的 Cookie 头整串（微博订阅直连仅在使用 /weibo/user/ 路由时需要）" />
              <el-button size="small" type="primary" :loading="savingRssHub" @click="saveWeiboCookie">保存</el-button>
            </div>
            <span class="form-tip">订阅源 {{ sources.length }} 个 · 入库消息 {{ itemTotal }} 条 · 上次轮询：{{ lastPollText }}</span>
          </div>

          <el-table :data="sources" size="small" empty-text="暂无订阅源" class="rss-table">
            <el-table-column prop="name" label="名称" min-width="120" />
            <el-table-column label="RSS类型" width="112">
              <template #default="{ row }"><el-tag size="small" effect="plain">{{ rssTypeLabel(row.rss_type) }}</el-tag></template>
            </el-table-column>
            <el-table-column label="订阅地址" min-width="240">
              <template #default="{ row }">
                <span class="route">{{ row.url || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="关注标签" min-width="140">
              <template #default="{ row }">
                <el-tag v-for="t in (row.tags || [])" :key="t" size="small" type="info" class="tag-gap" style="margin-right:4px">{{ t }}</el-tag>
                <span v-if="!row.tags || !row.tags.length" style="color:#c0c4cc">-</span>
              </template>
            </el-table-column>
            <el-table-column label="轮询(分钟)" prop="interval_min" width="86" />
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
            <el-table-column label="操作" width="170" fixed="right">
              <template #default="{ row }">
                <el-button link type="success" size="small" :loading="pollingId === row.id" @click="pollSource(row)">轮询</el-button>
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
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑订阅源' : '新增订阅源'" width="620px">
      <el-form label-width="96px" label-position="left">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="给这个源起个名字（可不填，自动识别）" />
        </el-form-item>
        <el-form-item label="RSS类型" required>
          <el-radio-group v-model="form.rss_type">
            <el-radio-button value="http">HTTP/HTTPS 直连</el-radio-button>
            <el-radio-button value="rsshub_local">RSSHub 本地 Docker</el-radio-button>
          </el-radio-group>
          <div class="form-tip" style="display:block;width:100%;margin-left:0;margin-top:6px">
            <template v-if="form.rss_type === 'http'">填写 RSS / Atom / JSON Feed 完整链接，直接抓取。示例：<code>https://www.ithome.com/rss/</code></template>
            <template v-else>填写 RSSHub 接口完整地址（直接粘 URL，不做任何校验）。参考：<code>/36kr/newsflashes</code> · <code>/cls/telegraph</code> · <code>/caixin/latest</code> · <a href="https://rsshub-doc.pages.dev/traditional-media.html#cai-xin-wang" target="_blank" rel="noopener" class="doc-link">官方文档</a></template>
          </div>
        </el-form-item>
        <el-form-item label="订阅地址" required>
          <el-input v-model="form.url" :placeholder="addressPlaceholder">
            <template v-if="form.rss_type === 'rsshub_local'" #prepend>http://127.0.0.1:11200</template>
          </el-input>
          <div class="form-tip" style="display:block;width:100%;margin-left:0;margin-top:6px">
            <template v-if="form.rss_type === 'rsshub_local'">
              只需填 <code>/36kr/newsflashes</code> 这类后缀，系统自动在前面加上本地 RSSHub 地址（左侧「http://127.0.0.1:11200」辅助拼接）。已在新源快速入口提供财联社/金十/财新等炒股相关路由。
            </template>
            <template v-else>
              填写 RSS / Atom / JSON Feed 完整链接，直接抓取。示例：<code>https://www.ithome.com/rss/</code>
            </template>
          </div>
        </el-form-item>
        <el-form-item label="轮询时间">
          <el-input-number v-model="form.interval_min" :min="1" :max="1440" :step="1" />
          <span class="form-tip" style="margin-left:10px">分钟（默认 5 分钟）</span>
        </el-form-item>
        <el-form-item label="关注标签">
          <el-input v-model="form.tagsText" :placeholder="'逗号分隔，普通自定义标签，如：热点,财经,A股'" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="备注（可选）" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="form.url" @click="testFeed" :loading="testing">
          测试地址
        </el-button>
        <span v-if="testResult" class="form-tip" :class="testResult.ok ? 'ok' : 'err'" style="margin-right:10px">
          {{ testResult.ok ? '可解析 ' + testResult.count + ' 条' : '失败：' + testResult.error }}
        </span>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSourceDialog">保存</el-button>
      </template>
    </el-dialog>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import MainLayout from '../layout/MainLayout.vue'
import { settingsApi, rssApi } from '../api'

const tab = ref('source')
const sourceOptions = ref(['sina', 'tencent'])
const sourceLabel = (s) => (s === 'sina' ? '新浪财经 (sina)' : '腾讯证券 (tencent)')
const sourceForm = ref({ primary_source: 'sina', backup_source_1: '', backup_source_2: '', backup_source_3: '' })
const sourceTimeout = ref(5)
const savingSource = ref(false)

const dbForm = ref({ database_url: '' })
const dbTest = ref(null)
const testingDb = ref(false)

const rssTypeMap = {
  http: { label: 'HTTP直连', ph: 'https://www.ithome.com/rss/' },
  rsshub_local: { label: 'RSSHub本地', ph: '/36kr/newsflashes（只需填后缀）' }
}
const rssTypeLabel = (t) => (rssTypeMap[t] || {}).label || t || '-'
const LOCAL_BASE = 'http://127.0.0.1:11200'
const addressPlaceholder = computed(() => (rssTypeMap[form.value.rss_type] || {}).ph || 'https://...')

function fullUrlFromForm() {
  let u = (form.value.url || '').trim()
  if (form.value.rss_type === 'rsshub_local') {
    if (!u) return ''
    if (/^https?:\/\//.test(u)) return u
    u = u.replace(/^\/+/, '')
    return LOCAL_BASE + '/' + u
  }
  return u
}

const sources = ref([])
const previewItems = ref([])
const itemTotal = ref(0)
const weiboCookie = ref('')
const lastPollText = ref('待轮询')
const polling = ref(false)
const savingRssHub = ref(false)

const dialogVisible = ref(false)
const editing = ref(false)
const form = ref({ name: '', rss_type: 'http', url: '', tagsText: '', remark: '', interval_min: 5, enabled: true })
const testing = ref(false)
const testResult = ref(null)
const pollingId = ref(null)
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
  weiboCookie.value = eff.weibo_cookies || ''
}

async function saveWeiboCookie() {
  savingRssHub.value = true
  try {
    await settingsApi.save({ weibo_cookies: (weiboCookie.value || '').trim() })
    ElMessage.success('微博 Cookie 已保存（微博订阅将直连 m.weibo.cn）')
  } finally {
    savingRssHub.value = false
  }
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

function openDialog(row) {
  editing.value = !!row
  testResult.value = null
  let url = row?.url || ''
  if (row?.rss_type === 'rsshub_local' && /^https?:\/\//.test(url) && url.startsWith(LOCAL_BASE)) {
    url = url.replace(LOCAL_BASE, '')
  }
  form.value = {
    name: row?.name || '',
    rss_type: row?.rss_type || 'http',
    url,
    tagsText: (row?.tags || []).join(','),
    remark: row?.remark || '',
    interval_min: row?.interval_min || 5,
    enabled: row?.enabled ?? true
  }
  dialogVisible.value = true
}

async function testFeed() {
  const u = fullUrlFromForm()
  if (!u) { ElMessage.warning('请填写订阅地址'); return }
  testing.value = true
  try {
    testResult.value = await rssApi.testFeed(u)
  } finally {
    testing.value = false
  }
}

async function saveSourceDialog() {
  const url = fullUrlFromForm()
  let name = form.value.name
  if (!name && url) {
    try { name = new URL(url).hostname } catch { name = url.slice(0, 30) }
  }
  const payload = {
    name,
    rss_type: form.value.rss_type,
    url: url || null,
    tags: form.value.tagsText.split(/[,，\s]+/).filter(Boolean),
    remark: form.value.remark || '',
    interval_min: Number(form.value.interval_min) || 5,
    enabled: form.value.enabled
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

async function pollSource(row) {
  pollingId.value = row.id
  try {
    const r = await rssApi.pollSource(row.id)
    if (r && r.ok) {
      ElMessage.success(`已轮询「${row.name}」，新增 ${r.added} 条`)
    } else {
      ElMessage.error(`轮询失败：${(r && r.error) || '未知错误'}`)
    }
  } catch (e) {
    ElMessage.error('轮询失败：' + (e?.message || e))
  } finally {
    pollingId.value = null
    await loadRss()
  }
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
.rss-base-line { display: flex; align-items: center; gap: 6px; }
.doc-link { color: #409eff; font-size: 12px; word-break: break-all; }
.doc-link code { background: #f5f7fa; padding: 0 4px; border-radius: 3px; font-size: 11px; }
.rss-tip { font-size: 12px; color: #e6a23c; background: #fdf6ec; border: 1px solid #f5dab1; border-radius: 6px; padding: 6px 10px; margin-bottom: 12px; line-height: 1.8; }
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