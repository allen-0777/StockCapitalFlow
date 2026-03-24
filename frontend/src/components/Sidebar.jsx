import { useEffect, useState } from 'react'
import { Activity, Layers, PieChart, Building2, Star } from 'lucide-react'
import useStore from '../store/useStore'

const tabs = [
  { id: 'overview', icon: <Activity size={20} />, label: '大盤總覽' },
  { id: 'institutional', icon: <Layers size={20} />, label: '法人進出' },
  { id: 'broker', icon: <Building2 size={20} />, label: '分點進出' },
  { id: 'concentration', icon: <PieChart size={20} />, label: '法人持股' },
  { id: 'watchlist', icon: <Star size={20} />, label: '自選股' },
]

export default function Sidebar() {
  const { activeTab, setActiveTab } = useStore()
  const [health, setHealth] = useState({ status: 'loading', last_update: null })

  useEffect(() => {
    fetch('/api/v1/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: 'error', last_update: null }))
  }, [])

  return (
    <div className="flex flex-col space-y-2 z-10 w-full">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => setActiveTab(tab.id)}
          className={`flex items-center space-x-3 px-4 py-3 rounded-2xl transition-all duration-300 ${
            activeTab === tab.id
              ? 'glass-card shadow-sm text-blue-600 font-medium scale-105'
              : 'text-slate-500 hover:bg-white/40 hover:text-slate-700'
          }`}
        >
          {tab.icon}
          <span>{tab.label}</span>
        </button>
      ))}

      <div className="mt-auto mb-4 glass-card p-4 rounded-3xl">
        <div className="text-xs text-slate-400 mb-2 uppercase tracking-wider font-semibold">系統狀態</div>
        <div className="flex items-center space-x-2">
          <span className="relative flex h-3 w-3">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${health.status === 'healthy' ? 'bg-green-400' : 'bg-red-400'}`}></span>
            <span className={`relative inline-flex rounded-full h-3 w-3 ${health.status === 'healthy' ? 'bg-green-500' : 'bg-red-500'}`}></span>
          </span>
          <span className="text-sm font-medium text-slate-600">
            {health.status === 'healthy' ? 'API 連線正常' : health.status === 'loading' ? '連線中...' : 'API 連線失敗'}
          </span>
        </div>
        <div className="text-xs text-slate-400 mt-1 ml-5 space-y-0.5">
          {health.last_institutional &&
          health.last_margin &&
          health.last_institutional !== health.last_margin ? (
            <>
              <div>法人: {health.last_institutional}</div>
              <div>融資券: {health.last_margin}</div>
            </>
          ) : (
            <div>
              最後更新:{' '}
              {health.last_update ?? health.last_institutional ?? health.last_margin ?? '—'}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
