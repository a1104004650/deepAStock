import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useNewsStore = defineStore('news', () => {
  const newsQueue = ref([])
  const currentNews = ref(null)
  let newsShown = new Set()

  function pushNews(n) {
    if (!n || !n.title) return
    const key = 'imp-news-' + n.title.slice(0, 40)
    if (newsShown.has(key)) return
    newsShown.add(key)
    if (newsShown.size > 800) {
      const arr = [...newsShown]
      newsShown = new Set(arr.slice(arr.length - 400))
    }
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

  return { newsQueue, currentNews, pushNews, advanceNewsQueue, dismissNews, openNews }
})