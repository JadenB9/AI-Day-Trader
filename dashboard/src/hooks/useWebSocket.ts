import { useEffect, useRef, useCallback } from 'react'
import { useTradingStore } from '../stores/tradingStore'

// Use relative path - Vite proxy handles routing to backend
const WS_URL = `ws://${window.location.host}/ws`

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number>()

  const {
    setWsConnected,
    updatePosition,
    updateOrder,
    addSignal,
    addActivityLog,
    setSystemStatus
  } = useTradingStore()

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)

    ws.onopen = () => {
      console.log('WebSocket connected')
      setWsConnected(true)

      // Request full state
      ws.send(JSON.stringify({ action: 'refresh' }))
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setWsConnected(false)

      // Reconnect after 3 seconds
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect()
      }, 3000)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        handleMessage(message)
      } catch (e) {
        console.error('Failed to parse message:', e)
      }
    }

    wsRef.current = ws
  }, [setWsConnected])

  const handleMessage = (message: any) => {
    const { type, data } = message

    switch (type) {
      case 'position_update':
        updatePosition(data)
        break
      case 'order_update':
        updateOrder(data)
        break
      case 'signal':
        addSignal(data)
        break
      case 'heartbeat':
        // Update system metrics from heartbeat
        if (data.equity) {
          setSystemStatus({
            running: data.running,
            equity: data.equity,
            cash: data.cash,
            position_count: data.position_count,
            cycle_count: data.cycle_count,
          } as any)
        }
        break
      case 'full_state':
        // Handle full state refresh
        console.log('Received full state:', data)
        break
      case 'risk_alert':
        // Show notification
        console.warn('Risk alert:', data)
        break
      case 'activity':
        // Add to activity log
        addActivityLog(data)
        break
    }
  }

  const subscribe = useCallback((symbols: string[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'subscribe',
        symbols
      }))
    }
  }, [])

  const unsubscribe = useCallback((symbols: string[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'unsubscribe',
        symbols
      }))
    }
  }, [])

  useEffect(() => {
    connect()

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      wsRef.current?.close()
    }
  }, [connect])

  return { subscribe, unsubscribe }
}
