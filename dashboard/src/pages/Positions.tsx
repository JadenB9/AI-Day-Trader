import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import {
  fetchPositions,
  fetchOrders,
  closePosition,
  closeAllPositions,
  cancelOrder,
  cancelAllOrders,
  submitOrder,
  type Position,
  type Order
} from '../api/client'

export default function Positions() {
  const [showOrderForm, setShowOrderForm] = useState(false)
  const [orderForm, setOrderForm] = useState({
    symbol: '',
    qty: '',
    side: 'buy',
    type: 'market',
    limit_price: '',
  })

  const { data: positionsData, refetch: refetchPositions } = useQuery({
    queryKey: ['positions'],
    queryFn: fetchPositions,
    refetchInterval: 3000,
  })

  const { data: ordersData, refetch: refetchOrders } = useQuery({
    queryKey: ['orders'],
    queryFn: fetchOrders,
    refetchInterval: 3000,
  })

  const positions: Position[] = positionsData?.positions || []
  const orders: Order[] = ordersData?.orders || []

  const handleClose = async (symbol: string) => {
    await closePosition(symbol)
    refetchPositions()
  }

  const handleCloseAll = async () => {
    if (confirm('Close all positions?')) {
      await closeAllPositions()
      refetchPositions()
    }
  }

  const handleCancelOrder = async (orderId: string) => {
    await cancelOrder(orderId)
    refetchOrders()
  }

  const handleCancelAll = async () => {
    if (confirm('Cancel all orders?')) {
      await cancelAllOrders()
      refetchOrders()
    }
  }

  const handleSubmitOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await submitOrder({
        symbol: orderForm.symbol.toUpperCase(),
        qty: parseFloat(orderForm.qty),
        side: orderForm.side,
        order_type: orderForm.type,
        limit_price: orderForm.limit_price ? parseFloat(orderForm.limit_price) : undefined,
      })
      setShowOrderForm(false)
      setOrderForm({ symbol: '', qty: '', side: 'buy', type: 'market', limit_price: '' })
      refetchOrders()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Order failed')
    }
  }

  return (
    <div className="space-y-6">
      {/* Positions */}
      <div className="card">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">Open Positions ({positions.length})</h2>
          <div className="flex gap-2">
            <button onClick={() => setShowOrderForm(true)} className="btn btn-primary flex items-center gap-2">
              <Plus className="w-4 h-4" />
              New Order
            </button>
            {positions.length > 0 && (
              <button onClick={handleCloseAll} className="btn btn-danger">
                Close All
              </button>
            )}
          </div>
        </div>

        <table className="w-full">
          <thead>
            <tr className="text-left text-sm text-slate-400 border-b border-slate-700">
              <th className="pb-2">Symbol</th>
              <th className="pb-2">Side</th>
              <th className="pb-2">Qty</th>
              <th className="pb-2">Entry</th>
              <th className="pb-2">Current</th>
              <th className="pb-2">Market Value</th>
              <th className="pb-2">P&L</th>
              <th className="pb-2">P&L %</th>
              <th className="pb-2">Today</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => (
              <tr key={pos.symbol} className="border-b border-slate-700/50">
                <td className="py-3 font-medium">
                  {pos.symbol}
                  {pos.asset_class === 'crypto' && (
                    <span className="ml-2 text-xs px-1.5 py-0.5 bg-purple-600/30 text-purple-300 rounded">
                      CRYPTO
                    </span>
                  )}
                </td>
                <td className={`py-3 ${pos.side === 'long' ? 'text-green-400' : 'text-red-400'}`}>
                  {pos.side.toUpperCase()}
                </td>
                <td className="py-3">{pos.qty}</td>
                <td className="py-3">${pos.avg_entry_price.toFixed(2)}</td>
                <td className="py-3">${pos.current_price.toFixed(2)}</td>
                <td className="py-3">${pos.market_value.toFixed(2)}</td>
                <td className={`py-3 ${pos.unrealized_pl >= 0 ? 'profit' : 'loss'}`}>
                  {pos.unrealized_pl >= 0 ? '+' : ''}${pos.unrealized_pl.toFixed(2)}
                </td>
                <td className={`py-3 ${pos.unrealized_plpc >= 0 ? 'profit' : 'loss'}`}>
                  {(pos.unrealized_plpc * 100).toFixed(2)}%
                </td>
                <td className={`py-3 ${pos.change_today >= 0 ? 'profit' : 'loss'}`}>
                  {(pos.change_today * 100).toFixed(2)}%
                </td>
                <td className="py-3">
                  <button onClick={() => handleClose(pos.symbol)} className="text-red-400 hover:text-red-300">
                    <X className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
            {positions.length === 0 && (
              <tr>
                <td colSpan={10} className="py-8 text-center text-slate-400">
                  No open positions
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Orders */}
      <div className="card">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">Open Orders ({orders.length})</h2>
          {orders.length > 0 && (
            <button onClick={handleCancelAll} className="btn btn-danger">
              Cancel All
            </button>
          )}
        </div>

        <table className="w-full">
          <thead>
            <tr className="text-left text-sm text-slate-400 border-b border-slate-700">
              <th className="pb-2">Symbol</th>
              <th className="pb-2">Side</th>
              <th className="pb-2">Type</th>
              <th className="pb-2">Qty</th>
              <th className="pb-2">Limit</th>
              <th className="pb-2">Stop</th>
              <th className="pb-2">Filled</th>
              <th className="pb-2">Status</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.order_id} className="border-b border-slate-700/50">
                <td className="py-3 font-medium">{order.symbol}</td>
                <td className={`py-3 ${order.side === 'buy' ? 'text-green-400' : 'text-red-400'}`}>
                  {order.side.toUpperCase()}
                </td>
                <td className="py-3">{order.type}</td>
                <td className="py-3">{order.qty}</td>
                <td className="py-3">{order.limit_price ? `$${order.limit_price.toFixed(2)}` : '-'}</td>
                <td className="py-3">{order.stop_price ? `$${order.stop_price.toFixed(2)}` : '-'}</td>
                <td className="py-3">{order.filled_qty} / {order.qty}</td>
                <td className="py-3">
                  <span className={`px-2 py-1 rounded text-xs ${
                    order.status === 'filled' ? 'bg-green-600' :
                    order.status === 'cancelled' ? 'bg-red-600' : 'bg-yellow-600'
                  }`}>
                    {order.status.toUpperCase()}
                  </span>
                </td>
                <td className="py-3">
                  <button onClick={() => handleCancelOrder(order.order_id)} className="text-red-400 hover:text-red-300">
                    <X className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
            {orders.length === 0 && (
              <tr>
                <td colSpan={9} className="py-8 text-center text-slate-400">
                  No open orders
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Order Form Modal */}
      {showOrderForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="card w-96">
            <h3 className="text-lg font-semibold mb-4">New Order</h3>
            <form onSubmit={handleSubmitOrder} className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Symbol</label>
                <input
                  type="text"
                  className="input w-full"
                  value={orderForm.symbol}
                  onChange={(e) => setOrderForm({ ...orderForm, symbol: e.target.value })}
                  placeholder="AAPL or BTC/USD"
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Side</label>
                  <select
                    className="input w-full"
                    value={orderForm.side}
                    onChange={(e) => setOrderForm({ ...orderForm, side: e.target.value })}
                  >
                    <option value="buy">Buy</option>
                    <option value="sell">Sell</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Qty</label>
                  <input
                    type="number"
                    className="input w-full"
                    value={orderForm.qty}
                    onChange={(e) => setOrderForm({ ...orderForm, qty: e.target.value })}
                    step="0.01"
                    min="0"
                    required
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Type</label>
                  <select
                    className="input w-full"
                    value={orderForm.type}
                    onChange={(e) => setOrderForm({ ...orderForm, type: e.target.value })}
                  >
                    <option value="market">Market</option>
                    <option value="limit">Limit</option>
                    <option value="stop">Stop</option>
                    <option value="stop_limit">Stop Limit</option>
                  </select>
                </div>
                {(orderForm.type === 'limit' || orderForm.type === 'stop_limit') && (
                  <div>
                    <label className="block text-sm text-slate-400 mb-1">Limit Price</label>
                    <input
                      type="number"
                      className="input w-full"
                      value={orderForm.limit_price}
                      onChange={(e) => setOrderForm({ ...orderForm, limit_price: e.target.value })}
                      step="0.01"
                    />
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setShowOrderForm(false)} className="btn bg-slate-700">
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Submit Order
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
