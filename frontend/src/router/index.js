import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'home', component: () => import('../views/Home.vue'), meta: { title: '大盘看板' } },
  { path: '/watchlist', name: 'watchlist', component: () => import('../views/Watchlist.vue'), meta: { title: '自选股' } },
  { path: '/stock/:symbol', redirect: to => ({ path: '/watchlist', query: { symbol: to.params.symbol } }) },
  { path: '/replay', name: 'replay', component: () => import('../views/Replay.vue'), meta: { title: '每日复盘' } },
  { path: '/simulation', name: 'simulation', component: () => import('../views/Simulation.vue'), meta: { title: '模拟交易' } },
  { path: '/backtest', name: 'backtest', component: () => import('../views/Backtest.vue'), meta: { title: '策略回测' } },
  { path: '/trade', name: 'trade', component: () => import('../views/TradeImport.vue'), meta: { title: '实盘导入' } },
  { path: '/agents', name: 'agents', component: () => import('../views/Agents.vue'), meta: { title: '智能体中心' } },
  { path: '/rss', name: 'rss', component: () => import('../views/RssNews.vue'), meta: { title: '订阅消息' } },
  { path: '/settings', name: 'settings', component: () => import('../views/Settings.vue'), meta: { title: '系统设置' } },
  { path: '/macro', name: 'macro', component: () => import('../views/Macro.vue'), meta: { title: '宏观数据' } },
  { path: '/fund', name: 'fund', component: () => import('../views/ComingSoon.vue'), props: { title: '基金', code: 'fund' }, meta: { title: '基金' } },
  { path: '/lab', name: 'lab', component: () => import('../views/ComingSoon.vue'), props: { title: '实验室', code: 'lab' }, meta: { title: '实验室' } },
  { path: '/knowledge', name: 'knowledge', component: () => import('../views/ComingSoon.vue'), props: { title: 'Wiki', code: 'knowledge' }, meta: { title: 'Wiki' } }
]

export default createRouter({
  history: createWebHashHistory(),
  routes
})