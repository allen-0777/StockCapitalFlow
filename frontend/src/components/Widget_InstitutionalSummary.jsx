import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

function StatRow({ label, value, unit = '億', decimals = 2 }) {
  if (value == null) return null
  const isBuy = value > 0
  const isFlat = value === 0
  const fmt = Math.abs(value).toFixed(decimals)
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-white/40 last:border-0">
      <span className="text-sm text-slate-500">{label}</span>
      <span className={`font-bold text-sm flex items-center gap-1 tabular-nums
        ${isFlat ? 'text-slate-400' : isBuy ? 'text-red-500' : 'text-green-500'}`}>
        {isFlat ? <Minus size={12} /> : isBuy ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
        {isBuy ? `+${fmt}` : `-${fmt}`}
        <span className="text-xs font-normal text-slate-400 ml-0.5">{unit}</span>
      </span>
    </div>
  )
}

export default function Widget_InstitutionalSummary({ marketData }) {
  const inst = marketData?.institutional
  const margin = marketData?.margin
  const date = marketData?.date

  return (
    <div className="flex flex-col gap-5">

      {/* 大盤三大法人摘要 */}
      <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-5 flex flex-col">
        <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-3">今日大盤法人</div>
        {inst ? (
          <>
            <StatRow label="外資及陸資" value={inst.foreign} unit="億" />
            <StatRow label="投信" value={inst.trust} unit="億" />
            <StatRow label="自營商" value={inst.dealer} unit="億" />
            <div className="mt-3 pt-3 border-t border-white/40 flex justify-between items-center">
              <span className="text-sm text-slate-500 font-medium">三大合計</span>
              <span className={`text-lg font-black tabular-nums ${inst.total >= 0 ? 'text-red-500' : 'text-green-500'}`}>
                {inst.total >= 0 ? `+${inst.total}` : inst.total}
                <span className="text-xs font-normal text-slate-400 ml-1">億</span>
              </span>
            </div>
            <div className="text-xs text-slate-400 mt-2 text-right">{date}</div>
          </>
        ) : (
          <p className="text-slate-400 text-sm py-4 text-center">等待資料...</p>
        )}
      </div>

      {/* 融資融券 */}
      <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-5 flex flex-col">
        <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-3">信用交易</div>
        {margin ? (
          <>
            <StatRow label="融資增減" value={margin.long_yi} unit="億" decimals={2} />
            <StatRow label="融券增減" value={margin.short_zhang} unit="張" decimals={0} />
          </>
        ) : (
          <p className="text-slate-400 text-sm py-4 text-center">等待資料...</p>
        )}
      </div>

    </div>
  )
}
