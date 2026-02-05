import { useQuery } from '@tanstack/react-query'
import { BarChart3, TrendingUp, TrendingDown, Target, Clock } from 'lucide-react'
import { fetchRiskMetrics, fetchSystemStatus } from '../api/client'
import { api } from '../api/client'

export default function Analytics() {
  const { data: riskMetrics } = useQuery({
    queryKey: ['riskMetrics'],
    queryFn: fetchRiskMetrics,
    refetchInterval: 10000,
  })

  const { data: systemStatus } = useQuery({
    queryKey: ['systemStatus'],
    queryFn: fetchSystemStatus,
    refetchInterval: 10000,
  })

  // Fetch real trade history from database
  const { data: tradeStats } = useQuery({
    queryKey: ['tradeStats'],
    queryFn: () => api.get('/trades/stats').then(r => r.data).catch(() => null),
    refetchInterval: 30000,
  })

  // Check if we have any real trading data
  const hasTrades = tradeStats?.total_trades > 0

  if (!hasTrades) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center max-w-md">
          <BarChart3 className="w-16 h-16 mx-auto mb-4 text-slate-600" />
          <h2 className="text-xl font-semibold mb-2">No Trading History Yet</h2>
          <p className="text-slate-400 mb-6">
            Analytics will appear here once the trader starts making trades.
            Start the trading engine and let it run to see real performance data.
          </p>
          <div className="bg-slate-800 rounded-lg p-4 text-left">
            <h3 className="font-medium mb-2 text-slate-300">What you'll see here:</h3>
            <ul className="text-sm text-slate-400 space-y-1">
              <li>• Win rate and profit factor</li>
              <li>• Equity curve over time</li>
              <li>• Daily P&L breakdown</li>
              <li>• Strategy performance comparison</li>
              <li>• Trade history and statistics</li>
            </ul>
          </div>
        </div>
      </div>
    )
  }

  // Real data from trade stats
  const winRate = tradeStats.win_rate || 0
  const totalTrades = tradeStats.total_trades || 0
  const wins = tradeStats.wins || 0
  const losses = tradeStats.losses || 0
  const avgWin = tradeStats.avg_win || 0
  const avgLoss = tradeStats.avg_loss || 0
  const profitFactor = avgLoss > 0 ? (wins * avgWin) / (losses * avgLoss) : 0
  const totalPnl = tradeStats.total_pnl || 0

  return (
    <div className="space-y-6">
      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          title="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          icon={Target}
          color="text-green-400"
          subtitle={`${wins} wins / ${losses} losses`}
        />
        <StatCard
          title="Total Trades"
          value={totalTrades}
          icon={BarChart3}
          color="text-primary-500"
          subtitle="All time"
        />
        <StatCard
          title="Avg Win"
          value={`$${avgWin.toFixed(2)}`}
          icon={TrendingUp}
          color="text-green-400"
          subtitle="Per winning trade"
        />
        <StatCard
          title="Avg Loss"
          value={`$${avgLoss.toFixed(2)}`}
          icon={TrendingDown}
          color="text-red-400"
          subtitle="Per losing trade"
        />
      </div>

      {/* Summary Card */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Performance Summary</h3>
        <div className="grid grid-cols-3 gap-6">
          <div>
            <p className="text-slate-400 text-sm">Total P&L</p>
            <p className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-slate-400 text-sm">Profit Factor</p>
            <p className="text-2xl font-bold text-primary-500">
              {profitFactor.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-slate-400 text-sm">Trading Since</p>
            <p className="text-2xl font-bold text-slate-300">
              {tradeStats.first_trade_date || 'N/A'}
            </p>
          </div>
        </div>
      </div>

      {/* Note about real data */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-center text-slate-400 text-sm">
        All data shown is from real trades executed by the system.
        No simulated or mock data is displayed.
      </div>
    </div>
  )
}

function StatCard({ title, value, icon: Icon, color, subtitle }: {
  title: string
  value: string | number
  icon: any
  color: string
  subtitle?: string
}) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-slate-400">{title}</p>
          <p className={`text-2xl font-bold ${color}`}>{value}</p>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
        <Icon className={`w-8 h-8 ${color} opacity-50`} />
      </div>
    </div>
  )
}
