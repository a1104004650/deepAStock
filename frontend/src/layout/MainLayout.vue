<template>
  <el-container class="app-shell" :class="{ 'is-collapsed': sidebarCollapsed }">
    <aside class="side-rail" :aria-label="sidebarCollapsed ? '折叠导航' : '主导航'">
      <div class="brand-row">
        <router-link to="/" class="logo"><span class="logo-mark">A</span><span v-if="!sidebarCollapsed">deepAStock</span></router-link>
        <button class="collapse-btn" type="button" :aria-label="sidebarCollapsed ? '展开导航' : '折叠导航'" @click="sidebarCollapsed = !sidebarCollapsed">
          <el-icon><component :is="sidebarCollapsed ? Expand : Fold" /></el-icon>
        </button>
      </div>
      <div class="rail-caption" v-if="!sidebarCollapsed">A股短线操盘终端</div>
      <nav class="side-nav">
        <router-link to="/" class="side-link" :class="{ active: isActive('/') }" :title="sidebarCollapsed ? '看板' : ''">
          <el-icon><DataBoard /></el-icon><span v-if="!sidebarCollapsed">看板</span>
        </router-link>
        <div v-for="g in desktopGroups" :key="g.label" class="side-section">
          <div v-if="!sidebarCollapsed" class="side-section-title">{{ g.label }}</div>
          <router-link v-for="it in g.items" :key="it.path" :to="it.path" class="side-link" :class="{ active: isActive(it.path) }" :title="sidebarCollapsed ? it.label : ''">
            <el-icon><component :is="it.icon" /></el-icon><span v-if="!sidebarCollapsed">{{ it.label }}</span>
            <i v-if="it.isNew && !sidebarCollapsed" class="new-dot">NEW</i>
          </router-link>
        </div>
        <div class="side-section side-direct">
          <router-link v-for="d in desktopDirect" :key="d.path" :to="d.path" class="side-link" :class="{ active: isActive(d.path) }" :title="sidebarCollapsed ? d.label : ''">
            <el-icon><component :is="d.icon" /></el-icon><span v-if="!sidebarCollapsed">{{ d.label }}</span>
          </router-link>
        </div>
      </nav>
      <div class="rail-footer" v-if="!sidebarCollapsed"><span class="status-dot" :class="`status-${healthState}`"></span>{{ healthLabel }}<span class="rail-version">v1.7</span></div>
    </aside>
    <el-container class="content-shell">
      <el-header class="topbar" height="60px">
        <div class="topbar-left">
          <button class="mobile-menu-btn" type="button" aria-label="打开导航" @click="mobileOpen = true"><el-icon><Menu /></el-icon></button>
          <div class="crumb"><span>交易终端</span><b>/</b><strong>{{ route.meta.title || '看板' }}</strong></div>
        </div>
        <div class="topbar-right">
          <span v-if="symbolStore.selectedSymbol" class="current-stock" @click="router.push({ path: '/watchlist', query: { symbol: symbolStore.selectedSymbol } })">
            <span class="selected-dot"></span>{{ symbolStore.selectedSymbol }}
            <el-icon class="clear-btn" @click.stop="symbolStore.clear()"><Close /></el-icon>
          </span>
          <span class="clock">{{ clockText }}</span>
          <span class="health" :class="`health-${healthState}`" aria-live="polite">{{ healthLabel }}</span>
        </div>
      </el-header>
      <el-main class="main"><slot /></el-main>
    </el-container>
    <div v-if="mobileOpen" class="mobile-scrim" @click="mobileOpen = false"></div>
    <aside class="mobile-drawer" :class="{ open: mobileOpen }" aria-label="移动端导航">
      <div class="drawer-head"><span class="logo"><span class="logo-mark">A</span>deepAStock</span><button type="button" class="collapse-btn" aria-label="关闭导航" @click="mobileOpen = false"><el-icon><Close /></el-icon></button></div>
      <router-link v-for="item in allNavItems" :key="item.path" :to="item.path" class="drawer-link" :class="{ active: isActive(item.path) }" @click="mobileOpen = false">
        <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span><i v-if="item.isNew" class="new-dot">NEW</i>
      </router-link>
    </aside>
    <nav class="bottom-nav">
      <router-link v-for="item in mobileNav" :key="item.path" :to="item.path" class="bn-item" :class="{ active: isActive(item.path) }">
        <el-icon :size="20"><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
      </router-link>
      <button class="bn-item" type="button" @click="mobileOpen = true"><el-icon :size="20"><Menu /></el-icon><span>更多</span></button>
    </nav>
    <!-- 全局重要消息渐变通知（多条同时弹出、互不覆盖，15 秒自动消失；含平台新闻 + RSS 增量推送） -->
    <transition-group name="news-pop" tag="div" class="news-stack">
      <div
        v-for="t in newsStore.toasts"
        :key="t.id"
        class="news-toast"
        @click="newsStore.openNews(t)"
      >
        <div class="news-toast-text">
          <span class="news-toast-tag">{{ t.source }}</span>
          <span class="news-toast-title">{{ t.title }}</span>
        </div>
        <el-icon class="news-toast-close" @click.stop="newsStore.dismissToast(t.id)"><Close /></el-icon>
      </div>
    </transition-group>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataBoard, Star, Document, TrendCharts, Histogram, Upload,
  MagicStick, Promotion, Setting, Close, DataLine, Coin, Cpu, Reading, Fold, Expand, Menu
} from '@element-plus/icons-vue'
import { systemApi, marketApi, rssApi } from '../api'
import { useNewsStore } from '../stores/news'
import { usePollingStore } from '../stores/polling'
import { useSymbolStore } from '../stores/symbol'

