import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Save, RefreshCw } from 'lucide-react'
import { fetchSettings, updateSettings } from '../api/client'
import { api } from '../api/client'

const CATEGORIES = [
  { key: 'alpaca', label: 'Alpaca', description: 'API credentials and trading mode' },
  { key: 'scanner', label: 'Scanner', description: 'Pre-market scanner filters' },
  { key: 'position_sizing', label: 'Position Sizing', description: 'Risk per trade and sizing method' },
  { key: 'stops', label: 'Stops', description: 'Stop loss configuration' },
  { key: 'portfolio', label: 'Portfolio', description: 'Position limits and risk limits' },
  { key: 'ai', label: 'AI', description: 'Claude AI decision engine' },
  { key: 'trading_hours', label: 'Trading Hours', description: 'Market hours and extended hours' },
  { key: 'crypto', label: 'Crypto', description: '24/7 cryptocurrency trading' },
  { key: 'hft', label: 'HFT', description: 'High-frequency trading mode' },
  { key: 'dashboard', label: 'Dashboard', description: 'Web dashboard settings' },
]

export default function Settings() {
  const queryClient = useQueryClient()
  const [activeCategory, setActiveCategory] = useState('alpaca')
  const [editedSettings, setEditedSettings] = useState<Record<string, any>>({})
  const [saving, setSaving] = useState(false)

  const { data: settings, refetch } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      for (const [category, values] of Object.entries(editedSettings)) {
        if (Object.keys(values).length > 0) {
          await updateSettings(category, values)
        }
      }
    },
    onSuccess: () => {
      setEditedSettings({})
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  const handleReload = async () => {
    await api.post('/settings/reload')
    refetch()
  }

  const handleChange = (category: string, key: string, value: any) => {
    setEditedSettings(prev => ({
      ...prev,
      [category]: {
        ...(prev[category] || {}),
        [key]: value
      }
    }))
  }

  const handleSave = async () => {
    setSaving(true)
    await saveMutation.mutateAsync()
    setSaving(false)
  }

  const currentSettings = settings?.[activeCategory] || {}
  const currentEdits = editedSettings[activeCategory] || {}

  const hasChanges = Object.keys(editedSettings).some(k => Object.keys(editedSettings[k]).length > 0)

  return (
    <div className="flex gap-6">
      {/* Sidebar */}
      <div className="w-64 space-y-1">
        {CATEGORIES.map(({ key, label, description }) => (
          <button
            key={key}
            onClick={() => setActiveCategory(key)}
            className={`w-full text-left p-3 rounded-lg transition-colors ${
              activeCategory === key
                ? 'bg-primary-600 text-white'
                : 'hover:bg-slate-700 text-slate-300'
            }`}
          >
            <div className="font-medium">{label}</div>
            <div className={`text-xs ${activeCategory === key ? 'text-primary-200' : 'text-slate-500'}`}>
              {description}
            </div>
          </button>
        ))}
      </div>

      {/* Settings Panel */}
      <div className="flex-1 card">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold">
            {CATEGORIES.find(c => c.key === activeCategory)?.label} Settings
          </h2>
          <div className="flex gap-2">
            <button onClick={handleReload} className="btn bg-slate-700 flex items-center gap-2">
              <RefreshCw className="w-4 h-4" />
              Reload
            </button>
            <button
              onClick={handleSave}
              disabled={!hasChanges || saving}
              className={`btn flex items-center gap-2 ${
                hasChanges ? 'btn-primary' : 'bg-slate-700 opacity-50'
              }`}
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>

        <div className="space-y-4">
          {Object.entries(currentSettings).map(([key, value]) => (
            <SettingField
              key={key}
              name={key}
              value={currentEdits[key] !== undefined ? currentEdits[key] : value}
              onChange={(newValue) => handleChange(activeCategory, key, newValue)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function SettingField({ name, value, onChange }: {
  name: string
  value: any
  onChange: (value: any) => void
}) {
  const isSecret = name.toLowerCase().includes('key') || name.toLowerCase().includes('secret')
  const isBool = typeof value === 'boolean'
  const isList = Array.isArray(value)

  const label = name
    .replace(/_/g, ' ')
    .split(' ')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')

  return (
    <div className="flex justify-between items-center py-3 border-b border-slate-700">
      <div>
        <label className="font-medium">{label}</label>
        <p className="text-xs text-slate-500">{getSettingDescription(name)}</p>
      </div>
      <div className="w-64">
        {isBool ? (
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              className="sr-only peer"
              checked={value}
              onChange={(e) => onChange(e.target.checked)}
            />
            <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
          </label>
        ) : isList ? (
          <input
            type="text"
            className="input w-full"
            value={value.join(', ')}
            onChange={(e) => onChange(e.target.value.split(',').map(s => s.trim()))}
          />
        ) : isSecret ? (
          <input
            type="password"
            className="input w-full"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="••••••••"
          />
        ) : (
          <input
            type={typeof value === 'number' ? 'number' : 'text'}
            className="input w-full"
            value={value}
            onChange={(e) => {
              const v = e.target.value
              onChange(typeof value === 'number' ? parseFloat(v) || 0 : v)
            }}
            step={typeof value === 'number' && value < 1 ? '0.01' : '1'}
          />
        )}
      </div>
    </div>
  )
}

function getSettingDescription(name: string): string {
  const descriptions: Record<string, string> = {
    enabled: 'Enable or disable this feature',
    api_key: 'API authentication key',
    secret_key: 'API secret key',
    trading_mode: 'paper or live trading',
    max_positions: 'Maximum number of open positions',
    max_portfolio_heat: 'Maximum total risk exposure',
    max_daily_loss: 'Stop trading after this daily loss',
    max_weekly_loss: 'Stop trading after this weekly loss',
    risk_per_trade: 'Risk percentage per trade',
    max_position_pct: 'Max position size as % of equity',
    cycle_time_ms: 'Trading cycle interval in milliseconds',
    symbols: 'List of symbols to trade',
    min_gap_percent: 'Minimum gap % for scanner',
    max_gap_percent: 'Maximum gap % for scanner',
    confidence_threshold: 'Minimum AI confidence to trade',
    extended_hours_enabled: 'Enable pre-market and after-hours',
  }
  return descriptions[name] || ''
}
