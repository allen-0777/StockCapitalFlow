import { BarChart3 } from 'lucide-react'

export default function Widget_Volume({ data }) {
  const history = data?.volume_history
  const latest = data?.volume_yi

  if (!history?.length) return null

  const max = Math.max(...history.map(d => d.volume_yi))

  return (
    <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-6">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center">
            <BarChart3 size={16} className="text-white" />
          </div>
          <div>
            <div className="font-bold text-slate-700 text-sm">大盤成交量</div>
            <div className="text-[10px] text-slate-400">近 {history.length} 個交易日</div>
          </div>
        </div>
        {latest != null && (
          <div className="text-right">
            <div className="text-xl sm:text-2xl font-black text-slate-700 tabular-nums">
              {latest.toLocaleString()}
              <span className="text-xs font-normal text-slate-400 ml-1">億</span>
            </div>
          </div>
        )}
      </div>

      {/* Bar chart */}
      <div className="flex items-end gap-[3px] sm:gap-1 h-20 sm:h-28">
        {history.map((d, i) => {
          const pct = max > 0 ? (d.volume_yi / max) * 100 : 0
          const isLast = i === history.length - 1
          const isHigh = d.volume_yi > max * 0.8
          return (
            <div
              key={d.date}
              className="flex-1 group relative"
              style={{ height: '100%', display: 'flex', alignItems: 'flex-end' }}
            >
              <div
                className={`w-full rounded-t-sm transition-all ${
                  isLast ? 'bg-orange-500' : isHigh ? 'bg-amber-400' : 'bg-slate-300'
                }`}
                style={{ height: `${Math.max(pct, 2)}%` }}
              />
              <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block
                bg-slate-800 text-white text-[10px] px-1.5 py-0.5 rounded whitespace-nowrap z-10">
                {d.date.slice(5)} {d.volume_yi}億
              </div>
            </div>
          )
        })}
      </div>

      <div className="flex justify-between mt-1 text-[10px] text-slate-400">
        <span>{history[0]?.date.slice(5)}</span>
        <span>{history[history.length - 1]?.date.slice(5)}</span>
      </div>
    </div>
  )
}