const route = useRoute()
const router = useRouter()
const newsStore = useNewsStore()
const polling = usePollingStore()
const symbolStore = useSymbolStore()
const clockText = ref('')
const openMenu = ref('')
const sidebarCollapsed = ref(false)
const mobileOpen = ref(false)
const healthState = ref('pending')
const healthLabel = computed(() => ({ online: '后端在线', offline: '后端离线', pending: '连接中…' }[healthState.value]))

// 桌面端导航：直接项 + 分组大菜单（功能相近的整合到一个菜单下）
const desktopGroups = [
  {
    label: '行情',
    items: [
      { path: '/watchlist', label: '自选股', icon: Star },
      { path: '/regime', label: '市场周期', icon: DataLine, isNew: true },
      { path: '/screening', label: '智能选股', icon: TrendCharts },
      { path: '/replay', label: '每日复盘', icon: Document },
      { path: '/macro', label: '宏观数据', icon: DataLine },
      { path: '/fund', label: '基金与ETF', icon: Coin }
    ]
  },
  {
    label: '交易',
    items: [
      { path: '/backtest', label: '策略回测', icon: Histogram },
      { path: '/trade', label: '实盘导入', icon: Upload }
    ]
  },
  {
    label: 'AI 研究',
    items: [
      { path: '/simulation', label: '模拟交易', icon: TrendCharts },
      { path: '/agents', label: '智能体', icon: MagicStick },
      { path: '/lab', label: '实验室', icon: Cpu, isNew: true },
      { path: '/knowledge', label: 'Wiki', icon: Reading, soon: true }
    ]
  }
]
const desktopDirect = [
  { path: '/rss', label: '订阅', icon: Promotion },
  { path: '/settings', label: '设置', icon: Setting }
]
// 移动端底部导航：只保留最常用入口
const mobileNav = [
  { path: '/', label: '看板', icon: DataBoard },
  { path: '/watchlist', label: '自选', icon: Star },
  { path: '/simulation', label: '模拟', icon: TrendCharts },
  { path: '/rss', label: '订阅', icon: Promotion },
  { path: '/settings', label: '设置', icon: Setting }
]
const allNavItems = [
  { path: '/', label: '看板', icon: DataBoard },
  ...desktopGroups.flatMap((g) => g.items),
  ...desktopDirect,
]

const isActive = (path) => {
  const p = route.path
  if (path === '/') return p === '/' || p.startsWith('/stock/')
  if (path === '/watchlist') return p === '/watchlist' || p.startsWith('/stock/')
  return p === path
}
const groupActive = (g) => g.items.some((it) => {
  const p = route.path
  return p === it.path || (it.path === '/watchlist' && p.startsWith('/stock/'))
})

