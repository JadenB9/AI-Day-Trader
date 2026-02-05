import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Terminal,
  Brain,
  TrendingUp,
  AlertTriangle,
  Search,
  Database,
  Zap,
  CheckCircle,
  XCircle,
  Clock,
  Filter,
  Trash2,
  Download,
  RefreshCw
} from 'lucide-react'
import { useTradingStore } from '../stores/tradingStore'
import { api } from '../api/client'

interface LogEntry {
  id: string
  timestamp: string
  type: 'info' | 'trade' | 'ai' | 'data' | 'signal' | 'error' | 'research'
  title: string
  message: string
  details?: Record<string, any>
}

const typeConfig = {
  info: { icon: Terminal, color: 'text-slate-400', bg: 'bg-slate-700' },
  trade: { icon: TrendingUp, color: 'text-green-400', bg: 'bg-green-900/30' },
  ai: { icon: Brain, color: 'text-purple-400', bg: 'bg-purple-900/30' },
  data: { icon: Database, color: 'text-blue-400', bg: 'bg-blue-900/30' },
  signal: { icon: Zap, color: 'text-yellow-400', bg: 'bg-yellow-900/30' },
  error: { icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-900/30' },
  research: { icon: Search, color: 'text-cyan-400', bg: 'bg-cyan-900/30' },
}

export default function Activity() {
  const [filter, setFilter] = useState<string>('all')
  const [autoScroll, setAutoScroll] = useState(true)
  const logContainerRef = useRef<HTMLDivElement>(null)
  const { wsConnected, activityLogs, setActivityLogs } = useTradingStore()

  // Fetch recent activity from backend on mount
  const { data: recentActivity, refetch } = useQuery({
    queryKey: ['recentActivity'],
    queryFn: () => api.get('/system/activity?limit=200').then(r => r.data),
    refetchInterval: false, // Only manual refresh
  })

  // Load initial logs from API
  useEffect(() => {
    if (recentActivity?.logs && activityLogs.length === 0) {
      setActivityLogs(recentActivity.logs)
    }
  }, [recentActivity, activityLogs.length, setActivityLogs])

  // Use activityLogs from store (updated via WebSocket)
  const logs = activityLogs

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const filteredLogs = filter === 'all'
    ? logs
    : logs.filter(l => l.type === filter)

  const clearLogs = () => setActivityLogs([])

  const refreshLogs = () => refetch()

  const exportLogs = () => {
    const text = logs.map(l =>
      `[${l.timestamp}] [${l.type.toUpperCase()}] ${l.title}: ${l.message}`
    ).join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `activity-log-${new Date().toISOString().slice(0,10)}.txt`
    a.click()
  }

  const formatTime = (ts: string) => {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">Activity Log</h1>
          <span className={`px-2 py-1 rounded text-xs ${
            wsConnected ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
          }`}>
            {wsConnected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Filter */}
          <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-1">
            <Filter className="w-4 h-4 text-slate-400 ml-2" />
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="bg-transparent text-sm text-slate-300 pr-2 py-1 outline-none"
            >
              <option value="all">All Events</option>
              <option value="ai">AI Decisions</option>
              <option value="trade">Trades</option>
              <option value="signal">Signals</option>
              <option value="research">Research</option>
              <option value="data">Data</option>
              <option value="error">Errors</option>
            </select>
          </div>

          {/* Auto-scroll toggle */}
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`px-3 py-1.5 rounded text-sm ${
              autoScroll ? 'bg-primary-600 text-white' : 'bg-slate-700 text-slate-300'
            }`}
          >
            Auto-scroll
          </button>

          {/* Refresh */}
          <button
            onClick={refreshLogs}
            className="p-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300"
            title="Refresh logs"
          >
            <RefreshCw className="w-4 h-4" />
          </button>

          {/* Clear */}
          <button
            onClick={clearLogs}
            className="p-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300"
            title="Clear logs"
          >
            <Trash2 className="w-4 h-4" />
          </button>

          {/* Export */}
          <button
            onClick={exportLogs}
            className="p-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300"
            title="Export logs"
          >
            <Download className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-6 gap-2 mb-4">
        {Object.entries(typeConfig).map(([type, config]) => {
          const count = logs.filter(l => l.type === type).length
          const Icon = config.icon
          return (
            <button
              key={type}
              onClick={() => setFilter(filter === type ? 'all' : type)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
                filter === type ? config.bg + ' ring-1 ring-white/20' : 'bg-slate-800 hover:bg-slate-700'
              }`}
            >
              <Icon className={`w-4 h-4 ${config.color}`} />
              <span className="text-sm text-slate-300 capitalize">{type}</span>
              <span className={`text-xs ${config.color}`}>{count}</span>
            </button>
          )
        })}
      </div>

      {/* Log Container */}
      <div
        ref={logContainerRef}
        className="flex-1 bg-slate-900 rounded-lg border border-slate-700 overflow-y-auto font-mono text-sm"
      >
        {filteredLogs.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-500">
            <div className="text-center">
              <Terminal className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No activity yet</p>
              <p className="text-xs mt-1">Events will appear here when the system is running</p>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-slate-800">
            {filteredLogs.map((log) => {
              const config = typeConfig[log.type]
              const Icon = config.icon
              return (
                <div
                  key={log.id}
                  className={`p-3 hover:bg-slate-800/50 transition-colors ${config.bg}`}
                >
                  <div className="flex items-start gap-3">
                    <Icon className={`w-4 h-4 mt-0.5 ${config.color}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`font-medium ${config.color}`}>
                          {log.title}
                        </span>
                        <span className="text-slate-500 text-xs">
                          {formatTime(log.timestamp)}
                        </span>
                      </div>
                      <p className="text-slate-300 mt-0.5">{log.message}</p>
                      {log.details && (
                        <div className="mt-2 text-xs text-slate-500 bg-slate-800/50 rounded p-2">
                          {Object.entries(log.details).map(([key, value]) => (
                            <div key={key} className="flex gap-2">
                              <span className="text-slate-400">{key}:</span>
                              <span className="text-slate-300">
                                {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
