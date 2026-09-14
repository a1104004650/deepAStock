import { defineStore } from 'pinia'
import { ref } from 'vue'

const TOAST_MS = 15000

export const useNewsStore = defineStore('news', () => {
  const toasts = ref([])
  const timers = new Map()
  let newsShown = new Set()
  let idSeed = 0

  function dismissToast(id) {
    const t = timers.get(id)
    if (t) {
      clearTimeout(t)
      timers.delete(id)
    }
    const idx = toasts.value.findIndex((x) => x.id === id)
    if (idx >= 0) toasts.value.splice(idx, 1)
  }

  function pushNews(n) {
    if (!n || !n.title) return
    const key = 'imp-news-' + n.title.slice(0, 40)
    if (newsShown.has(key)) return
    newsShown.add(key)
    if (newsShown.size > 800) {
      const arr = [...newsShown]
      newsShown = new Set(arr.slice(arr.length - 400))
    }
    const id = ++idSeed
    toasts.value.push({
      id,
      title: n.title,
      url: n.url || '',
      source: n.source || '重要',
      importance: n.importance || 3
    })
    // 每条通知独立计时，15 秒后自动消失（多条同时弹出互不覆盖）
    timers.set(id, setTimeout(() => dismissToast(id), TOAST_MS))
  }

  function openNews(n) {
    if (n && n.url) window.open(n.url, '_blank', 'noopener')
    dismissToast(n.id)
  }

  return { toasts, pushNews, openNews, dismissToast }
})