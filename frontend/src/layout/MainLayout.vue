<template>
  <el-container class="layout">
    <el-header class="header" height="56px">
      <div class="logo">deepAStock</div>
      <nav class="nav">
        <router-link
          v-for="item in desktopNav"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
        >{{ item.label }}</router-link>
      </nav>
      <div class="right">
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
    <!-- 全局重要消息渐变通知（每条只提示一次，本地去重；含平台新闻 + RSS 增量推送） -->
    <transition name="news-pop">
      <div v-if="currentNews" class="news-toast" @click="openNews(currentNews)">
        <div class="news-toast-text">
          <span class="news-toast-tag">{{ currentNews.source || '重要' }}</span>
          <span class="news-toast-title">{{ currentNews.title }}</span>
        </div>
        <el-icon class="news-toast-close" @click.stop="dismissNews"><Close /></el-icon>
      </div>
    </transition>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { DataBoard, Star, Document, TrendCharts, Upload, MagicStick, Promotion, Setting, Close } from '@element-plus/icons-vue'
import { systemApi, marketApi, rssApi } from '../api'

const route = useRoute()
const clockText = ref('')
const currentNews = ref(null)

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
      pushNews(item)
    }
  } catch { /* ignore */ }
}

// RSS 纯增量轮询：所有新入库的消息都进全局通知（本地去重）
const rssSeen = new Set()
async function pollRssIncrement() {
  try {
    const rows = await rssApi.recent(50).catch(() => [])
    for (const r of rows || []) {
      if (!r || !r.title) continue
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
      pushNews({ title: r.title, url: r.link || '', source: r.source_name || 'RSS', importance: Number(r.importance) || 3 })
    }
  } catch { /* ignore */ }
}

// 通知队列：逐条弹出，避免一次涌入多条只显示最后一条
const newsQueue = ref([])
let newsShown = new Set()
function pushNews(n) {
  if (!n || !n.title) return
  const key = 'imp-news-' + n.title.slice(0, 40)
  if (newsShown.has(key)) return
  newsShown.add(key)
  if (newsShown.size > 800) newsShown = new Set([...newsShown].slice(-400))
  newsQueue.value.push({ ...n, source: n.source || '', importance: n.importance || 3 })
  if (!currentNews.value) currentNews.value = newsQueue.value.shift() || null
}
function advanceNewsQueue() {
  if (newsQueue.value.length) currentNews.value = newsQueue.value.shift()
  else currentNews.value = null
}
function dismissNews() {
  currentNews.value = null
}
function openNews(n) {
  if (n && n.url) window.open(n.url, '_blank', 'noopener')
  currentNews.value = null
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

const navItems = [
  { path: '/', label: '看板', icon: DataBoard },
  { path: '/watchlist', label: '自选', icon: Star },
  { path: '/replay', label: '复盘', icon: Document },
  { path: '/simulation', label: '模拟', icon: TrendCharts },
  { path: '/trade', label: '实盘', icon: Upload },
  { path: '/agents', label: '智能体', icon: MagicStick },
  { path: '/rss', label: '订阅', icon: Promotion },
  { path: '/settings', label: '设置', icon: Setting }
]

const desktopNav = navItems.map(({ path, label }) => ({ path, label }))
const mobileNav = navItems

const isActive = (path) => {
  const p = route.path
  if (path === '/') return p === '/' || p.startsWith('/stock/')
  return p === path
}

let timer = null
let clockTimer = null
let newsTimer = null
let rssTimer = null
let newsAdvTimer = null

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
  timer = setInterval(checkHealth, 30000)
  updateClock()
  clockTimer = setInterval(updateClock, 1000)
  pollImportantNews()
  pollRssIncrement()
  newsTimer = setInterval(pollImportantNews, pollNewsInterval())
  rssTimer = setInterval(pollRssIncrement, 60000)
  newsAdvTimer = setInterval(advanceNewsQueue, 15000)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  clearInterval(clockTimer)
  if (newsTimer) clearInterval(newsTimer)
  if (rssTimer) clearInterval(rssTimer)
  if (newsAdvTimer) clearInterval(newsAdvTimer)
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
.right {
  color: #cbd5e1;
  font-size: 12px;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 12px;
}
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
.news-toast {
  position: fixed;
  top: 66px;
  right: 16px;
  max-width: min(420px, calc(100vw - 32px));
  z-index: 2200;
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
</style>