function isTradingHours() {
  const now = new Date()
  const d = now.getDay()
  if (d === 0 || d === 6) return false
  const mins = now.getHours() * 60 + now.getMinutes()
  return mins >= 9 * 60 + 15 && mins <= 15 * 60 + 10
}
function pollNewsInterval() {
  return isTradingHours() ? 2 * 60 * 1000 : 4 * 60 * 60 * 1000
}
// 平台新闻入队去重（存 store 的 pushNews 会再次去重，这里只是轮询本地快速跳过）
const newsShown = new Set()
async function pollImportantNews() {
  try {
    const platRows = await marketApi.news(60).catch(() => [])
    for (const n of platRows || []) {
      if (Number(n.importance || 3) !== 1) continue
      const key = 'plat-news-' + (n.title || '').slice(0, 80)
      if (newsShown.has(key)) continue
      newsShown.add(key)
      try {
        if (localStorage.getItem(key)) continue
        localStorage.setItem(key, '1')
      } catch { /* storage disabled */ }
      const item = { title: n.title, url: n.url, source: '平台新闻' }
      newsStore.pushNews(item)
    }
  } catch { /* ignore */ }
}

// RSS 纯增量轮询：仅推送 重要(1) 与 普通(2) 级别的消息进全局通知，其他级别不推送（本地去重）
const rssSeen = new Set()
async function pollRssIncrement() {
  try {
    const rows = await rssApi.recent(50).catch(() => [])
    for (const r of rows || []) {
      if (!r || !r.title) continue
      const imp = Number(r.importance || 3)
      if (imp > 2) continue
      const key = 'rss-inc-' + (r.guid || ('i' + (r.id || r.title)))
      if (rssSeen.has(key)) continue
      rssSeen.add(key)
      if (rssSeen.size > 2000) {
        const oldest = [...rssSeen].slice(0, rssSeen.size - 2000)
        oldest.forEach((k) => rssSeen.delete(k))
      }
      try {
        if (localStorage.getItem(key)) continue
        localStorage.setItem(key, '1')
      } catch { /* storage disabled */ }
      newsStore.pushNews({ title: r.title, url: r.link || '', source: r.source_name || 'RSS', importance: imp })
    }
  } catch { /* ignore */ }
}

function updateClock() {
  const now = new Date()
  const weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const y = now.getFullYear()
  const mo = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  const w = weekDays[now.getDay()]
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  const ss = String(now.getSeconds()).padStart(2, '0')
  clockText.value = `${y}-${mo}-${d} ${w} ${hh}:${mm}:${ss}`
}

function checkHealth() {
  systemApi
    .health()
    .then(() => { healthState.value = 'online' })
    .catch(() => { healthState.value = 'offline' })
}

onMounted(() => {
  checkHealth()
  polling.register('health', checkHealth, 30000)
  updateClock()
  polling.register('clock', updateClock, 1000)
  pollImportantNews()
  pollRssIncrement()
  polling.register('platnews', pollImportantNews, pollNewsInterval())
  polling.register('rss', pollRssIncrement, 60000)
})
onBeforeUnmount(() => {
  polling.stop('health')
  polling.stop('clock')
  polling.stop('platnews')
  polling.stop('rss')
})
</script>

