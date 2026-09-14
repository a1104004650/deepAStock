<template>
  <MainLayout>
    <div class="page">
      <div class="coming-card">
        <el-icon class="coming-icon"><component :is="iconComp" /></el-icon>
        <h2 class="coming-title">{{ title }}</h2>
        <div class="coming-sub">敬请开放</div>
        <p class="coming-desc">该功能正在开发中，敬请期待。</p>
        <el-button type="primary" plain size="small" @click="backHome">返回看板</el-button>
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { DataLine, Coin, Cpu, Reading } from '@element-plus/icons-vue'
import MainLayout from '../layout/MainLayout.vue'

const props = defineProps({
  title: { type: String, default: '敬请开放' },
  code: { type: String, default: '' }
})

const router = useRouter()
const icons = { macro: DataLine, fund: Coin, lab: Cpu, knowledge: Reading }
const iconComp = computed(() => icons[props.code] || DataLine)

function backHome() { router.push('/') }
</script>

<style scoped>
.page { padding: 40px 20px; display: flex; justify-content: center; }
.coming-card {
  width: min(560px, 100%);
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 14px;
  padding: 48px 32px;
  text-align: center;
}
.coming-icon { font-size: 52px; color: #60a5fa; margin-bottom: 14px; }
.coming-title { font-size: 22px; font-weight: 700; margin: 0 0 6px; color: #303133; }
.coming-sub { display: inline-block; color: #e6a23c; border: 1px solid #f5dab1; background: #fdf6ec; border-radius: 6px; padding: 2px 10px; font-size: 13px; }
.coming-desc { color: #909399; font-size: 13px; margin: 14px 0 20px; }
</style>