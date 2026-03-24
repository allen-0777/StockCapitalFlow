function Sparkline({ values, isBull }) {
  if (!values || values.length < 2) return null
  const w = 100, h = 28, pad = 2
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const pts = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2)
    const y = h - pad - ((v - min) / range) * (h - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const color = isBull ? '#ef4444' : '#22c55e'
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline points={pts.join(' ')} fill="none" stroke={color}
        strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" opacity="0.7" />
      <circle cx={pts[pts.length - 1].split(',')[0]} cy={pts[pts.length - 1].split(',')[1]}
        r="2.5" fill={color} />
    </svg>
  )
}

function getTrend(history, pctKey) {
  if (!history || history.length < 2) return { delta: null, streak: null }
  const vals = history.map(h => h[pctKey]).filter(v => v != null)
  if (vals.length < 2) return { delta: null, streak: null }
  const delta = vals[vals.length - 1] - vals[vals.length - 2]
  const last = vals[vals.length - 1]
  const base = last >= 50 ? 'bull' : 'bear'
  let streak = 1
  for (let i = vals.length - 2; i >= 0; i--) {
    if ((vals[i] >= 50 ? 'bull' : 'bear') === base) streak++
    else break
  }
  return { delta, streak, base }
}

// 判斷土洋格局
function getConflictLabel(foreignBull, trustBull) {
  if (foreignBull == null || trustBull == null) return null
  const fBull = foreignBull >= 50
  const tBull = trustBull >= 50
  if (fBull && tBull)   return { text: '🚀 土洋合擊', color: 'text-red-600 bg-red-50' }
  if (!fBull && !tBull) return { text: '🐻 土洋同空', color: 'text-green-700 bg-green-50' }
  if (!fBull && tBull)  return { text: '🛡️ 外空投多', color: 'text-amber-600 bg-amber-50' }
  return                       { text: '⚡ 外多投空', color: 'text-purple-600 bg-purple-50' }
}

export default function Widget4_FuturesOI({ data }) {
  if (!data || !data.futures_oi) {
    return (
      <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 flex items-center justify-center h-28 sm:h-32">
        <p className="text-slate-400 text-sm">期貨OI 尚無資料，等待 17:15 排程</p>
      </div>
    )
  }

  const { tx_foreign_bull_pct, mtx_retail_bull_pct, trust_tx_bull_pct,
          trust_tx_long, trust_tx_short } = data.futures_oi
  const history = data.futures_oi_history ?? []
  const date = data.futures_oi_date ?? data.date
  const conflictLabel = getConflictLabel(tx_foreign_bull_pct, trust_tx_bull_pct)

  const items = [
    {
      label: '外資大台未平倉多空比',
      sublabel: '台指期 (TX)｜外資部位',
      pct: tx_foreign_bull_pct,
      histKey: 'tx_foreign_bull_pct',
    },
    {
      label: '外資小台未平倉多空比',
      sublabel: '小台指 (MTX)｜外資部位',
      pct: mtx_retail_bull_pct,
      histKey: 'mtx_retail_bull_pct',
    },
  ]

  return (
    <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-6">
      {/* 標題列 */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h2 className="text-lg font-bold text-slate-800">外資期貨雙指標動向</h2>
          <p className="text-xs text-slate-400 mt-0.5">{date} 盤後資料</p>
        </div>
        {/* 土洋格局標籤 */}
        {conflictLabel && (
          <span className={`text-xs font-semibold px-3 py-1 rounded-full ${conflictLabel.color}`}>
            {conflictLabel.text}
          </span>
        )}
      </div>

      {/* 外資大台 / 外資小台（主指標）*/}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4 mb-4">
        {items.map(({ label, sublabel, pct, histKey }) => {
          const isNull = pct == null
          const bullPct = isNull ? 50 : pct
          const isBull = bullPct >= 50
          const sparkVals = history.map(h => h[histKey]).filter(v => v != null)
          const { delta, streak, base } = getTrend(history, histKey)

          return (
            <div key={label} className="bg-white/40 rounded-2xl p-4">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <div className="text-sm font-semibold text-slate-700">{label}</div>
                  <div className="text-xs text-slate-400">{sublabel}</div>
                </div>
                <div className="text-right">
                  <div className={`text-2xl font-black tabular-nums leading-none ${isBull ? 'text-red-500' : 'text-green-500'}`}>
                    {isNull ? '—' : `${bullPct.toFixed(2)}%`}
                  </div>
                  {delta != null && (
                    <div className={`text-[11px] font-medium mt-0.5 tabular-nums ${delta >= 0 ? 'text-red-400' : 'text-green-500'}`}>
                      {delta >= 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(2)}%
                    </div>
                  )}
                </div>
              </div>
              <div className="relative h-2.5 w-full bg-slate-100 rounded-full overflow-hidden">
                <div className={`absolute left-0 top-0 h-full rounded-full transition-all duration-1000 ${isBull ? 'bg-gradient-to-r from-red-300 to-red-500' : 'bg-gradient-to-r from-green-300 to-green-500'}`}
                  style={{ width: `${bullPct}%` }} />
              </div>
              <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                <span className="text-red-400 font-medium">多 {bullPct.toFixed(1)}%</span>
                <span className="text-green-500 font-medium">空 {(100 - bullPct).toFixed(1)}%</span>
              </div>
              <div className="flex items-center justify-between mt-3 pt-2 border-t border-white/40">
                <div>
                  {streak != null && streak >= 2
                    ? <div className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${base === 'bull' ? 'bg-red-50 text-red-500' : 'bg-green-50 text-green-600'}`}>
                        連 {streak} 日{base === 'bull' ? '偏多' : '偏空'}
                      </div>
                    : <div className="text-[10px] text-slate-400">近 5 日趨勢</div>
                  }
                </div>
                <Sparkline values={sparkVals} isBull={isBull} />
              </div>
            </div>
          )
        })}
      </div>

      {/* 投信 TX OI（輔助指標 — 窄條）*/}
      {trust_tx_bull_pct != null && (
        <div className="bg-white/30 rounded-2xl px-4 py-3 border border-white/50">
          <div className="flex items-center justify-between mb-1.5">
            <div>
              <span className="text-xs font-semibold text-slate-600">投信大台未平倉多空比</span>
              <span className="text-[10px] text-slate-400 ml-2">台指期 (TX)｜投信部位</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-slate-400">
                多 {trust_tx_long?.toLocaleString()} ｜ 空 {trust_tx_short?.toLocaleString()} 口
              </span>
              <span className={`text-base font-black tabular-nums ${trust_tx_bull_pct >= 50 ? 'text-red-500' : 'text-green-500'}`}>
                {trust_tx_bull_pct.toFixed(2)}%
              </span>
            </div>
          </div>
          <div className="relative h-2 w-full bg-slate-100 rounded-full overflow-hidden">
            <div className={`absolute left-0 top-0 h-full rounded-full transition-all duration-1000 ${trust_tx_bull_pct >= 50 ? 'bg-gradient-to-r from-red-200 to-red-400' : 'bg-gradient-to-r from-green-200 to-green-400'}`}
              style={{ width: `${trust_tx_bull_pct}%` }} />
          </div>
          <div className="flex justify-between text-[10px] text-slate-400 mt-0.5">
            <span className="text-red-400">多 {trust_tx_bull_pct.toFixed(1)}%</span>
            <span className="text-green-500">空 {(100 - trust_tx_bull_pct).toFixed(1)}%</span>
          </div>
        </div>
      )}
    </div>
  )
}
