export default function Widget4_FuturesOI({ data }) {
  if (!data || !data.futures_oi) {
    return (
      <div className="md:col-span-2 lg:col-span-3 glass-card rounded-[2rem] p-6 flex items-center justify-center h-32">
        <p className="text-slate-400 text-sm">期貨OI 尚無資料，等待 17:15 排程</p>
      </div>
    )
  }

  const { tx_foreign_bull_pct, mtx_retail_bull_pct } = data.futures_oi
  const date = data.futures_oi_date ?? data.date

  const items = [
    {
      label: '外資大台未平倉多空比',
      sublabel: '台指期 (TX)｜外資部位',
      pct: tx_foreign_bull_pct,
    },
    {
      label: '外資小台未平倉多空比',
      sublabel: '小台指 (MTX)｜外資部位',
      pct: mtx_retail_bull_pct,
    },
  ]

  return (
    <div className="md:col-span-2 lg:col-span-3 glass-card rounded-[2rem] p-6">
      <div className="mb-5">
        <h2 className="text-lg font-bold text-slate-800">外資期貨雙指標動向</h2>
        <p className="text-xs text-slate-400 mt-0.5">{date} 盤後資料</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {items.map(({ label, sublabel, pct }) => {
          const isNull = pct == null
          const bullPct = isNull ? 50 : pct
          const isBull = bullPct >= 50

          return (
            <div key={label} className="bg-white/40 rounded-2xl p-4">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <div className="text-sm font-semibold text-slate-700">{label}</div>
                  <div className="text-xs text-slate-400">{sublabel}</div>
                </div>
                <div className={`text-2xl font-black tabular-nums ${isBull ? 'text-red-500' : 'text-green-500'}`}>
                  {isNull ? '—' : `${bullPct.toFixed(2)}%`}
                </div>
              </div>

              <div className="relative h-3 w-full bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="absolute left-0 top-0 h-full bg-gradient-to-r from-red-300 to-red-500 rounded-full transition-all duration-1000"
                  style={{ width: `${bullPct}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                <span className="text-red-400 font-medium">多 {bullPct.toFixed(1)}%</span>
                <span className="text-green-500 font-medium">空 {(100 - bullPct).toFixed(1)}%</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
