import { create } from 'zustand'
import type { Position, Order, RiskMetrics, SystemStatus } from '../api/client'

interface ActivityLog {
  id: string
  timestamp: string
  type: string
  title: string
  message: string
  details?: Record<string, any>
}

interface TradingState {
  // Data
  positions: Position[]
  orders: Order[]
  riskMetrics: RiskMetrics | null
  systemStatus: SystemStatus | null
  signals: any[]
  activityLogs: ActivityLog[]

  // WebSocket
  wsConnected: boolean

  // Actions
  setPositions: (positions: Position[]) => void
  updatePosition: (position: Position) => void
  removePosition: (symbol: string) => void
  setOrders: (orders: Order[]) => void
  updateOrder: (order: Order) => void
  setRiskMetrics: (metrics: RiskMetrics) => void
  setSystemStatus: (status: SystemStatus) => void
  addSignal: (signal: any) => void
  addActivityLog: (log: ActivityLog) => void
  setActivityLogs: (logs: ActivityLog[]) => void
  setWsConnected: (connected: boolean) => void
}

export const useTradingStore = create<TradingState>((set) => ({
  positions: [],
  orders: [],
  riskMetrics: null,
  systemStatus: null,
  signals: [],
  activityLogs: [],
  wsConnected: false,

  setPositions: (positions) => set({ positions }),

  updatePosition: (position) => set((state) => {
    const idx = state.positions.findIndex(p => p.symbol === position.symbol)
    if (idx >= 0) {
      const newPositions = [...state.positions]
      newPositions[idx] = position
      return { positions: newPositions }
    }
    return { positions: [...state.positions, position] }
  }),

  removePosition: (symbol) => set((state) => ({
    positions: state.positions.filter(p => p.symbol !== symbol)
  })),

  setOrders: (orders) => set({ orders }),

  updateOrder: (order) => set((state) => {
    const idx = state.orders.findIndex(o => o.order_id === order.order_id)
    if (idx >= 0) {
      const newOrders = [...state.orders]
      newOrders[idx] = order
      return { orders: newOrders }
    }
    return { orders: [...state.orders, order] }
  }),

  setRiskMetrics: (metrics) => set({ riskMetrics: metrics }),

  setSystemStatus: (status) => set({ systemStatus: status }),

  addSignal: (signal) => set((state) => ({
    signals: [signal, ...state.signals].slice(0, 50) // Keep last 50
  })),

  addActivityLog: (log) => set((state) => ({
    activityLogs: [...state.activityLogs, log].slice(-500) // Keep last 500
  })),

  setActivityLogs: (logs) => set({ activityLogs: logs }),

  setWsConnected: (connected) => set({ wsConnected: connected }),
}))
