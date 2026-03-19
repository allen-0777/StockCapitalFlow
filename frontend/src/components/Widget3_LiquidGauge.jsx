export default function Widget3_LiquidGauge({ data }) {
  if (!data) {
    return (
      <div className="glass-card rounded-[2rem] p-6 flex items-center justify-center">
        <p className="text-slate-400 text-sm">載入中...</p>
      </div>
    )
  }

  // long_yi: 融資增減（億元, float）；short_zhang: 融券增減（張, int）
  const { long_yi: longYi, short_zhang: shortZhang } = data.margin

  // 多空水位計算：各自 normalize 後合成
  // 融資億元：±150 億為極端值；融券張：±15000 張為極端值
  const longNorm  = Math.max(-1, Math.min(1, longYi   / 150))
  const shortNorm = Math.max(-1, Math.min(1, shortZhang / 15000))
  const sentiment = longNorm - shortNorm  // [-2, +2]
  const bullPct = Math.min(100, Math.max(0, Math.round(50 + sentiment * 25)))
  const isBull = bullPct >= 50

  // 標籤
  let label = '中性盤整'
  if (longYi > 0 && shortZhang < 0) label = '強勢多頭'
  else if (longYi > 0 && shortZhang > 0) label = '多空拉鋸'
  else if (longYi < 0 && shortZhang < 0) label = '空方回補'
  else if (longYi < 0 && shortZhang > 0) label = '偏空格局'

  // 格式化：融資用億元，融券用萬張
  const fmtYi = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}億`
  const fmtZhang = (v) => {
    const wan = v / 10000
    return `${v >= 0 ? '+' : ''}${wan.toFixed(1)}萬張`
  }

  return (
    <div className="glass-card rounded-[2rem] p-6 flex flex-col items-center justify-center relative">
      <h2 className="text-lg font-bold text-slate-800 absolute top-6 left-6">大盤主力水位</h2>
      <p className="text-xs text-slate-400 absolute top-11 left-6">
        {data.margin_date ?? data.date} 融資/融券增減
      </p>

      {/* 液態球 */}
      <div className="relative w-48 h-48 mt-8 rounded-full border-4 border-white/50 bg-white/20 shadow-[inset_0_-10px_30px_rgba(59,130,246,0.2)] overflow-hidden flex items-center justify-center">
        <div
          className="absolute bottom-0 w-[200%] h-[200%] bg-gradient-to-t from-blue-400/80 to-cyan-300/80 rounded-[40%]"
          style={{
            animation: 'spin 6s linear infinite',
            transform: `translateY(${100 - bullPct}%)`,
          }}
        />
        <div
          className="absolute bottom-0 w-[200%] h-[200%] bg-gradient-to-t from-blue-500/50 to-cyan-400/50 rounded-[45%]"
          style={{
            animation: 'spin 8s linear infinite reverse',
            transform: `translateY(${100 - bullPct + 3}%)`,
          }}
        />
        <div className="relative z-10 text-center drop-shadow-md">
          <div className="text-4xl font-black text-white tabular-nums">
            {bullPct}<span className="text-xl">%</span>
          </div>
          <div className="text-xs text-white/90 font-medium mt-1">{label}</div>
        </div>
      </div>

      {/* 融資/融券增減 */}
      <div className="mt-8 grid grid-cols-2 gap-4 w-full text-center">
        <div className="bg-white/40 rounded-2xl py-3">
          <div className="text-xs text-slate-500 mb-1">融資增減</div>
          <div className={`font-bold text-sm ${longYi >= 0 ? 'text-red-500' : 'text-green-500'}`}>
            {fmtYi(longYi)}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            {longYi >= 0 ? '多頭加碼' : '多頭退場'}
          </div>
        </div>
        <div className="bg-white/40 rounded-2xl py-3">
          <div className="text-xs text-slate-500 mb-1">融券增減</div>
          <div className={`font-bold text-sm ${shortZhang <= 0 ? 'text-red-500' : 'text-green-500'}`}>
            {fmtZhang(shortZhang)}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            {shortZhang <= 0 ? '空方回補' : '空頭加碼'}
          </div>
        </div>
      </div>
    </div>
  )
}
