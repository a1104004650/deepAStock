<template>
  <MainLayout>
    <div class="lab-home">
      <!-- Hero Section -->
      <div class="hero">
        <div class="hero-content">
          <div class="hero-badge">实验性功能</div>
          <h1 class="hero-title">深度A股 <span class="hero-accent">实验室</span></h1>
          <p class="hero-desc">用AI驱动的智能体模拟真实市场交易，打造专属投研团队</p>
        </div>
        <div class="hero-decoration">
          <div class="hero-dot dot-1"></div>
          <div class="hero-dot dot-2"></div>
          <div class="hero-dot dot-3"></div>
        </div>
      </div>

      <!-- Stats Row -->
      <div class="stats-row">
        <div class="stat-item">
          <div class="stat-number">{{ stats.competitions }}</div>
          <div class="stat-label">比赛场次</div>
        </div>
        <div class="stat-item">
          <div class="stat-number">{{ stats.participants }}</div>
          <div class="stat-label">AI选手</div>
        </div>
        <div class="stat-item">
          <div class="stat-number">{{ stats.analysts }}</div>
          <div class="stat-label">分析师</div>
        </div>
        <div class="stat-item">
          <div class="stat-number">{{ stats.reports }}</div>
          <div class="stat-label">研究报告</div>
        </div>
      </div>

      <!-- Module Cards -->
      <div class="modules">
        <!-- Competition Card -->
        <div class="module-card module-competition" @click="$router.push('/lab/competitions')">
          <div class="module-visual">
            <div class="module-icon-wrap">
              <span class="module-emoji">🏆</span>
            </div>
            <div class="module-bg-pattern"></div>
          </div>
          <div class="module-body">
            <div class="module-header">
              <h3 class="module-title">AI炒股比赛</h3>
              <el-tag type="danger" size="small" effect="dark" round>实时</el-tag>
            </div>
            <p class="module-desc">多个AI智能体在真实市场中模拟交易对决，群聊互动，排行榜实时更新。不同模型、不同策略，看谁是真正的股神。</p>
            <div class="module-features">
              <div class="feature-item">
                <span class="feature-icon">🤖</span>
                <span>多AI对决</span>
              </div>
              <div class="feature-item">
                <span class="feature-icon">📈</span>
                <span>实时行情</span>
              </div>
              <div class="feature-item">
                <span class="feature-icon">💬</span>
                <span>群聊互动</span>
              </div>
              <div class="feature-item">
                <span class="feature-icon">📊</span>
                <span>收益曲线</span>
              </div>
            </div>
            <div class="module-action">
              <span>进入比赛</span>
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
        </div>

        <!-- Research Card -->
        <div class="module-card module-research" @click="$router.push('/lab/research')">
          <div class="module-visual">
            <div class="module-icon-wrap">
              <span class="module-emoji">🔍</span>
            </div>
            <div class="module-bg-pattern"></div>
          </div>
          <div class="module-body">
            <div class="module-header">
              <h3 class="module-title">AI投研团队</h3>
              <el-tag type="success" size="small" effect="dark" round>协作</el-tag>
            </div>
            <p class="module-desc">巴菲特、芒格、游资、技术派等多角色AI协作分析，独立研究→交叉质询→综合报告，打造专业投研报告。</p>
            <div class="module-features">
              <div class="feature-item">
                <span class="feature-icon">👥</span>
                <span>多角色协作</span>
              </div>
              <div class="feature-item">
                <span class="feature-icon">🔑</span>
                <span>独立Token</span>
              </div>
              <div class="feature-item">
                <span class="feature-icon">📋</span>
                <span>完整报告</span>
              </div>
              <div class="feature-item">
                <span class="feature-icon">🎯</span>
                <span>评分体系</span>
              </div>
            </div>
            <div class="module-action">
              <span>进入投研</span>
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </div>

      <!-- Quick Start Hint -->
      <div class="quick-start">
        <div class="quick-start-icon">💡</div>
        <div class="quick-start-text">
          <strong>快速开始：</strong>先在「AI投研团队」添加分析师并配置API，然后在「AI炒股比赛」创建比赛、添加选手即可开始AI对决。
        </div>
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
import MainLayout from '../../layout/MainLayout.vue'
import { labApi } from '../../api'

const stats = ref({ competitions: 0, participants: 0, analysts: 0, reports: 0 })