<style scoped>
.layout {
  height: 100%;
}
.header {
  background: linear-gradient(105deg, var(--c-navy) 0%, var(--c-navy-2) 100%);
  color: var(--c-text-1);
  display: flex;
  align-items: center;
  padding: 0 20px;
  box-shadow: 0 4px 18px rgba(10, 22, 39, .14);
  z-index: 10;
}
.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  margin-right: 16px;
  white-space: nowrap;
  text-decoration: none;
}
.logo-mark { display:grid; place-items:center; width:26px; height:26px; border-radius:6px; background:var(--c-up); color:#fff; font:700 15px var(--font-mono); box-shadow:0 3px 10px rgba(239,35,42,.3); }
.nav {
  display: flex;
  align-items: center;
  flex: 1;
}
.nav-item {
  color: rgba(255,255,255,.68);
  font-size: 14px;
  padding: 8px 12px;
  border-radius: 5px;
  margin-right: 4px;
  cursor: pointer;
  text-decoration: none;
  transition: all .15s;
  border: 0;
  background: none;
  font-family: inherit;
}
.nav-item:hover {
  color: #fff;
  background: rgba(255,255,255,.08);
}
.nav-item.active {
  color: #fff;
  background: rgba(255,255,255,.12);
  box-shadow: inset 0 -2px 0 var(--c-up);
  font-weight: 600;
}
.nav-group {
  position: relative;
}
.nav-trigger {
  display: inline-flex;
  align-items: center;
}
.caret { transition: transform .2s; }
.caret.open { transform: rotate(180deg); }
.nav-panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 190px;
  background: var(--c-bg-card);
  border-radius: 7px;
  box-shadow: 0 14px 34px rgba(10,22,39,.18);
  border: 1px solid var(--c-border);
  padding: 6px;
  z-index: 900;
}
.nav-link {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 7px;
  font-size: 13px;
  color: var(--c-text-1);
  text-decoration: none;
  transition: all .12s;
}
.nav-link:hover {
  background: var(--c-bg);
  color: var(--c-primary);
}
.nav-link .el-tag { margin-left: auto; }
.nav-link.router-link-active {
  color: var(--c-primary);
  font-weight: 600;
  background: rgba(46,107,198,.08);
}
.right {
  color: var(--c-text-2);
  font-size: 12px;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 10px;
}
.current-stock {
  background: rgba(255,255,255,.1);
  color: #fff;
  border: 1px solid rgba(255,255,255,.2);
  border-radius: 5px;
  padding: 5px 9px;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.2s;
}
.selected-dot { width:6px; height:6px; border-radius:50%; background:var(--c-up); box-shadow:0 0 0 3px rgba(239,35,42,.15); }
.current-stock:hover { background: rgba(255,255,255,.16); }
.clear-btn { cursor: pointer; font-size: 12px; opacity: 0.6; }
.clear-btn:hover { opacity: 1; }
.clock {
  font-family: var(--font-mono, 'Consolas', 'SF Mono', monospace);
  font-size: 13px;
  color: rgba(255,255,255,.58);
}
.health {
  border: 1px solid rgba(255,255,255,.2);
  border-radius: 5px;
  padding: 4px 8px;
  background: rgba(255,255,255,.06);
}
.health-online { color: var(--c-up); border-color: rgba(239,35,42,.35); }
.health-offline { color: var(--c-down); border-color: rgba(20,177,67,.35); }
.health-pending { color: var(--c-text-3); }
.main {
  padding: 0;
  background: var(--c-bg);
}

/* 底部导航：默认隐藏，移动端显示 */
.bottom-nav {
  display: none;
}
@media (max-width: 820px) {
  .nav, .logo, .right { display: none; }
  .main { padding-bottom: 58px; }
  .bottom-nav {
    display: flex;
    position: fixed;
    left: 0; right: 0; bottom: 0;
    height: 62px;
    background: rgba(17,27,45,.98);
    border-top: 1px solid var(--c-border);
    box-shadow: 0 -4px 16px rgba(10,22,39,.18);
    z-index: 100;
    padding-bottom: env(safe-area-inset-bottom);
  }
  .bn-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    font-size: 11px;
    color: rgba(255,255,255,.6);
    text-decoration: none;
    border: 0;
    background: none;
    font-family: inherit;
    padding: 0;
  }
  .bn-item.active {
    color: #fff;
    font-weight: 600;
  }
}

