import http from './http'

// 实验室
export const labApi = {
  competitions: () => http.get('/lab/competitions'),
  getCompetition: (id) => http.get(`/lab/competitions/${id}`),
  createCompetition: (data) => http.post('/lab/competitions', data),
  updateCompetition: (id, data) => http.put(`/lab/competitions/${id}`, data),
  deleteCompetition: (id) => http.delete(`/lab/competitions/${id}`),
  startCompetition: (id) => http.put(`/lab/competitions/${id}/start`),
  pauseCompetition: (id) => http.put(`/lab/competitions/${id}/pause`),
  resumeCompetition: (id) => http.put(`/lab/competitions/${id}/resume`),
  finishCompetition: (id) => http.put(`/lab/competitions/${id}/finish`),
  competitionStats: (id) => http.get(`/lab/competitions/${id}/stats`),
  tradeAll: (compId) => http.post(`/lab/competitions/${compId}/trade-all`),
  addParticipant: (compId, data) => http.post(`/lab/competitions/${compId}/participants`, data),
  removeParticipant: (id) => http.delete(`/lab/participants/${id}`),
  triggerParticipantTrade: (compId, pId) => http.post(`/lab/competitions/${compId}/participants/${pId}/trade`),
  triggerTrade: (id) => http.post(`/lab/participants/${id}/trade`),
  participantTrades: (id) => http.get(`/lab/participants/${id}/trades`),
  participantPositions: (id) => http.get(`/lab/participants/${id}/positions`),
  chat: (compId) => http.get(`/lab/competitions/${compId}/chat`),
  sendChat: (compId, content) => http.post(`/lab/competitions/${compId}/chat`, null, { params: { content } }),
  leaderboard: (compId) => http.get(`/lab/competitions/${compId}/leaderboard`),
  equityCurve: (compId) => http.get(`/lab/competitions/${compId}/equity-curve`),
  parseCurl: (curl) => http.post('/agents/parse-curl', { curl }),
  // 投研
  analysts: () => http.get('/lab/analysts'),
  createAnalyst: (data) => http.post('/lab/analysts', data),
  updateAnalyst: (id, data) => http.put(`/lab/analysts/${id}`, data),
  deleteAnalyst: (id) => http.delete(`/lab/analysts/${id}`),
  researchList: () => http.get('/lab/research'),
  createResearch: (data) => http.post('/lab/research', data),
  researchDetail: (id) => http.get(`/lab/research/${id}`),
  runResearch: (id) => http.post(`/lab/research/${id}/run`),
  deleteResearch: (id) => http.delete(`/lab/research/${id}`),
}

// 行情
export const marketApi = {
  overview: () => http.get('/market/overview'),
  indices: () => http.get('/market/indices'),
  globalIndices: () => http.get('/market/global-indices'),
  macro: (refresh = 0) => http.get('/market/macro', { params: { refresh } }),
  kline: (p) => http.get('/market/kline', { params: p }),
  intraday: (p) => http.get('/market/intraday', { params: p }),
  intradayAnalysis: (p) => http.get('/market/intraday-analysis', { params: p }),
  realtime: (p) => http.get('/market/realtime', { params: p }),
  news: (limit = 50) => http.get('/market/news', { params: { limit } }),
  sectorFlow: () => http.get('/market/sectors/money-flow'),
  sectorFlowTop: () => http.get('/market/sectors/flow-top'),
  etfFlow: () => http.get('/market/etf/flow'),
  sectorSpeed: () => http.get('/market/sectors/speed'),
  limitUpLadder: () => http.get('/market/limit-up/ladder'),
  dragonTiger: () => http.get('/market/dragon-tiger'),
  distribution: () => http.get('/market/distribution'),
  sectorMonitor: () => http.get('/market/sectors/monitor'),
  sectorMonitorIntraday: (symbol) => http.get('/market/sectors/monitor/intraday', { params: { symbol } }),
  sectorConstituents: (symbol) => http.get('/market/sectors/constituents', { params: { symbol } }),
  hotStocks: (top = 10) => http.get('/market/hot-stocks', { params: { top } }),
  priceMovers: () => http.get('/market/price-movers'),
  marketFlow: () => http.get('/market/market-flow'),
  regulatory: () => http.get('/market/regulatory'),
  investCalendar: () => http.get('/market/invest-calendar'),
  dragonTigerSeats: (tradeDate) => http.get('/market/dragon-tiger/seats', { params: { trade_date: tradeDate } }),
}

