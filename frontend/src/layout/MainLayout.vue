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
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { DataBoard, Star, Document, TrendCharts, Upload, MagicStick } from '@element-plus/icons-vue'
import { systemApi } from '../api'

const route = useRoute()
const clockText = ref('')

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
  { path: '/agents', label: '智能体', icon: MagicStick }
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
})
onBeforeUnmount(() => {
  clearInterval(timer)
  clearInterval(clockTimer)
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
  }
  .bn-item.active {
    color: #409eff;
    font-weight: 600;
  }
}
</style>