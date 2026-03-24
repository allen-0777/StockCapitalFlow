import { TrendingUp, TrendingDown } from 'lucide-react'

export default function Widget1_Institutional({ data }) {
  if (!data) {
    return (
      <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 flex items-center justify-center h-36 sm:h-48">
        <p className="text-slate-400 text-sm">載入中... 若首次使用請等待每日 16:30 排程執行，或手動觸發爬蟲。</p>
      </div>
    )
  }

  const items = [
    { key: 'foreign', label: '外資及陸資', net: data.institutional.foreign },
    { key: 'trust', label: '投信', net: data.institutional.trust },
    { key: 'dealer', label: '自營商', net: data.institutional.dealer },
  ]

  return (
    <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 relative group">
      <div className="absolute inset-0 overflow-hidden rounded-2xl sm:rounded-[2rem] pointer-events-none">
        <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-br from-white/40 to-transparent rounded-full -translate-y-1/2 translate-x-1/2"></div>
      </div>

      <div className="flex justify-between items-end mb-4 sm:mb-8">
        <div>
          <h2 className="text-base sm:text-xl font-bold text-slate-800 flex items-center">
            三大法人買賣超
            <span className="ml-2 px-2 py-0.5 rounded-full bg-red-100 text-red-600 text-[10px] sm:text-xs font-semibold">台股上市</span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5 sm:mt-1">{data.institutional_date ?? data.date} 盤後資料</p>
        </div>
        <div className="text-right">
          <div className={`text-xl sm:text-3xl font-black drop-shadow-sm flex items-center justify-end ${data.institutional.total >= 0 ? 'text-red-500' : 'text-green-500'}`}>
            {data.institutional.total >= 0 ? '+' : ''}{data.institutional.total}
            <span className="text-sm sm:text-lg font-medium ml-1">億</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 sm:gap-4">
        {items.map(({ key, label, net }) => {
          const isBuy = net >= 0
          return (
            <div key={key} className="bg-white/50 rounded-xl sm:rounded-3xl p-3 sm:p-5 hover:bg-white/70 transition-colors border border-white/60">
              <div className="text-[11px] sm:text-sm text-slate-500 mb-1 sm:mb-2 font-medium">{label}</div>
              <div className={`text-base sm:text-2xl font-bold flex items-center ${isBuy ? 'text-red-500' : 'text-green-500'}`}>
                {isBuy ? <TrendingUp size={16} className="mr-1 hidden sm:block" /> : <TrendingDown size={16} className="mr-1 hidden sm:block" />}
                {net > 0 ? `+${net}` : net}
              </div>
              <div className="mt-2 sm:mt-4 h-1.5 sm:h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-1000 ease-out ${isBuy ? 'bg-gradient-to-r from-red-300 to-red-500' : 'bg-gradient-to-r from-green-300 to-green-500'}`}
                  style={{ width: `${Math.min(Math.abs(net) / 200 * 100, 100)}%` }}
                ></div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