// 自选股
export const watchlistApi = {
  groups: () => http.get('/watchlist/groups'),
  preview: () => http.get('/watchlist/preview'),
  createGroup: (data) => http.post('/watchlist/groups', data),
  updateGroup: (id, data) => http.put(`/watchlist/groups/${id}`, data),
  deleteGroup: (id) => http.delete(`/watchlist/groups/${id}`),
  addItem: (data) => http.post('/watchlist/items', data),
  removeItem: (id) => http.delete(`/watchlist/items/${id}`),
  batchRemove: (ids) => http.post('/watchlist/items/batch-delete', { ids }),
  updateNote: (id, data) => http.put(`/watchlist/items/${id}/note`, data)
}

// 个股
export const stockApi = {
  search: (keyword) => http.get('/stocks/search', { params: { keyword } }),
  basic: (s) => http.get(`/stocks/${s}/basic`),
  kline: (s, p) => http.get(`/stocks/${s}/kline`, { params: p }),
  indicators: (s, p) => http.get(`/stocks/${s}/indicators`, { params: p }),
  czsc: (s) => http.get(`/stocks/${s}/czsc`),
  czscMulti: (s) => http.get(`/stocks/${s}/czsc/multi`),
  financial: (s) => http.get(`/stocks/${s}/financial`),
  financialOverview: (s) => http.get(`/stocks/${s}/financial-overview`),
  moneyFlow: (s) => http.get(`/stocks/${s}/money-flow`),
  moneyFlowSummary: (s) => http.get(`/stocks/${s}/money-flow-summary`),
  news: (s) => http.get(`/stocks/${s}/news`),
  shareholders: (s) => http.get(`/stocks/${s}/shareholders`),
  sentiment: (s) => http.get(`/stocks/${s}/sentiment`),
  forms: (s) => http.get(`/stocks/${s}/forms`),
  sector: (s) => http.get(`/stocks/${s}/sector`),
  industryRanking: (s) => http.get(`/stocks/${s}/industry-ranking`),
  industryChain: (s) => http.get(`/stocks/${s}/industry-chain`),
  quotePanel: (s) => http.get('/market/quote-panel', { params: { symbol: s } })
}

// 复盘
export const replayApi = {
  latest: () => http.get('/replay/latest'),
  history: () => http.get('/replay/history'),
  trend: (days = 7) => http.get('/replay/trend', { params: { days } }),
  byDate: (date) => http.get(`/replay/${date}`),
  trigger: (data) => http.post('/replay/trigger', data, { timeout: 300000 })
}

