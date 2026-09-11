<template>
  <MainLayout>
    <div class="page rss-page">
    <div class="rss-head">
      <div>
        <h2 class="page-title">订阅消息</h2>
        <div class="rss-subtitle">
          RSSHub / 自定义 RSS 推送，轮询去重后落库展示 · 定时轮询每 30s 调度（单源按间隔限频）· 重要消息同步全局推送
        </div>
      </div>
      <div class="action-bar">
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
      <el-tag :type="rssStatus.enabled ? 'success' : 'info'">
        {{ rssStatus.enabled ? 'RSSHub 启用' : 'RSSHub 关闭' }}
      </el-tag>
      <span v-if="lastPollText" class="last-poll">{{ lastPollText }}</span>
    </div>

    <!-- RSSHub 配置（与「设置 → RSSHub 订阅」一致，此处可直接维护） -->
    <el-card shadow="never" class="panel cfg-panel">
      <div class="cfg-row">
        <span class="cfg-title">RSSHub 配置</span>
        <el-switch v-model="rssStatus.enabled" active-text="启用轮询" @change="saveCfg" />
        <span class="form-tip" style="margin-left:4px">实例地址</span>
        <el-input v-model="rssBase" size="small" placeholder="本机开发：http://127.0.0.1:11200" style="width:260px" />
        <el-button size="small" type="primary" :loading="savingCfg" @click="saveCfg">保存配置</el-button>
        <span class="cfg-hint">本机开发填宿主机映射 <code>http://127.0.0.1:11200</code>；Docker 容器内自动为 <code>http://rsshub:1200</code>；微博订阅直连 m.weibo.cn（无需 docker 配 Cookie）</span>
      </div>
      <div class="cfg-row">
        <span class="cfg-title">微博 Cookie</span>
        <el-input v-model="weiboCookie" size="small" type="textarea" :rows="2" style="width:560px" placeholder="浏览器登录 m.weibo.cn → F12 → 复制任一请求的 Cookie 头整串（仅微博订阅直连使用，保存在本应用）" />
        <el-button size="small" type="primary" :loading="savingCfg" @click="saveWeiboCookie">保存微博 Cookie</el-button>
      </div>
    </el-card>

    <div class="rss-grid">
    <el-card shadow="never" class="panel feed-panel">
      <template #header>
        <div class="panel-head">
          <span>消息流（{{ filteredItems.length }} 条）</span>
          <div class="filters">
            <el-input v-model="keyword" placeholder="搜索标题/摘要/来源" clearable size="small" style="width:200px" :prefix-icon="Search" />
            <el-select v-model="fSource" placeholder="全部来源" clearable size="small" style="width:140px">
              <el-option v-for="s in sources" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
            <el-select v-model="fImportance" placeholder="全部重要度" clearable size="small" style="width:120px">
              <el-option label="重要" :value="1" />
              <el-option label="一般" :value="2" />
              <el-option label="普通" :value="3" />
            </el-select>
            <el-switch v-model="fShowSt" active-text="含ST" />
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
        <el-table-column prop="name" label="名称" min-width="120">
          <template #default="{ row }"><b>{{ row.name }}</b></template>
        </el-table-column>
        <el-table-column label="地址" min-width="220">
          <template #default="{ row }">
            <span class="route">{{ row.url || (rssStatus.base || '') + (row.route || '') }}</span>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="62">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" size="small" @change="(v) => toggle(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="间隔" width="66">
          <template #default="{ row }">{{ row.interval_sec }}s</template>
        </el-table-column>
        <el-table-column label="最近轮询" min-width="170">
          <template #default="{ row }">
            <span class="form-tip" :class="row.last_status ? (row.last_status.startsWith('ok') ? 'ok' : 'err') : ''">
              {{ row.last_poll ? fmtTime(row.last_poll) : '未轮询' }} · {{ row.last_status || '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="入库" width="70">
          <template #default="{ row }">{{ row.last_item_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="removeSource(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑订阅源' : '新增订阅源'" width="580px">
      <el-form label-width="90px" label-position="left">
        <el-form-item label="快速添加">
          <el-select v-model="quickCase" placeholder="一键填入已验证的案例源" clearable @change="onQuickCase">
            <el-option v-for="c in cases" :key="c.url" :label="c.name" :value="c.url" />
          </el-select>
        </el-form-item>
        <el-form-item label="平台" required>
          <el-select v-model="form.platform" @change="onPlatformChange">
            <el-option v-for="(p, key) in platformMap" :key="key" :label="p.label" :value="key" />
          </el-select>
          <span class="form-tip">{{ platformHint }}</span>
        </el-form-item>
        <el-form-item :label="isRssHub ? 'RSSHub 路径' : '订阅地址'" required>
          <el-input v-model="addressValue" :placeholder="addressPlaceholder" />
          <div class="form-tip" style="display:block;width:100%;margin-left:0;margin-top:4px">
            <template v-if="isRssHub">
              填写 RSSHub 路径，会自动拼接到上方实例地址。示例：<br/>
              <code>/weibo/user/1645823934</code>（微博用户）·
              <code>/weibo/search/hot</code>（微博热搜）·
              <code>/wechat/sogou/财经</code>（公众号）·
              <code>/eastmoney/guba/600519</code>（股吧）
            </template>
            <template v-else>
              填写 RSS / Atom / JSON Feed 完整链接，直接拉取不经过 RSSHub。示例：<br/>
              <code>https://xueqiu.com/hots/topic/rss</code>（雪球热帖）·
              <code>https://www.ithome.com/rss/</code>（IT之家）·
              <code>https://www.ifanr.com/feed</code>（爱范儿）
            </template>
          </div>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="给这个源起个名字" />
        </el-form-item>
        <el-form-item label="关注标签">
          <el-input v-model="form.tagsText" placeholder="逗号分隔，如：600519,茅台,热点（可不填）" />
        </el-form-item>
        <el-form-item label="轮询间隔">
          <el-input-number v-model="form.interval_sec" :min="10" :max="1800" :step="10" />
          <span class="form-tip" style="margin-left:10px">秒</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="过滤 ST">
          <el-switch v-model="form.filter_st" />
          <span class="form-tip" style="margin-left:10px">过滤标题含 ST / *ST 的消息</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="addressValue" @click="testFeed" :loading="testing">测试地址</el-button>
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
import { Refresh, RefreshRight, Search } from '@element-plus/icons-vue'
import { rssApi, systemApi, settingsApi } from '../api'
import MainLayout from '../layout/MainLayout.vue'

const sources = ref([])
const items = ref([])
const rssStatus = ref({ enabled: true, base: '' })
const rssBase = ref('')
const weiboCookie = ref('')
const savingCfg = ref(false)
const loading = ref(false)
const refreshing = ref(false)
const polling = ref(false)
const lastPollText = ref('待轮询')

const keyword = ref('')
const fSource = ref('')
const fImportance = ref('')
const fShowSt = ref(true)

const enabledCount = computed(() => sources.value.filter((s) => s.enabled).length)
const itemTotal = computed(() => items.value.length)
const todayCount = computed(() => {
  const t = new Date()
  const today = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`
  return items.value.filter((it) => fmtDate(it.pub_time || it.created_at) === today).length
})

const filteredItems = computed(() => {
  let list = items.value
  const kw = keyword.value.trim().toLowerCase()
  if (kw) list = list.filter((it) => (it.title || '').toLowerCase().includes(kw) || (it.summary || '').toLowerCase().includes(kw) || (it.source_name || '').toLowerCase().includes(kw))
  if (fSource.value) list = list.filter((it) => it.source_id === fSource.value)
  if (fImportance.value !== '') list = list.filter((it) => Number(it.importance) === Number(fImportance.value))
  if (!fShowSt.value) list = list.filter((it) => !it.is_st)
  return list
})

function fmtDate(ts) {
  if (!ts) return ''
  const d = new Date(String(ts).includes('T') ? String(ts).replace(' ', 'T') : String(ts).replace(' ', 'T'))
  if (isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

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
  { name: '雪球每日热帖（财经）', url: 'https://xueqiu.com/hots/topic/rss', platform: 'generic' },
  { name: '钛媒体 TMT（科技商业）', url: 'https://www.tmtpost.com/rss', platform: 'generic' },
  { name: 'IT之家（数码）', url: 'https://www.ithome.com/rss/', platform: 'generic' },
  { name: '爱范儿（数码消费）', url: 'https://www.ifanr.com/feed', platform: 'generic' },
  { name: '少数派（效率工具）', url: 'https://sspai.com/feed', platform: 'generic' }
]
const platformMap = {
  generic: { label: '直接 RSS（填完整链接）', route: '' },
  weibo: { label: '微博（RSSHub 路径）', route: '/weibo/user/' },
  wechat: { label: '微信公众号（RSSHub 路径）', route: '/wechat/sogou/' },
  guba: { label: '东方财富股吧（RSSHub 路径）', route: '/eastmoney/guba/' },
  weibo_hot: { label: '微博热搜（RSSHub 路径）', route: '/weibo/search/hot' }
}
const platformHint = computed(() => {
  const p = platformMap[form.value.platform]
  return p?.route ? '走 RSSHub 实例，填路径即可' : '直接抓取 RSS 链接，不走 RSSHub'
})
const isRssHub = computed(() => {
  const p = platformMap[form.value.platform]
  return !!(p && p.route)
})
const addressValue = computed({
  get: () => isRssHub.value ? form.value.route : form.value.url,
  set: (v) => { if (isRssHub.value) form.value.route = v; else form.value.url = v }
})
const addressPlaceholder = computed(() => {
  if (isRssHub.value) {
    const hint = { weibo: '1645823934（只填 uid，自动拼成 /weibo/user/uid）', wechat: '财经（关键词）', guba: '600519（股票代码）', weibo_hot: '（无需填写，直接保存）' }
    return hint[form.value.platform] || '/路由/参数'
  }
  return 'https://example.com/feed.xml'
})

const quickCase = ref('')
function onQuickCase() {
  const c = cases.find((x) => x.url === quickCase.value)
  if (!c) return
  form.value.name = c.name
  form.value.url = c.url
  form.value.route = ''
  form.value.platform = c.platform || 'generic'
  if (!editing.value) form.value.filter_st = c.url.includes('xueqiu')
}

function onPlatformChange() {
  form.value.route = ''
  form.value.url = ''
}

const dialogVisible = ref(false)
const editing = ref(false)
const form = ref({ name: '', platform: 'generic', route: '', url: '', tagsText: '', interval_sec: 180, enabled: true, filter_st: true })
const testing = ref(false)
const testResult = ref(null)

const fmtTime = (t) => {
  if (!t) return ''
  const str = String(t)
  if (str.includes('T')) return str.slice(0, 16).replace('T', ' ')
  return str.slice(0, 16).replace('T', ' ')
}

async function loadAll() {
  refreshing.value = true
  try {
    sources.value = await rssApi.sources()
    const sys = await systemApi.status().catch(() => null)
    if (sys && sys.rsshub) {
      rssStatus.value = { enabled: sys.rsshub.enabled, base: sys.rsshub.base }
      rssBase.value = sys.rsshub.base || ''
    }
    const s = await settingsApi.get().catch(() => null)
    if (s && s.effective) weiboCookie.value = s.effective.weibo_cookies || ''
    items.value = await rssApi.items({ limit: 100 })
  } finally {
    refreshing.value = false
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

async function saveCfg() {
  savingCfg.value = true
  try {
    await settingsApi.save({ rsshub_enabled: rssStatus.value.enabled ? '1' : '0', rsshub_base: rssBase.value })
    await loadAll()
    ElMessage.success('RSSHub 配置已保存')
  } finally { savingCfg.value = false }
}

async function saveWeiboCookie() {
  savingCfg.value = true
  try {
    await settingsApi.save({ weibo_cookies: (weiboCookie.value || '').trim() })
    await loadAll()
    ElMessage.success('微博 Cookie 已保存（微博订阅将直连 m.weibo.cn）')
  } finally { savingCfg.value = false }
}

function openDialog(row) {
  editing.value = !!row
  testResult.value = null
  form.value = {
    name: row?.name || '',
    platform: row?.platform || 'generic',
    route: row?.route || '',
    url: row?.url || '',
    tagsText: (row?.tags || []).join(','),
    interval_sec: row?.interval_sec || 180,
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
  if (!u) { ElMessage.warning('请填写订阅地址'); return }
  testing.value = true
  try {
    testResult.value = await rssApi.testFeed(u)
  } finally {
    testing.value = false
  }
}

async function saveSourceDialog() {
  const route = form.value.route || null
  const url = form.value.url || null
  if (!route && !url) { ElMessage.warning('请填写订阅地址'); return }
  // auto-fill name from address if empty
  let name = form.value.name
  if (!name) {
    if (url) {
      try { name = new URL(url).hostname } catch { name = url.slice(0, 30) }
    } else {
      name = route
    }
  }
  const payload = {
    name,
    platform: form.value.platform,
    route,
    url,
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
.page { padding: 20px; max-width: 1240px; }
.page-title { font-size: 18px; font-weight: 700; margin: 0 0 4px; }
.rss-head { display: flex; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.rss-subtitle { color: #909399; font-size: 12px; }
.action-bar { display: flex; gap: 8px; }
.stat-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.last-poll { color: #909399; font-size: 12px; }
.panel { border-radius: 10px; margin-bottom: 14px; }
.cfg-panel :deep(.el-card__body) { padding-top: 10px; }
.cfg-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.cfg-title { font-weight: 600; flex-shrink: 0; }
.cfg-hint { color: #909399; font-size: 12px; }
.cfg-hint code { background: #f5f7fa; padding: 0 4px; border-radius: 3px; font-size: 11px; }
.rss-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 14px; align-items: start; }
@media (max-width: 1100px) { .rss-grid { grid-template-columns: 1fr; } }
.panel-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.feed-list { max-height: 520px; overflow-y: auto; }
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
</style>