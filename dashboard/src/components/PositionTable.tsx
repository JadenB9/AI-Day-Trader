import { X } from 'lucide-react'
import { closePosition } from '../api/client'
import type { Position } from '../api/client'

interface Props {
  positions: Position[]
}

export default function PositionTable({ positions }: Props) {
  const handleClose = async (symbol: string) => {
    if (confirm(`Close position for ${symbol}?`)) {
      await closePosition(symbol)
    }
  }

  if (positions.length === 0) {
    return (
      <div className="text-center py-8 text-slate-400">
        No open positions
      </div>
    )
  }

  return (
    <table className="w-full">
      <thead>
        <tr className="text-left text-sm text-slate-400 border-b border-slate-700">
          <th className="pb-2">Symbol</th>
          <th className="pb-2">Qty</th>
          <th className="pb-2">Entry</th>
          <th className="pb-2">Current</th>
          <th className="pb-2">P&L</th>
          <th className="pb-2">P&L %</th>
          <th className="pb-2"></th>
        </tr>
      </thead>
      <tbody>
        {positions.map((pos) => (
          <tr key={pos.symbol} className="border-b border-slate-700/50 hover:bg-slate-700/30">
            <td className="py-3">
              <div className="flex items-center gap-2">
                <span className="font-medium">{pos.symbol}</span>
                {pos.asset_class === 'crypto' && (
                  <span className="text-xs px-1.5 py-0.5 bg-purple-600/30 text-purple-300 rounded">
                    CRYPTO
                  </span>
                )}
              </div>
            </td>
            <td className="py-3">
              <span className={pos.side === 'long' ? 'text-green-400' : 'text-red-400'}>
                {pos.qty > 0 ? '+' : ''}{pos.qty}
              </span>
            </td>
            <td className="py-3">${pos.avg_entry_price.toFixed(2)}</td>
            <td className="py-3">${pos.current_price.toFixed(2)}</td>
            <td className={`py-3 ${pos.unrealized_pl >= 0 ? 'profit' : 'loss'}`}>
              {pos.unrealized_pl >= 0 ? '+' : ''}${pos.unrealized_pl.toFixed(2)}
            </td>
            <td className={`py-3 ${pos.unrealized_plpc >= 0 ? 'profit' : 'loss'}`}>
              {pos.unrealized_plpc >= 0 ? '+' : ''}{(pos.unrealized_plpc * 100).toFixed(2)}%
            </td>
            <td className="py-3">
              <button
                onClick={() => handleClose(pos.symbol)}
                className="p-1 hover:bg-slate-600 rounded transition-colors"
                title="Close position"
              >
                <X className="w-4 h-4 text-slate-400 hover:text-red-400" />
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