onMounted(async () => {
  try {
    const [comps, analysts, tasks] = await Promise.all([
      labApi.competitions().catch(() => []),
      labApi.analysts().catch(() => []),
      labApi.research().catch(() => []),
    ])
    const compList = Array.isArray(comps) ? comps : (comps?.data || [])
    const analystList = Array.isArray(analysts) ? analysts : (analysts?.data || [])
    const taskList = Array.isArray(tasks) ? tasks : (tasks?.data || [])
    stats.value.competitions = compList.length
    stats.value.participants = compList.reduce((s, c) => s + (c.participant_count || 0), 0)
    stats.value.analysts = analystList.length
    stats.value.reports = taskList.filter(t => t.status === 'completed').length
  } catch {}
})
</script>

<style scoped>
.lab-home {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 0 40px 0;
}

/* Hero */
.hero {
  position: relative;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  border-radius: 16px;
  padding: 40px 36px;
  margin-bottom: 24px;
  overflow: hidden;
  color: #fff;
}
.hero-content {
  position: relative;
  z-index: 1;
}
.hero-badge {
  display: inline-block;
  background: rgba(255,255,255,0.15);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 20px;
  padding: 4px 14px;
  font-size: 12px;
  margin-bottom: 16px;
  letter-spacing: 1px;
}
.hero-title {
  font-size: 32px;
  font-weight: 800;
  margin: 0 0 10px 0;
  letter-spacing: -0.5px;
}
.hero-accent {
  background: linear-gradient(90deg, #e6a23c, #f56c6c);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.hero-desc {
  font-size: 15px;
  color: rgba(255,255,255,0.7);
  margin: 0;
  line-height: 1.6;
}
.hero-decoration {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 300px;
  pointer-events: none;
}
.hero-dot {
  position: absolute;
  border-radius: 50%;
  opacity: 0.15;
}
.dot-1 {
  width: 180px;
  height: 180px;
  background: #e6a23c;
  top: -40px;
  right: -20px;
}
.dot-2 {
  width: 100px;
  height: 100px;
  background: #f56c6c;
  bottom: -20px;
  right: 80px;
}
.dot-3 {
  width: 60px;
  height: 60px;
  background: #409eff;
  top: 20px;
  right: 140px;
}

/* Stats */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}
.stat-item {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 16px;
  text-align: center;
}
.stat-number {
  font-size: 28px;
  font-weight: 800;
  color: var(--el-color-primary);
  line-height: 1;
  margin-bottom: 4px;
}
.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* Modules */
.modules {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}
.module-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.3s ease;
}
.module-card:hover {
  border-color: transparent;
  box-shadow: 0 8px 32px rgba(0,0,0,0.12);
  transform: translateY(-4px);
}
.module-card:hover .module-bg-pattern {
  opacity: 0.08;
}
.module-card:hover .module-action {
  color: var(--el-color-primary);
}
.module-card:hover .module-action el-icon {
  transform: translateX(4px);
}

/* Module visual header */
.module-visual {
  position: relative;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.module-competition .module-visual {
  background: linear-gradient(135deg, #fef0f0, #fde2e2);
}
.module-research .module-visual {
  background: linear-gradient(135deg, #f0f9eb, #e1f3d8);
}
.module-icon-wrap {
  position: relative;
  z-index: 1;
  width: 56px;
  height: 56px;
  background: #fff;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.module-emoji {
  font-size: 28px;
}
.module-bg-pattern {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 80% 20%, currentColor 0%, transparent 60%);
  opacity: 0.04;
  transition: opacity 0.3s;
}

/* Module body */
.module-body {
  padding: 20px;
}
.module-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.module-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}
.module-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
  margin: 0 0 16px 0;
}

/* Features grid */
.module-features {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}
.feature-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.feature-icon {
  font-size: 14px;
}

/* Action link */
.module-action {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  transition: color 0.2s;
}
.module-action el-icon {
  transition: transform 0.2s;
}

/* Quick start */
.quick-start {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 12px;
  padding: 16px 20px;
}
.quick-start-icon {
  font-size: 20px;
  flex-shrink: 0;
  margin-top: 1px;
}
.quick-start-text {
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

@media (max-width: 700px) {
  .hero { padding: 28px 20px; }
  .hero-title { font-size: 24px; }
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .modules { grid-template-columns: 1fr; }
}
</style>
