import { DollarSign, TrendingUp, TrendingDown } from 'lucide-react'

export default function Widget_ExchangeRate({ data }) {
  const fx = data?.exchange_rate
  if (!fx) return null

  return (
    <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-6">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-green-400 to-teal-500 flex items-center justify-center">
          <DollarSign size={16} className="text-white" />
        </div>
        <div>
          <div className="font-bold text-slate-700 text-sm">美金匯率</div>
          <div className="text-[10px] text-slate-400">台銀牌告 {fx.date}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-white/50 rounded-xl p-3 border border-white/60">
          <div className="text-[11px] text-slate-500 mb-1">現金買入</div>
          <div className="text-xl sm:text-2xl font-bold text-emerald-600 tabular-nums">
            {fx.usd_buy.toFixed(2)}
          </div>
        </div>
        <div className="bg-white/50 rounded-xl p-3 border border-white/60">
          <div className="text-[11px] text-slate-500 mb-1">現金賣出</div>
          <div className="text-xl sm:text-2xl font-bold text-red-500 tabular-nums">
            {fx.usd_sell.toFixed(2)}
          </div>
        </div>
      </div>
    </div>
  )
}
