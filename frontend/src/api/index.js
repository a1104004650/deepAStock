import http from './http'

// 行情
export const marketApi = {
  overview: () => http.get('/market/overview'),
  indices: () => http.get('/market/indices'),
  kline: (p) => http.get('/market/kline', { params: p }),
  intraday: (p) => http.get('/market/intraday', { params: p }),
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
  hotStocks: (top = 10) => http.get('/market/hot-stocks', { params: { top } }),
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
  industryChain: (s) => http.get(`/stocks/${s}/industry-chain`)
}

// 复盘
export const replayApi = {
  latest: () => http.get('/replay/latest'),
  history: () => http.get('/replay/history'),
  trigger: (data) => http.post('/replay/trigger', data)
}

// 智能体
export const agentApi = {
  list: () => http.get('/agents/'),
  create: (data) => http.post('/agents/', data),
  update: (id, data) => http.put(`/agents/${id}`, data),
  remove: (id) => http.delete(`/agents/${id}`),
  runs: () => http.get('/agents/runs'),
  runsStats: () => http.get('/agents/runs/stats'),
  analyzeStock: (data) => http.post('/agents/analyze/stock', data),
  analyzeMarket: (data) => http.post('/agents/analyze/market', data),
  brainstorm: (data) => http.post('/agents/brainstorm', data),
  brainstormGet: (s) => http.get(`/agents/brainstorm/${s}`),
  brainstormOne: (s, at) => http.post(`/agents/brainstorm/${s}/${at}`)
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
  stats: (id) => http.get(`/simulation/accounts/${id}/stats`),
  reset: (id) => http.post(`/simulation/accounts/${id}/reset`),
}

// 实盘导入
export const tradeApi = {
  importJson: (data) => http.post('/trade/import/json', data),
  importCsv: (formData) =>
    http.post('/trade/import/csv', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  positions: () => http.get('/trade/positions'),
  trades: () => http.get('/trade/trades'),
  deleteTrade: (id) => http.delete(`/trade/trades/${id}`),
  deleteAll: () => http.delete('/trade/trades'),
  pnl: () => http.get('/trade/pnl/summary')
}

// 系统
export const systemApi = {
  health: () => http.get('/system/health'),
  status: () => http.get('/system/status')
}