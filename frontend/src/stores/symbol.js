import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSymbolStore = defineStore('symbol', () => {
  const selectedSymbol = ref(null)
  const selectedRealtime = ref({})

  function select(symbol, realtime = {}) {
    selectedSymbol.value = symbol
    selectedRealtime.value = realtime
  }

  function updateRealtime(data) {
    if (!data || typeof data !== 'object') return
    selectedRealtime.value = { ...selectedRealtime.value, ...data }
  }

  function clear() {
    selectedSymbol.value = null
    selectedRealtime.value = {}
  }

  return { selectedSymbol, selectedRealtime, select, updateRealtime, clear }
})