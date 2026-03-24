import { Activity, Layers, Building2, PieChart, Star } from 'lucide-react'
import useStore from '../store/useStore'

const tabs = [
  { id: 'overview', icon: Activity, label: '總覽' },
  { id: 'institutional', icon: Layers, label: '法人' },
  { id: 'broker', icon: Building2, label: '分點' },
  { id: 'concentration', icon: PieChart, label: '持股' },
  { id: 'watchlist', icon: Star, label: '自選' },
]

export default function BottomTabBar() {
  const activeTab = useStore((s) => s.activeTab)
  const setActiveTab = useStore((s) => s.setActiveTab)

  return (
    <nav className="fixed bottom-0 inset-x-0 z-50 h-16 bg-white/95 backdrop-blur-lg border-t border-slate-200/80 flex items-stretch safe-bottom lg:hidden">
      {tabs.map(({ id, icon: Icon, label }) => {
        const active = activeTab === id
        return (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex-1 flex flex-col items-center justify-center gap-0.5 min-h-[44px] transition-colors ${
              active ? 'text-blue-500' : 'text-slate-400'
            }`}
          >
            <Icon size={22} strokeWidth={active ? 2.2 : 1.8} />
            <span className={`text-[10px] font-medium ${active ? 'text-blue-500' : 'text-slate-400'}`}>
              {label}
            </span>
          </button>
        )
      })}
    </nav>
  )
}
