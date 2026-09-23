<template>
  <header class="page-header">
    <div class="page-heading">
      <div v-if="eyebrow" class="page-eyebrow">{{ eyebrow }}</div>
      <div class="page-title-line">
        <h1>{{ title }}</h1>
        <slot name="badge" />
      </div>
      <p v-if="subtitle" class="page-subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="page-actions"><slot name="actions" /></div>
  </header>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  eyebrow: { type: String, default: '' },
  subtitle: { type: String, default: '' },
})
</script>

<style scoped>
.page-header { display:flex; align-items:flex-end; justify-content:space-between; gap:18px; padding:14px 2px 16px; border-bottom:1px solid var(--c-border); margin-bottom:12px; }
.page-heading { min-width:0; }
.page-eyebrow { color:var(--c-primary); font:600 10px var(--font-mono); letter-spacing:.1em; text-transform:uppercase; margin-bottom:4px; }
.page-title-line { display:flex; align-items:center; gap:8px; }
h1 { color:var(--c-ink); font-size:22px; line-height:1.2; font-weight:750; letter-spacing:-.03em; }
.page-subtitle { color:var(--c-text-3); font-size:12px; line-height:1.5; margin-top:5px; }
.page-actions { display:flex; align-items:center; gap:8px; flex-wrap:wrap; justify-content:flex-end; }
@media (max-width:820px) { .page-header { align-items:flex-start; flex-direction:column; gap:10px; padding:10px 0 12px; } .page-actions { width:100%; justify-content:flex-start; } h1 { font-size:19px; } }
</style>
