import { Search, Droplets, RefreshCw } from 'lucide-react'

export default function Header({ onRefresh }) {
  return (
    <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-lg border-b border-slate-100 px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between">
      {/* Left: Logo + Title */}
      <div className="flex items-center gap-2 sm:gap-3">
        <div className="w-8 h-8 sm:w-10 sm:h-10 bg-gradient-to-br from-blue-400 to-cyan-300 rounded-xl sm:liquid-shape flex items-center justify-center text-white shadow-md shadow-blue-200/50">
          <Droplets size={18} className="sm:hidden" />
          <Droplets size={22} className="hidden sm:block" />
        </div>
        <div>
          <h1 className="text-lg sm:text-xl font-bold text-slate-800 tracking-tight">
            籌碼流動
            <span className="hidden sm:inline font-light text-slate-500"> LiquidChip</span>
          </h1>
          <p className="hidden sm:block text-xs text-slate-500">台股資金動能自動化追蹤</p>
        </div>
      </div>

      {/* Right: Search + Refresh + Avatar */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Desktop search bar */}
        <div className="relative group hidden sm:block">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search size={16} className="text-slate-400 group-focus-within:text-blue-500 transition-colors" />
          </div>
          <input
            type="text"
            placeholder="搜尋股號 / 股名..."
            className="pl-9 pr-4 py-2 w-48 lg:w-64 glass-card rounded-full focus:outline-none focus:ring-2 focus:ring-blue-400/50 transition-all text-sm placeholder-slate-400"
          />
        </div>

        {/* Mobile search icon */}
        <button className="p-2 rounded-full text-slate-500 hover:bg-slate-100 transition-colors sm:hidden">
          <Search size={20} />
        </button>

        {/* Refresh */}
        <button
          onClick={onRefresh}
          className="p-2 rounded-full text-slate-500 hover:bg-slate-100 transition-colors"
        >
          <RefreshCw size={18} />
        </button>

        {/* Avatar (desktop only) */}
        <div className="hidden sm:flex w-9 h-9 rounded-full bg-slate-200 border-2 border-white shadow-sm overflow-hidden items-center justify-center">
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
