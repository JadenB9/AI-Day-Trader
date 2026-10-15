import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Zap, Settings } from 'lucide-react'
import { fetchStrategies, toggleStrategy, updateStrategyParams, type Strategy } from '../api/client'

export default function Strategies() {
  const queryClient = useQueryClient()
  const [editingStrategy, setEditingStrategy] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['strategies'],
    queryFn: fetchStrategies,
    refetchInterval: 10000,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      toggleStrategy(name, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
    },
  })

  const strategies: Strategy[] = data?.strategies || []

  const handleToggle = (name: string, currentEnabled: boolean) => {
    toggleMutation.mutate({ name, enabled: !currentEnabled })
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Trading Strategies</h1>
        <div className="text-sm text-slate-400">
          {strategies.filter(s => s.enabled).length} of {strategies.length} active
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {strategies.map((strategy) => (
          <div key={strategy.name} className="card">
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${
                  strategy.enabled ? 'bg-green-600/20' : 'bg-slate-700'
                }`}>
                  <Zap className={`w-5 h-5 ${
                    strategy.enabled ? 'text-green-400' : 'text-slate-400'
                  }`} />
                </div>
                <div>
                  <h3 className="font-semibold">{formatStrategyName(strategy.name)}</h3>
                  <p className="text-sm text-slate-400">{strategy.description}</p>
                </div>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={strategy.enabled}
                  onChange={() => handleToggle(strategy.name, strategy.enabled)}
                />
                <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
              </label>
            </div>

            <div className="grid grid-cols-3 gap-4 text-center py-4 border-t border-slate-700">
              <div>
                <p className="text-2xl font-bold">{strategy.signals_generated}</p>
                <p className="text-xs text-slate-400">Signals</p>
              </div>
              <div>
                <p className={`text-2xl font-bold ${
                  strategy.win_rate >= 50 ? 'text-green-400' : 'text-red-400'
                }`}>
                  {strategy.win_rate.toFixed(0)}%
                </p>
                <p className="text-xs text-slate-400">Win Rate</p>
              </div>
              <div>
                <button
                  onClick={() => setEditingStrategy(editingStrategy === strategy.name ? null : strategy.name)}
                  className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
                >
                  <Settings className="w-5 h-5 text-slate-400" />
                </button>
              </div>
            </div>

            {editingStrategy === strategy.name && (
              <div className="pt-4 border-t border-slate-700">
                <h4 className="text-sm font-medium mb-3">Parameters</h4>
                <div className="space-y-2">
                  {Object.entries(strategy.params).map(([key, value]) => (
                    <div key={key} className="flex justify-between items-center">
                      <span className="text-sm text-slate-400">{formatParamName(key)}</span>
                      <input
                        type="text"
                        className="input w-24 text-sm"
                        defaultValue={String(value)}
                        onBlur={(e) => {
                          // Save on blur
                          const newValue = parseFloat(e.target.value) || e.target.value
                          updateStrategyParams(strategy.name, { [key]: newValue })
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {strategies.length === 0 && (
        <div className="card text-center py-12">
          <p className="text-slate-400">No strategies loaded</p>
        </div>
      )}
    </div>
  )
}

function formatStrategyName(name: string): string {
  return name
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function formatParamName(name: string): string {
  return name
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .toLowerCase()
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}
