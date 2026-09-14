import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePollingStore = defineStore('polling', () => {
  const timers = ref({})

  function register(name, fn, intervalMs) {
    stop(name)
    if (!fn || !intervalMs) return
    timers.value[name] = setInterval(fn, intervalMs)
  }

  function stop(name) {
    if (timers.value[name]) {
      clearInterval(timers.value[name])
      delete timers.value[name]
    }
  }

  function clearAll() {
    for (const k of Object.keys(timers.value)) {
      clearInterval(timers.value[k])
      delete timers.value[k]
    }
  }

  return { timers, register, stop, clearAll }
})