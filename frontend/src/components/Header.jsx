import { Search, Droplets, RefreshCw } from 'lucide-react'

export default function Header({ onRefresh }) {
  return (
    <header className="flex items-center justify-between mb-8 z-10">
      <div className="flex items-center space-x-3">
        <div className="w-12 h-12 bg-gradient-to-br from-blue-400 to-cyan-300 liquid-shape flex items-center justify-center text-white shadow-lg shadow-blue-200">
          <Droplets size={24} />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-800 tracking-tight">
            籌碼流動 <span className="font-light text-slate-500">LiquidChip</span>
          </h1>
          <p className="text-sm text-slate-500">台股資金動能自動化追蹤</p>
        </div>
      </div>

      <div className="flex items-center space-x-4">
        <div className="relative group">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search size={18} className="text-slate-400 group-focus-within:text-blue-500 transition-colors" />
          </div>
          <input
            type="text"
            placeholder="搜尋股號 / 股名..."
            className="pl-10 pr-4 py-2.5 w-64 glass-card rounded-full focus:outline-none focus:ring-2 focus:ring-blue-400/50 transition-all text-sm placeholder-slate-400"
          />
        </div>
        <button
          onClick={onRefresh}
          className="p-2.5 glass-card rounded-full hover:bg-white/80 transition-colors text-slate-600"
        >
          <RefreshCw size={18} />
        </button>
        <div className="w-10 h-10 rounded-full bg-slate-200 border-2 border-white shadow-sm overflow-hidden flex items-center justify-center">
          <img
            src="https://api.dicebear.com/7.x/notionists/svg?seed=Felix"
            alt="User"
            className="w-full h-full object-cover"
          />
        </div>
      </div>
    </header>
  )
}
