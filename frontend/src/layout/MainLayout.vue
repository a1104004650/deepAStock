<template>
  <el-container class="layout">
    <el-header class="header" height="56px">
      <router-link to="/" class="logo">deepAStock</router-link>
      <nav class="nav">
        <router-link to="/" class="nav-item" :class="{ active: isActive('/') }">看板</router-link>

        <div
          v-for="g in desktopGroups"
          :key="g.label"
          class="nav-group"
          @mouseenter="onGroupEnter(g.label)"
          @mouseleave="onGroupLeave"
        >
          <span class="nav-item nav-trigger" :class="{ active: groupActive(g) }">
            {{ g.label }}
            <el-icon class="caret" :class="{ open: openMenu === g.label }" style="margin-left:3px"><ArrowDown /></el-icon>
          </span>
          <div v-show="openMenu === g.label" class="nav-panel">
            <router-link
              v-for="it in g.items"
              :key="it.path"
              :to="it.path"
              class="nav-link"
              @click="openMenu = ''"
            >
              <el-icon :size="15"><component :is="it.icon" /></el-icon>
              <span>{{ it.label }}</span>
              <el-tag v-if="it.soon" size="small" effect="plain" type="warning">敬请开放</el-tag>
            </router-link>
          </div>
        </div>

        <router-link
          v-for="d in desktopDirect"
          :key="d.path"
          :to="d.path"
          class="nav-item"
          :class="{ active: isActive(d.path) }"
        >{{ d.label }}</router-link>
      </nav>
      <div class="right">
        <span v-if="symbolStore.selectedSymbol" class="current-stock" @click="router.push({ path: '/watchlist', query: { symbol: symbolStore.selectedSymbol } })">
          {{ symbolStore.selectedSymbol }}
          <el-icon class="clear-btn" @click.stop="symbolStore.clear()"><Close /></el-icon>
        </span>
        <span class="clock">{{ clockText }}</span>
        <span class="health" id="health-tag">后端连接中…</span>
      </div>
    </el-header>
    <el-main class="main">
      <slot />
    </el-main>
    <nav class="bottom-nav">
      <router-link
        v-for="item in mobileNav"
        :key="item.path"
        :to="item.path"
        class="bn-item"
        :class="{ active: isActive(item.path) }"
      >
        <el-icon :size="20"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </router-link>
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
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataBoard, Star, Document, TrendCharts, Histogram, Upload,
  MagicStick, Promotion, Setting, Close, ArrowDown, DataLine, Coin, Cpu, Reading
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

// 桌面端导航：直接项 + 分组大菜单（功能相近的整合到一个菜单下）
const desktopGroups = [
  {
    label: '行情',
    items: [
      { path: '/watchlist', label: '自选股', icon: Star },
      { path: '/replay', label: '每日复盘', icon: Document },
      { path: '/macro', label: '宏观数据', icon: DataLine },
      { path: '/fund', label: '基金', icon: Coin, soon: true }
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
      { path: '/lab', label: '实验室', icon: Cpu, soon: true },
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

let hoverTimer = null
function onGroupEnter(label) {
  if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null }
  openMenu.value = label
}
function onGroupLeave() {
  if (hoverTimer) clearTimeout(hoverTimer)
  hoverTimer = setTimeout(() => { openMenu.value = ''; hoverTimer = null }, 150)
}

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
    .then(() => {
      const tag = document.getElementById('health-tag')
      if (tag) tag.textContent = '后端在线'
    })
    .catch(() => {})
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
  polling.clearAll()
})
</script>

<style scoped>
.layout {
  height: 100%;
}
.header {
  background: #1f2937;
  color: #f9fafb;
  display: flex;
  align-items: center;
  padding: 0 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.2);
  z-index: 10;
}
.logo {
  font-size: 17px;
  font-weight: 700;
  color: #60a5fa;
  margin-right: 24px;
  white-space: nowrap;
  text-decoration: none;
}
.nav {
  display: flex;
  align-items: center;
  flex: 1;
}
.nav-item {
  color: #cbd5e1;
  font-size: 14px;
  padding: 8px 14px;
  border-radius: 6px;
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
  color: #409eff;
  background: rgba(64,158,255,.12);
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
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0,0,0,.16);
  border: 1px solid #eef0f3;
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
  color: #303133;
  text-decoration: none;
  transition: all .12s;
}
.nav-link:hover {
  background: #f3f6fb;
  color: #409eff;
}
.nav-link .el-tag { margin-left: auto; }
.nav-link.router-link-active {
  color: #409eff;
  font-weight: 600;
  background: #ecf5ff;
}
.right {
  color: #cbd5e1;
  font-size: 12px;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 12px;
}
.current-stock {
  background: #409eff22;
  color: #409eff;
  border: 1px solid #409eff55;
  border-radius: 12px;
  padding: 2px 10px;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.2s;
}
.current-stock:hover { background: #409eff33; }
.clear-btn { cursor: pointer; font-size: 12px; opacity: 0.6; }
.clear-btn:hover { opacity: 1; }
.clock {
  font-family: 'Consolas', 'SF Mono', monospace;
  font-size: 13px;
  color: #94a3b8;
}
.health {
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 2px 10px;
}
.main {
  padding: 0;
  background: #f5f7fa;
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
    height: 56px;
    background: #fff;
    border-top: 1px solid #e5e7eb;
    box-shadow: 0 -1px 6px rgba(0,0,0,.06);
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
    color: #909399;
    text-decoration: none;
    border: 0;
    background: none;
    font-family: inherit;
    padding: 0;
  }
  .bn-item.active {
    color: #409eff;
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
</style>