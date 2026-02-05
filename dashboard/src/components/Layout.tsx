import { ReactNode, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  Briefcase,
  Zap,
  Settings,
  BarChart3,
  Wifi,
  WifiOff,
  Play,
  Square,
  ScrollText
} from 'lucide-react'
import { fetchSystemStatus, startTrading, stopTrading } from '../api/client'
import { useWebSocket } from '../hooks/useWebSocket'
import { useTradingStore } from '../stores/tradingStore'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const { wsConnected, systemStatus, setSystemStatus } = useTradingStore()

  // Initialize WebSocket
  useWebSocket()

  // Fetch system status
  const { data: status } = useQuery({
    queryKey: ['systemStatus'],
    queryFn: fetchSystemStatus,
    refetchInterval: 5000,
  })

  useEffect(() => {
    if (status) setSystemStatus(status)
  }, [status, setSystemStatus])

  const navItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/positions', icon: Briefcase, label: 'Positions' },
    { path: '/strategies', icon: Zap, label: 'Strategies' },
    { path: '/analytics', icon: BarChart3, label: 'Analytics' },
    { path: '/activity', icon: ScrollText, label: 'Activity' },
    { path: '/settings', icon: Settings, label: 'Settings' },
  ]

  const handleToggleTrading = async () => {
    if (systemStatus?.running) {
      await stopTrading()
    } else {
      await startTrading()
    }
  }

  const formatTime = () => {
    return new Date().toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'America/New_York'
    })
  }

  return (
    <div className="min-h-screen bg-slate-900 flex">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-800 border-r border-slate-700 flex flex-col">
        {/* Logo */}
        <div className="p-4 border-b border-slate-700">
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Zap className="w-6 h-6 text-primary-500" />
            AI Day Trader
          </h1>
          <p className="text-xs text-slate-400 mt-1">v2.0.0</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map(({ path, icon: Icon, label }) => (
            <Link
              key={path}
              to={path}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                location.pathname === path
                  ? 'bg-primary-600 text-white'
                  : 'text-slate-300 hover:bg-slate-700'
              }`}
            >
              <Icon className="w-5 h-5" />
              {label}
            </Link>
          ))}
        </nav>

        {/* Risk Info */}
        <div className="p-4 border-t border-slate-700">
          <div className="text-sm text-slate-400 mb-2">Portfolio Heat</div>
          <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-orange-500 transition-all"
              style={{ width: `${Math.min((systemStatus as any)?.portfolio_heat || 0, 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-slate-500 mt-1">
            <span>{((systemStatus as any)?.portfolio_heat || 0).toFixed(1)}%</span>
            <span>Max 5%</span>
          </div>
        </div>

        {/* Connection Status */}
        <div className="p-4 border-t border-slate-700 flex items-center gap-2 text-sm">
          {wsConnected ? (
            <>
              <Wifi className="w-4 h-4 text-green-400" />
              <span className="text-green-400">Connected</span>
            </>
          ) : (
            <>
              <WifiOff className="w-4 h-4 text-red-400" />
              <span className="text-red-400">Disconnected</span>
            </>
          )}
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="h-14 bg-slate-800 border-b border-slate-700 flex items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <span className={`px-2 py-1 rounded text-xs font-medium ${
              systemStatus?.mode === 'live' ? 'bg-green-600' :
              systemStatus?.mode === 'paper' ? 'bg-yellow-600' : 'bg-slate-600'
            }`}>
              {systemStatus?.mode?.toUpperCase() || 'OFFLINE'}
            </span>
            <span className="text-slate-400 text-sm">{formatTime()} ET</span>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-sm text-slate-400">Equity</div>
              <div className="text-lg font-semibold">
                ${(systemStatus?.equity || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
            </div>

            <button
              onClick={handleToggleTrading}
              className={`btn flex items-center gap-2 ${
                systemStatus?.running ? 'btn-danger' : 'btn-success'
              }`}
            >
              {systemStatus?.running ? (
                <>
                  <Square className="w-4 h-4" />
                  Stop
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Start
                </>
              )}
            </button>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