// 智能体
export const agentApi = {
  list: () => http.get('/agents/'),
  create: (data) => http.post('/agents/', data),
  update: (id, data) => http.put(`/agents/${id}`, data),
  remove: (id) => http.delete(`/agents/${id}`),
  runs: () => http.get('/agents/runs'),
  runsStats: () => http.get('/agents/runs/stats'),
  weeklyStats: (week) => http.get('/agents/runs/weekly', { params: { week } }),
  analyzeStock: (data) => http.post('/agents/analyze/stock', data),
  analyzeMarket: (data) => http.post('/agents/analyze/market', data),
  brainstorm: (data) => http.post('/agents/brainstorm', data),
  brainstormGet: (s) => http.get(`/agents/brainstorm/${s}`),
  brainstormOne: (s, at) => http.post(`/agents/brainstorm/${s}/${at}`),
  brainstormOneStream: (s, at) =>
    fetch(`/api/v1/agents/brainstorm/${s}/${at}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    }),
  parseCurl: (curl) => http.post('/agents/parse-curl', { curl })
}

// 模拟交易
export const simulationApi = {
  accounts: () => http.get('/simulation/accounts'),
  create: (data) => http.post('/simulation/accounts', data),
  initAI: () => http.post('/simulation/accounts/init-ai'),
  remove: (id) => http.delete(`/simulation/accounts/${id}`),
  run: (id, data) => http.post(`/simulation/accounts/${id}/run`, data),
  performance: (id) => http.get(`/simulation/accounts/${id}/performance`),
  equity: (id) => http.get(`/simulation/accounts/${id}/equity`),
  positions: (id) => http.get(`/simulation/accounts/${id}/positions`),
  trades: (id) => http.get(`/simulation/accounts/${id}/trades`),
  reviews: (id) => http.get(`/simulation/accounts/${id}/reviews`),
  logs: (id, limit = 100) => http.get(`/simulation/accounts/${id}/logs`, { params: { limit } }),
  pool: (id) => http.get(`/simulation/accounts/${id}/pool`),
  setPool: (id, tracked) => http.put(`/simulation/accounts/${id}/pool`, { tracked }),
  stats: (id) => http.get(`/simulation/accounts/${id}/stats`),
  reset: (id) => http.post(`/simulation/accounts/${id}/reset`),
}

// 实盘导入
export const tradeApi = {
  importJson: (data) => http.post('/trade/import/json', data),
  importFile: (formData) =>
    http.post('/trade/import/file', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  positions: () => http.get('/trade/positions'),
  trades: () => http.get('/trade/trades'),
  deleteTrade: (id) => http.delete(`/trade/trades/${id}`),
  deleteAll: () => http.delete('/trade/trades'),
  pnl: () => http.get('/trade/pnl/summary'),
  reviewTrade: (id) => http.post(`/trade/trades/${id}/review`)
}

// 系统
export const systemApi = {
  health: () => http.get('/system/health'),
  status: () => http.get('/system/status'),
  changelog: () => http.get('/system/changelog')
}

// 系统设置
export const settingsApi = {
  get: () => http.get('/settings'),
  save: (updates) => http.put('/settings', { updates }),
  testDatabase: (url) => http.post('/settings/test-database', { url })
}

// RSSHub 订阅
export const rssApi = {
  sources: () => http.get('/rss/sources'),
  createSource: (data) => http.post('/rss/sources', data),
  updateSource: (id, data) => http.put(`/rss/sources/${id}`, data),
  deleteSource: (id) => http.delete(`/rss/sources/${id}`),
  testFeed: (url) => http.post('/rss/test', { url }),
  netTest: (id) => http.post(`/rss/sources/${id}/net-test`),
  pollSource: (id) => http.post(`/rss/sources/${id}/poll`),
  items: (params) => http.get('/rss/items', { params }),
  clearItems: () => http.delete('/rss/items'),
  recent: (limit = 50) => http.get('/rss/recent', { params: { limit } }),
  stats: () => http.get('/rss/stats'),
  poll: () => http.post('/rss/poll')
}

// 策略回测
export const backtestApi = {
  run: (data) => http.post('/backtest/run', data),
  strategies: () => http.get('/backtest/strategies'),
  createStrategy: (data) => http.post('/backtest/strategies', data),
  updateStrategy: (id, data) => http.put(`/backtest/strategies/${id}`, data),
  deleteStrategy: (id) => http.delete(`/backtest/strategies/${id}`),
  duplicateStrategy: (id) => http.post(`/backtest/strategies/${id}/duplicate`),
  testStrategy: (data) => http.post('/backtest/strategies/test', data)
}