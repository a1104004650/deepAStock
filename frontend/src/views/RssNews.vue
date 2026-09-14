<template>
  <MainLayout>
    <div class="page rss-page">
    <div class="rss-head">
      <div>
        <h2 class="page-title">订阅消息</h2>
        <div class="rss-subtitle">
          RSS 订阅管理与聚合消息 · 每个源按「轮询时间」增量入库 · 新增消息自动进全局通知
        </div>
      </div>
      <div class="action-bar">
        <el-button size="small" type="danger" plain :loading="clearing" @click="clearAllItems">
          <el-icon style="margin-right:4px"><Delete /></el-icon>清空消息
        </el-button>
        <el-button size="small" :loading="polling" @click="pollNow">
          <el-icon style="margin-right:4px"><Refresh /></el-icon>立即轮询
        </el-button>
        <el-button size="small" :loading="refreshing" @click="loadAll">
          <el-icon style="margin-right:4px"><RefreshRight /></el-icon>刷新
        </el-button>
        <el-button size="small" type="primary" @click="openDialog()">新增订阅源</el-button>
      </div>
    </div>

    <div class="stat-row">
      <el-tag type="info" effect="plain">订阅源 {{ sources.length }} 个（启用 {{ enabledCount }}）</el-tag>
      <el-tag type="success" effect="plain">已入库 {{ itemTotal }} 条</el-tag>
      <el-tag type="warning" effect="plain">今日新增 {{ todayCount }} 条</el-tag>
      <span v-if="lastPollText" class="last-poll">{{ lastPollText }}</span>
    </div>

    <div class="doc-line">
      RSSHub 官方路由文档（传统媒体）：
      <a href="https://rsshub-doc.pages.dev/traditional-media.html#cai-xin-wang" target="_blank" rel="noopener" class="doc-link">
        https://rsshub-doc.pages.dev/traditional-media.html#cai-xin-wang
      </a>
    </div>

    <div class="rss-grid">
    <el-card shadow="never" class="panel feed-panel">
      <template #header>
        <div class="panel-head">
          <span>消息流（近3天 {{ filteredItems.length }} 条，轮询增量全部通知）</span>
          <div class="filters">
            <el-input v-model="keyword" placeholder="搜索标题/摘要/来源" clearable size="small" style="width:200px" :prefix-icon="Search" />
            <el-select v-model="fSource" placeholder="全部来源" clearable size="small" style="width:140px">
              <el-option v-for="s in sources" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
            <el-select v-model="fImportance" size="small" style="width:100px">
              <el-option label="全部" :value="0" />
              <el-option label="重要" :value="1" />
              <el-option label="一般" :value="2" />
              <el-option label="普通" :value="3" />
            </el-select>
          </div>
        </div>
      </template>

      <div v-if="loading" class="feed-loading">
        <el-skeleton :rows="6" animated />
      </div>
      <div v-else-if="!filteredItems.length" class="feed-empty">
        <el-empty description="暂无消息，点击「立即轮询」拉取订阅源或新增订阅源" :image-size="80" />
      </div>
      <div v-else class="feed-list">
        <div v-for="it in filteredItems" :key="it.id" class="feed-item">
          <span class="imp-tag" :style="impStyle(it.importance)">{{ impLabel(it.importance) }}</span>
          <div class="feed-main">
            <a v-if="it.link" class="feed-title" :href="it.link" target="_blank" rel="noopener">
              {{ it.title }}
            </a>
            <span v-else class="feed-title">{{ it.title }}</span>
            <div class="feed-meta">
              <el-tag size="small" type="info" effect="plain" class="feed-src">{{ it.source_name }}</el-tag>
              <el-tag v-for="t in (it.tags || [])" :key="t" size="small" effect="plain" class="feed-tag">{{ t }}</el-tag>
              <el-tag v-if="it.is_st" size="small" type="danger" effect="dark" class="feed-tag">ST</el-tag>
              <span class="feed-time">{{ fmtTime(it.pub_time) }}</span>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="panel sources-panel">
      <template #header>
        <div class="panel-head">
          <span>订阅源状态（轮询结果与入库条数）</span>
        </div>
      </template>
      <el-table :data="sources" size="small" empty-text="暂无订阅源">
        <el-table-column prop="name" label="名称" min-width="110">
          <template #default="{ row }"><b>{{ row.name }}</b></template>
        </el-table-column>
        <el-table-column label="RSS类型" width="120">
          <template #default="{ row }"><el-tag size="small" effect="plain">{{ rssTypeLabel(row.rss_type) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="订阅地址" min-width="200">
          <template #default="{ row }">
            <span class="route">{{ row.url || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }"><span class="form-tip" style="margin-left:0">{{ row.remark || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="轮询(分钟)" width="82" prop="interval_min" />
        <el-table-column label="启用" width="60">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" size="small" @change="(v) => toggle(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="网络状态" width="130">
          <template #default="{ row }">
            <span class="form-tip" style="margin-left:0" :class="netClass(row.net_status)">{{ netText(row.net_status) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最近轮询" min-width="150">
          <template #default="{ row }">
            <span class="form-tip" :class="row.last_status ? (row.last_status.startsWith('ok') ? 'ok' : 'err') : ''">
              {{ row.last_poll ? fmtTime(row.last_poll) : '未轮询' }} · {{ row.last_status || '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="216" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" size="small" :loading="pollingId === row.id" @click="pollSource(row)">轮询</el-button>
            <el-button link type="success" size="small" :loading="netTestingId === row.id" @click="netTestRow(row)">测试</el-button>
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="removeSource(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑订阅源' : '新增订阅源'" width="620px">
      <el-form label-width="96px" label-position="left">
        <el-form-item label="快速添加">
          <el-select v-model="quickCase" placeholder="一键填入默认的订阅源示例" clearable @change="onQuickCase">
            <el-option v-for="c in cases" :key="c.key" :label="c.name" :value="c.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="给这个源起个名字（可不填，自动识别）" />
        </el-form-item>
        <el-form-item label="RSS类型" required>
          <el-radio-group v-model="form.rss_type">
            <el-radio-button value="http">HTTP/HTTPS 直连</el-radio-button>
            <el-radio-button value="rsshub_local">RSSHub 本地 Docker</el-radio-button>
          </el-radio-group>
          <div class="form-tip" style="display:block;width:100%;margin-left:0;margin-top:6px">
            <template v-if="form.rss_type === 'http'">填写 RSS / Atom / JSON Feed 完整链接，直接抓取。示例：<code>https://www.ithome.com/rss/</code> · <code>https://www.ifanr.com/feed</code></template>
            <template v-else>填写 RSSHub 接口完整地址（直接粘 URL，不做任何校验）。参考：<br/>
              <code>/36kr/newsflashes</code>（36氪快讯）·
              <code>/cls/telegraph</code>（财联社电报）·
              <code>/wallstreetcn/news</code>（华尔街见闻）·
              <code>/caixin/latest</code>（财新）·
              <a href="https://rsshub-doc.pages.dev/traditional-media.html#cai-xin-wang" target="_blank" rel="noopener" class="doc-link">官方文档</a>
            </template>
          </div>
        </el-form-item>
        <el-form-item :label="'订阅地址'" required>
          <el-input v-model="form.url" :placeholder="addressPlaceholder">
            <template v-if="form.rss_type === 'rsshub_local'" #prepend>http://127.0.0.1:11200</template>
          </el-input>
          <div class="form-tip" style="display:block;width:100%;margin-left:0;margin-top:6px">
            <template v-if="form.rss_type === 'rsshub_local'">
              只需填 <code>/36kr/newsflashes</code> 这类后缀，系统自动在前面加上本地 RSSHub 地址（已由左侧「http://127.0.0.1:11200」辅助拼接）。<br/>
              已验证路由：<code>/36kr/newsflashes</code>（36氪快讯）· <code>/cls/telegraph</code>（财联社电报）· <code>/cls/depth</code>（财联社深度）· <code>/jin10/index</code>（金十快讯）· <code>/wallstreetcn/news</code>（华尔街见闻）· <code>/caixin/latest</code>（财新）
            </template>
            <template v-else>
              填写 RSS / Atom / JSON Feed 完整链接，直接抓取。示例：<code>https://www.ithome.com/rss/</code> · <code>https://www.ifanr.com/feed</code> · <code>https://www.tmtpost.com/rss</code>
            </template>
          </div>
        </el-form-item>
        <el-form-item label="轮询时间">
          <el-input-number v-model="form.interval_min" :min="1" :max="1440" :step="1" />
          <span class="form-tip" style="margin-left:10px">分钟（默认 5 分钟）</span>
        </el-form-item>
        <el-form-item label="关注标签">
          <el-input v-model="form.tagsText" placeholder="逗号分隔，普通自定义标签，如：热点,财经,A股" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="备注（可选）" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="form.url" @click="testFeed" :loading="testing">测试地址</el-button>
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
import { Refresh, RefreshRight, Search, Delete } from '@element-plus/icons-vue'
import { rssApi } from '../api'
import { formatNewsTime, toEpochMs } from '../utils/time'
import MainLayout from '../layout/MainLayout.vue'

const sources = ref([])
const items = ref([])
const loading = ref(false)
const refreshing = ref(false)
const polling = ref(false)
const lastPollText = ref('待轮询')
const clearing = ref(false)

const keyword = ref('')
const fSource = ref('')
const fImportance = ref(0)
const itemsTotal = ref(0)

const enabledCount = computed(() => sources.value.filter((s) => s.enabled).length)
const itemTotal = computed(() => itemsTotal.value)
const todayCount = computed(() => {
  const now = new Date(Date.now() + 8 * 3600 * 1000)
  const dayStart = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}-${String(now.getUTCDate()).padStart(2, '0')}`
  return items.value.filter((it) => fmtDate(it.pub_time || it.created_at) === dayStart).length
})

const filteredItems = computed(() => {
  const cutoff = Date.now() - 3 * 24 * 3600 * 1000
  let list = items.value.filter((it) => {
    const t = toEpochMs(it.pub_time || it.created_at)
    return !t || t >= cutoff
  })
  const kw = keyword.value.trim().toLowerCase()
  if (kw) list = list.filter((it) => (it.title || '').toLowerCase().includes(kw) || (it.summary || '').toLowerCase().includes(kw) || (it.source_name || '').toLowerCase().includes(kw))
  if (fSource.value) list = list.filter((it) => it.source_id === fSource.value)
  if (fImportance.value) list = list.filter((it) => Number(it.importance) === Number(fImportance.value))
  return list.slice().sort((a, b) => (toEpochMs(b.pub_time || b.created_at) || 0) - (toEpochMs(a.pub_time || a.created_at) || 0))
})

const rssTypeMap = {
  http: { label: 'HTTP直连', ph: 'https://www.ithome.com/rss/' },
  rsshub_local: { label: 'RSSHub本地', ph: '/36kr/newsflashes（只需填后缀）' }
}
const rssTypeLabel = (t) => (rssTypeMap[t] || {}).label || t || '-'
const LOCAL_BASE = 'http://127.0.0.1:11200'
const addressPlaceholder = computed(() => (rssTypeMap[form.value.rss_type] || {}).ph || 'https://...')

// 本地 RSSHub：用户只填后缀，保存时自动拼本地地址；公网/直连原样保存
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
function netText(s) {
  if (!s || s === 'untested') return '未测试'
  return s
}
function netClass(s) {
  if (!s || s === 'untested') return ''
  return s.startsWith('ok') ? 'ok' : 'err'
}

function fmtDate(ts) {
  const ms = toEpochMs(ts)
  if (ms == null) return ''
  const d = new Date(ms + 8 * 3600 * 1000)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

const fmtTime = (t) => formatNewsTime(t)

const impMap = {
  1: { label: '重要', color: '#f56c6c', bg: 'rgba(245,108,108,.1)' },
  2: { label: '一般', color: '#e6a23c', bg: 'rgba(230,162,60,.1)' },
  3: { label: '普通', color: '#909399', bg: 'rgba(144,147,153,.08)' }
}
const impLabel = (v) => (impMap[Number(v)] || impMap[3]).label
const impStyle = (v) => {
  const m = impMap[Number(v)] || impMap[3]
  return { color: m.color, background: m.bg, borderColor: m.color + '55' }
}

const cases = [
  { key: 'xhq', name: '雪球热帖（HTTP 直连）', rss_type: 'http', url: 'https://xueqiu.com/hots/topic/rss', tags: '财经' },
  { key: 'ithome', name: 'IT之家（HTTP 直连）', rss_type: 'http', url: 'https://www.ithome.com/rss/', tags: 'IT' },
  { key: 'ifanr', name: '爱范儿（HTTP 直连）', rss_type: 'http', url: 'https://www.ifanr.com/feed', tags: '数码' },
  { key: 'tmt', name: '钛媒体 TMT（HTTP 直连）', rss_type: 'http', url: 'https://www.tmtpost.com/rss', tags: 'TMT' },
  { key: '36kr', name: '36氪快讯（本地 RSSHub）', rss_type: 'rsshub_local', url: '/36kr/newsflashes', tags: '快讯' },
  { key: 'cls', name: '财联社电报（本地 RSSHub）', rss_type: 'rsshub_local', url: '/cls/telegraph', tags: '电报' },
  { key: 'cls-depth', name: '财联社深度（本地 RSSHub）', rss_type: 'rsshub_local', url: '/cls/depth', tags: '深度' },
  { key: 'jin10', name: '金十快讯（本地 RSSHub）', rss_type: 'rsshub_local', url: '/jin10/index', tags: '快讯' },
  { key: 'wscn', name: '华尔街见闻要闻（本地 RSSHub）', rss_type: 'rsshub_local', url: '/wallstreetcn/news', tags: '财经' },
  { key: 'caixin', name: '财新网要闻（本地 RSSHub）', rss_type: 'rsshub_local', url: '/caixin/latest', tags: '财经' }
]

const dialogVisible = ref(false)
const editing = ref(false)
const quickCase = ref('')
const form = ref({ name: '', rss_type: 'http', url: '', interval_min: 5, tagsText: '', remark: '', enabled: true })
const testing = ref(false)
const testResult = ref(null)
const netTestingId = ref(null)
const pollingId = ref(null)

function onQuickCase() {
  const c = cases.find((x) => x.key === quickCase.value)
  if (!c) return
  form.value.name = c.name
  form.value.rss_type = c.rss_type
  form.value.url = c.url
  form.value.tagsText = c.tags || ''
  form.value.interval_min = 5
  form.value.remark = ''
}

async function loadAll() {
  refreshing.value = true
  try {
    sources.value = await rssApi.sources()
    items.value = await rssApi.items({ limit: 100 })
    try { const st = await rssApi.stats(); itemsTotal.value = st?.items || 0 } catch { /* 忽略 */ }
  } finally {
    refreshing.value = false
  }
}

async function clearAllItems() {
  await ElMessageBox.confirm(
    '确认清除所有已入库消息？此操作不可恢复（订阅源保留）。',
    '清空消息', { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' })
  clearing.value = true
  try {
    const r = await rssApi.clearItems()
    ElMessage.success(`已清空 ${r.cleared || 0} 条消息`)
    await loadAll()
  } finally {
    clearing.value = false
  }
}

async function pollNow() {
  polling.value = true
  try {
    const r = await rssApi.poll()
    lastPollText.value = `上次轮询：${r.polled} 个源 · 新增 ${r.added} 条${r.errors && r.errors.length ? ` · ${r.errors.length} 个失败` : ''}`
    ElMessage.success(lastPollText.value)
    await loadAll()
  } finally {
    polling.value = false
  }
}

function openDialog(row) {
  editing.value = !!row
  testResult.value = null
  quickCase.value = ''
  let url = row?.url || ''
  if (row?.rss_type === 'rsshub_local' && /^https?:\/\//.test(url) && url.startsWith(LOCAL_BASE)) {
    url = url.replace(LOCAL_BASE, '')
  }
  form.value = {
    name: row?.name || '',
    rss_type: row?.rss_type || 'http',
    url,
    interval_min: row?.interval_min || 5,
    tagsText: (row?.tags || []).join(','),
    remark: row?.remark || '',
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
    await loadAll()
  }
}

async function netTestRow(row) {
  netTestingId.value = row.id
  try {
    const r = await rssApi.netTest(row.id)
    row.net_status = r.net_status || 'untested'
    const ok = r.ok
    ElMessage[ok ? 'success' : 'error'](ok ? `网络正常，可解析 ${r.count} 条` : `网络异常：${r.error}`)
  } catch (e) {
    ElMessage.error('测试失败：' + (e?.message || e))
  } finally {
    netTestingId.value = null
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
  await loadAll()
}

async function toggle(row, v) {
  await rssApi.updateSource(row.id, { enabled: v })
  ElMessage.success(v ? '订阅源已启用' : '订阅源已停用')
  await loadAll()
}

async function removeSource(row) {
  await ElMessageBox.confirm(`确认删除订阅源「${row.name}」及其已入库消息？`, '删除确认', { type: 'warning' })
  await rssApi.deleteSource(row.id)
  ElMessage.success('已删除')
  await loadAll()
}

let timer = null
onMounted(() => {
  loadAll()
  timer = setInterval(loadAll, 30000)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.page { padding: 20px; max-width: 1280px; }
.page-title { font-size: 18px; font-weight: 700; margin: 0 0 4px; }
.rss-head { display: flex; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.rss-subtitle { color: #909399; font-size: 12px; }
.action-bar { display: flex; gap: 8px; }
.stat-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.last-poll { color: #909399; font-size: 12px; }
.panel { border-radius: 10px; margin-bottom: 14px; }
.rss-grid { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1.3fr); gap: 14px; align-items: start; }
@media (max-width: 1100px) { .rss-grid { grid-template-columns: 1fr; } }
.panel-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.feed-list { max-height: 620px; overflow-y: auto; }
.feed-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 4px; border-bottom: 1px dashed #f0f2f5; }
.feed-item:last-child { border-bottom: none; }
.imp-tag { flex-shrink: 0; font-size: 12px; border: 1px solid; border-radius: 4px; padding: 0 6px; line-height: 18px; margin-top: 1px; }
.feed-main { flex: 1; min-width: 0; }
.feed-title { color: #303133; font-size: 14px; text-decoration: none; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-all; }
a.feed-title:hover { color: #409eff; }
.feed-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.feed-src { flex-shrink: 0; }
.feed-tag { flex-shrink: 0; }
.feed-time { color: #909399; font-size: 12px; }
.feed-loading { padding: 8px; }
.feed-empty { padding: 12px 0; }
.form-tip { color: #909399; font-size: 12px; margin-left: 10px; }
.form-tip.ok { color: #67c23a; }
.form-tip.err { color: #f56c6c; }
.route { font-family: Consolas, monospace; font-size: 12px; color: #606266; word-break: break-all; }
.doc-line { font-size: 12px; color: #606266; margin-bottom: 12px; }
.doc-link { color: #409eff; word-break: break-all; }
.doc-link code { background: #f5f7fa; padding: 0 4px; border-radius: 3px; font-size: 11px; }
</style>