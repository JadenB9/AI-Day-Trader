import axios from 'axios'

const API_BASE = '/api'

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Types
export interface Position {
  symbol: string
  qty: number
  side: string
  avg_entry_price: number
  market_value: number
  current_price: number
  unrealized_pl: number
  unrealized_plpc: number
  change_today: number
  asset_class: string
}

export interface Order {
  order_id: string
  symbol: string
  qty: number
  side: string
  type: string
  status: string
  limit_price?: number
  stop_price?: number
  filled_qty: number
  filled_avg_price?: number
  asset_class: string
}

export interface Strategy {
  name: string
  enabled: boolean
  description: string
  signals_generated: number
  win_rate: number
  params: Record<string, any>
}

export interface RiskMetrics {
  portfolio_heat: number
  daily_pnl: number
  daily_pnl_pct: number
  weekly_pnl: number
  weekly_pnl_pct: number
  max_daily_loss: number
  max_weekly_loss: number
  daily_limit_remaining: number
  weekly_limit_remaining: number
  position_count: number
  max_positions: number
  consecutive_losses: number
  is_halted: boolean
  halt_reason?: string
}

export interface SystemStatus {
  running: boolean
  mode: string
  uptime_seconds: number
  cycle_count: number
  last_cycle_time_ms: number
  equity: number
  cash: number
  buying_power: number
  position_count: number
  open_orders: number
  crypto_enabled: boolean
  hft_enabled: boolean
}

// API functions
export const fetchPositions = () => api.get('/positions').then(r => r.data)
export const closePosition = (symbol: string) => api.delete(`/positions/${symbol}`)
export const closeAllPositions = () => api.delete('/positions')

export const fetchOrders = () => api.get('/orders').then(r => r.data)
export const cancelOrder = (orderId: string) => api.delete(`/orders/${orderId}`)
export const cancelAllOrders = () => api.delete('/orders')
export const submitOrder = (order: any) => api.post('/orders', order)

export const fetchStrategies = () => api.get('/strategies').then(r => r.data)
export const toggleStrategy = (name: string, enabled: boolean) =>
  api.post(`/strategies/${name}/toggle`, { enabled })
export const updateStrategyParams = (name: string, params: any) =>
  api.patch(`/strategies/${name}/params`, { params })

export const fetchRiskMetrics = () => api.get('/risk/metrics').then(r => r.data)
export const haltTrading = () => api.post('/risk/halt')
export const resumeTrading = () => api.post('/risk/resume')

export const fetchSystemStatus = () => api.get('/system/status').then(r => r.data)
export const startTrading = () => api.post('/system/start')
export const stopTrading = () => api.post('/system/stop')
export const fetchWatchlist = () => api.get('/system/watchlist').then(r => r.data)

export const fetchSettings = () => api.get('/settings').then(r => r.data)
export const updateSettings = (category: string, settings: any) =>
  api.patch(`/settings/${category}`, { settings })

// Equity history - real data from Alpaca
export const fetchEquityHistory = (period: string = '1D', timeframe: string = '5Min') =>
  api.get(`/positions/history/equity?period=${period}&timeframe=${timeframe}`).then(r => r.data)