/* 全局重要消息渐变通知 */
.news-stack {
  position: fixed;
  top: 66px;
  right: 16px;
  z-index: 2200;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(420px, calc(100vw - 32px));
  pointer-events: none;
}
.news-stack .news-toast { pointer-events: auto; }
.news-toast {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  color: #fff;
  background: linear-gradient(90deg, #ef232a 0%, #e6a23c 100%);
  box-shadow: 0 6px 18px rgba(239, 35, 42, .35);
  font-size: 13px;
  line-height: 1.5;
}
.news-toast-text {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.news-toast-tag {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid rgba(255,255,255,.8);
  border-radius: 4px;
  padding: 1px 5px;
}
.news-toast-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.news-toast-close {
  flex-shrink: 0;
  font-size: 15px;
  opacity: .85;
}
.news-toast-close:hover { opacity: 1; }
.news-pop-enter-active, .news-pop-leave-active { transition: all .3s ease; }
.news-pop-enter-from, .news-pop-leave-to {
  opacity: 0;
  transform: translateX(30px);
}
.news-pop-leave-active { position: relative; }

/* 终端壳层：桌面侧栏 + 顶部状态栏，页面业务内容仍由 slot 提供 */
.app-shell { height: 100%; background: var(--c-bg); }
.side-rail { width: 224px; flex: 0 0 224px; background: var(--c-navy); color: #fff; display:flex; flex-direction:column; transition: width .2s ease; z-index:20; }
.is-collapsed .side-rail { width: 72px; flex-basis:72px; }
.brand-row { height:60px; display:flex; align-items:center; justify-content:space-between; padding:0 14px; border-bottom:1px solid rgba(255,255,255,.08); }
.is-collapsed .brand-row { justify-content:center; padding:0; }
.collapse-btn, .mobile-menu-btn { border:0; background:transparent; color:inherit; cursor:pointer; display:grid; place-items:center; min-width:34px; min-height:34px; border-radius:6px; }
.collapse-btn:hover, .mobile-menu-btn:hover { background:rgba(255,255,255,.1); }
.rail-caption { color:rgba(255,255,255,.4); font-size:10px; letter-spacing:.12em; padding:18px 18px 8px; }
.side-nav { flex:1; overflow:auto; padding:8px 10px; }
.side-section { margin-top:16px; }
.side-section-title { color:rgba(255,255,255,.38); font-size:10px; letter-spacing:.12em; padding:0 10px 6px; }
.side-link, .drawer-link { min-height:40px; display:flex; align-items:center; gap:11px; padding:0 11px; border-radius:6px; color:rgba(255,255,255,.68); text-decoration:none; font-size:13px; transition:background .15s, color .15s; }
.side-link:hover, .drawer-link:hover { color:#fff; background:rgba(255,255,255,.08); }
.side-link.active, .drawer-link.active { color:#fff; background:linear-gradient(90deg, rgba(239,35,42,.22), rgba(255,255,255,.08)); box-shadow:inset 3px 0 0 var(--c-up); }
.is-collapsed .side-link { justify-content:center; padding:0; }
.side-direct { border-top:1px solid rgba(255,255,255,.08); padding-top:10px; }
.new-dot { margin-left:auto; color:#ff9b91; font:700 9px var(--font-mono); font-style:normal; }
.rail-footer { display:flex; align-items:center; gap:7px; min-height:48px; padding:0 18px; border-top:1px solid rgba(255,255,255,.08); color:rgba(255,255,255,.55); font-size:11px; }
.rail-version { margin-left:auto; color:rgba(255,255,255,.3); font-family:var(--font-mono); }
.status-dot { width:7px; height:7px; border-radius:50%; background:#9aa3af; }
.status-online { background:var(--c-up); box-shadow:0 0 0 3px rgba(239,35,42,.15); }
.status-offline { background:var(--c-down); }
.content-shell { min-width:0; }
.topbar { background:#fff; border-bottom:1px solid var(--c-border); display:flex; align-items:center; justify-content:space-between; padding:0 22px; box-shadow:0 1px 8px rgba(31,35,41,.04); z-index:10; }
.topbar-left, .topbar-right { display:flex; align-items:center; gap:12px; }
.crumb { display:flex; gap:9px; align-items:center; font-size:13px; color:var(--c-text-3); }
.crumb b { color:#c6ccd5; font-weight:400; }
.crumb strong { color:var(--c-ink); font-weight:600; }
.mobile-menu-btn { display:none; color:var(--c-ink); }
.mobile-scrim, .mobile-drawer { display:none; }

@media (max-width: 820px) {
  .side-rail { display:none; }
  .topbar { height:54px !important; padding:0 12px; }
  .mobile-menu-btn { display:grid; }
  .topbar-right .clock { display:none; }
  .crumb { font-size:12px; }
  .main { padding-bottom:62px; }
  .mobile-scrim { display:block; position:fixed; inset:0; background:rgba(10,22,39,.42); z-index:1000; }
  .mobile-drawer { display:flex; position:fixed; top:0; bottom:0; left:0; width:min(300px, 84vw); transform:translateX(-102%); transition:transform .22s ease; background:var(--c-navy); z-index:1001; flex-direction:column; padding:0 12px; box-shadow:12px 0 30px rgba(10,22,39,.22); }
  .mobile-drawer.open { transform:translateX(0); }
  .drawer-head { min-height:60px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,.08); margin-bottom:10px; }
  .drawer-head .logo { margin:0; }
  .drawer-link { min-height:46px; }
  .bottom-nav { height:62px; }
}
</style>
