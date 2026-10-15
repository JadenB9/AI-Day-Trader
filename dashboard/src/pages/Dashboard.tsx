import { useQuery } from '@tanstack/react-query'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Briefcase,
  AlertTriangle,
  Activity
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer
} from 'recharts'
import { fetchPositions, fetchRiskMetrics, closeAllPositions, fetchEquityHistory } from '../api/client'
import { useTradingStore } from '../stores/tradingStore'
import PositionTable from '../components/PositionTable'

export default function Dashboard() {
  const { signals, systemStatus } = useTradingStore()

  const { data: positionsData } = useQuery({
    queryKey: ['positions'],
    queryFn: fetchPositions,
    refetchInterval: 3000,
  })

  const { data: riskMetrics } = useQuery({
    queryKey: ['riskMetrics'],
    queryFn: fetchRiskMetrics,
    refetchInterval: 5000,
  })

  // Real equity history from Alpaca
  const { data: equityData } = useQuery({
    queryKey: ['equityHistory'],
    queryFn: () => fetchEquityHistory('1D', '5Min'),
    refetchInterval: 60000, // Refresh every minute
  })

  const positions = positionsData?.positions || []
  const totalPl = positionsData?.total_unrealized_pl || 0
  const totalValue = positionsData?.total_value || 0

  const handleCloseAll = async () => {
    if (confirm('Close all positions? This cannot be undone.')) {
      await closeAllPositions()
    }
  }

  // Format equity history for chart - REAL DATA ONLY
  const equityHistory = (equityData?.data || []).map((point: any) => ({
    time: new Date(point.timestamp).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    }),
    equity: point.equity
  }))

  return (
    <div className="space-y-6">
      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          title="Portfolio Value"
          value={`$${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
          icon={DollarSign}
          color="text-primary-500"
        />
        <StatCard
          title="Unrealized P&L"
          value={`${totalPl >= 0 ? '+' : ''}$${totalPl.toFixed(2)}`}
          icon={totalPl >= 0 ? TrendingUp : TrendingDown}
          color={totalPl >= 0 ? 'text-green-400' : 'text-red-400'}
          subtitle={`${((totalPl / (systemStatus?.equity || 1)) * 100).toFixed(2)}%`}
        />
        <StatCard
          title="Open Positions"
          value={positions.length}
          icon={Briefcase}
          color="text-yellow-400"
          subtitle={`/ ${riskMetrics?.max_positions || 20} max`}
        />
        <StatCard
          title="Daily P&L"
          value={`${(riskMetrics?.daily_pnl_pct || 0) >= 0 ? '+' : ''}${(riskMetrics?.daily_pnl_pct || 0).toFixed(2)}%`}
          icon={Activity}
          color={(riskMetrics?.daily_pnl_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}
        />
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-3 gap-6">
        {/* Positions */}
        <div className="col-span-2 card">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">Open Positions</h2>
            {positions.length > 0 && (
              <button onClick={handleCloseAll} className="btn btn-danger text-sm">
                Close All
              </button>
            )}
          </div>
          <PositionTable positions={positions} />
        </div>

        {/* Right Column */}
        <div className="space-y-6">
          {/* Risk Metrics */}
          <div className="card">
            <h2 className="text-lg font-semibold mb-4">Risk Metrics</h2>
            <div className="space-y-4">
              <RiskBar
                label="Portfolio Heat"
                value={riskMetrics?.portfolio_heat || 0}
                max={5}
                warning={3}
                danger={4}
              />
              <RiskBar
                label="Daily Loss Limit"
                value={Math.abs(riskMetrics?.daily_pnl_pct || 0)}
                max={riskMetrics?.max_daily_loss || 2}
                warning={1.5}
                danger={1.8}
                inverse
              />
              <RiskBar
                label="Weekly Loss Limit"
                value={Math.abs(riskMetrics?.weekly_pnl_pct || 0)}
                max={riskMetrics?.max_weekly_loss || 6}
                warning={4}
                danger={5}
                inverse
              />
            </div>

            {riskMetrics?.is_halted && (
              <div className="mt-4 p-3 bg-red-900/50 border border-red-700 rounded-lg flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-400" />
                <span className="text-red-400 text-sm">
                  Trading halted: {riskMetrics.halt_reason}
                </span>
              </div>
            )}
          </div>

          {/* Recent Signals */}
          <div className="card">
            <h2 className="text-lg font-semibold mb-4">Recent Signals</h2>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {signals.length === 0 ? (
                <p className="text-slate-400 text-sm">No signals yet</p>
              ) : (
                signals.slice(0, 10).map((signal, i) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-slate-700/50 rounded">
                    <div>
                      <span className="font-medium">{signal.symbol}</span>
                      <span className={`ml-2 text-xs ${
                        signal.direction === 'long' ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {signal.direction?.toUpperCase()}
                      </span>
                    </div>
                    <span className="text-sm text-slate-400">
                      {(signal.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Equity Chart - REAL DATA ONLY */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">Equity Curve</h2>
        <div className="h-64">
          {equityHistory.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equityHistory}>
                <XAxis dataKey="time" stroke="#64748b" fontSize={12} />
                <YAxis stroke="#64748b" fontSize={12} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }}
                  formatter={(value: number) => [`$${value.toFixed(2)}`, 'Equity']}
                />
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="#0ea5e9"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-400">
              <div className="text-center">
                <p>No trading history yet</p>
                <p className="text-sm text-slate-500 mt-1">Chart will populate once trading begins</p>
              </div>
            </div>
          )}
        </div>
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

function RiskBar({ label, value, max, warning, danger, inverse }: {
  label: string
  value: number
  max: number
  warning: number
  danger: number
  inverse?: boolean
}) {
  const pct = Math.min((value / max) * 100, 100)
  let color = 'bg-green-500'
  if (inverse ? value <= danger : value >= danger) color = 'bg-red-500'
  else if (inverse ? value <= warning : value >= warning) color = 'bg-yellow-500'

  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="text-slate-400">{label}</span>
        <span>{value.toFixed(1)}% / {max}%</span>
      </div>
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
