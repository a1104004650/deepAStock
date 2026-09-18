import { defineStore } from 'pinia'
import { ref } from 'vue'

const KEY = 'symbol.selected'

export const useSymbolStore = defineStore('symbol', () => {
  const selectedSymbol = ref(null)
  const selectedRealtime = ref({})

  function _save() {
    try {
      localStorage.setItem(KEY, JSON.stringify({ symbol: selectedSymbol.value, realtime: selectedRealtime.value }))
    } catch { /* storage disabled */ }
  }

  function _load() {
    try {
      const raw = localStorage.getItem(KEY)
      if (raw) {
        const data = JSON.parse(raw)
        if (data && data.symbol) {
          selectedSymbol.value = data.symbol
          selectedRealtime.value = data.realtime || {}
        }
      }
    } catch { /* storage disabled */ }
  }

  function select(symbol, realtime = {}) {
    selectedSymbol.value = symbol
    selectedRealtime.value = realtime
    _save()
  }

  function updateRealtime(data) {
    if (!data || typeof data !== 'object') return
    selectedRealtime.value = { ...selectedRealtime.value, ...data }
    _save()
  }

  function clear() {
    selectedSymbol.value = null
    selectedRealtime.value = {}
    _save()
  }

  // 启动时恢复上次选中的股票(跨刷新/跨页不丢)
  _load()

  return { selectedSymbol, selectedRealtime, select, updateRealtime, clear }
})