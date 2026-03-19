import { useEffect, useState } from 'react'

function PcRatioBar({ value }) {
  // P/C Ratio 通常範圍 60~160，中軸 100
  const min = 60, max = 160
  const clamped = Math.min(max, Math.max(min, value ?? 100))
  const pct = ((clamped - min) / (max - min)) * 100

  let color, label, labelColor
  if (value >= 110) {
    color = 'bg-gradient-to-r from-red-300 to-red-500'
    label = '偏多'; labelColor = 'text-red-500'
  } else if (value <= 90) {
    color = 'bg-gradient-to-r from-green-300 to-green-500'
    label = '偏空'; labelColor = 'text-green-500'
  } else {
    color = 'bg-gradient-to-r from-amber-300 to-amber-400'
    label = '中性'; labelColor = 'text-amber-500'
  }

  return (
    <div>
      <div className="flex justify-between items-end mb-1.5">
        <div>
          <span className="text-sm font-semibold text-slate-700">P/C Ratio 未平倉比</span>
          <span className="text-[10px] text-slate-400 ml-2">Put÷Call OI</span>
        </div>
        <div className="text-right">
          <span className={`text-2xl font-black tabular-nums leading-none ${labelColor}`}>
            {value != null ? `${value.toFixed(1)}%` : '—'}
          </span>
          {value != null && (
            <span className={`text-[11px] font-semibold ml-1.5 ${labelColor}`}>{label}</span>
          )}
        </div>
      </div>
      <div className="relative h-2.5 w-full bg-slate-100 rounded-full overflow-hidden">
        <div className={`absolute left-0 top-0 h-full rounded-full transition-all duration-1000 ${color}`}
          style={{ width: `${pct}%` }} />
        {/* 中軸 100% 標記 */}
        <div className="absolute top-0 h-full w-px bg-slate-400/60" style={{ left: `${((100 - min) / (max - min)) * 100}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-slate-400 mt-1">
        <span>空方 {min}%</span>
        <span className="text-slate-500">中性 100%</span>
        <span>多方 {max}%</span>
      </div>
    </div>
  )
}

function NetBar({ label, value, max }) {
  const isBull = (value ?? 0) >= 0
  const pct = Math.min(100, Math.abs(value ?? 0) / max * 50) // 50% = max (各佔一半)
  const color = isBull
    ? 'bg-gradient-to-r from-red-300 to-red-500'
    : 'bg-gradient-to-l from-green-300 to-green-500'

  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-500">{label}</span>
        <span className={`text-sm font-bold tabular-nums ${isBull ? 'text-red-500' : 'text-green-500'}`}>
          {value != null ? `${isBull ? '+' : ''}${value.toFixed(1)} 億` : '—'}
        </span>
      </div>
      <div className="relative h-2 w-full bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`absolute top-0 h-full rounded-full transition-all duration-1000 ${color}`}
          style={{
            width: `${pct}%`,
            left: isBull ? '50%' : `${50 - pct}%`,
          }}
        />
        <div className="absolute top-0 h-full w-px bg-slate-300" style={{ left: '50%' }} />
      </div>
    </div>
  )
}

export default function Widget5_Options() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/market/options')
      .then(r => r.ok ? r.json() : null)
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="md:col-span-2 lg:col-span-3 glass-card rounded-[2rem] p-6 flex items-center justify-center h-32">
        <p className="text-slate-400 text-sm">載入選擇權數據中…</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="md:col-span-2 lg:col-span-3 glass-card rounded-[2rem] p-6 flex items-center justify-center h-32">
        <p className="text-slate-400 text-sm">選擇權資料尚無，等待 17:15 排程</p>
      </div>
    )
  }

  const {
    date, pc_ratio,
    call_max_strike, put_max_strike,
    call_total_oi, put_total_oi,
    foreign_call_net_yi, foreign_put_net_yi,
  } = data

  // 最大淨額絕對值，用於 NetBar 比例基準
  const maxNet = Math.max(
    Math.abs(foreign_call_net_yi ?? 0),
    Math.abs(foreign_put_net_yi ?? 0),
    10 // 最小 10 億，避免除零
  )

  return (
    <div className="md:col-span-2 lg:col-span-3 glass-card rounded-[2rem] p-6">
      {/* 標題 */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h2 className="text-lg font-bold text-slate-800">選擇權籌碼觀測</h2>
          <p className="text-xs text-slate-400 mt-0.5">{date} 盤後資料</p>
        </div>
        {call_max_strike != null && put_max_strike != null && (
          <div className="text-right">
            <div className="text-[10px] text-slate-400 mb-0.5">近月壓力區間</div>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-bold text-red-500">天 {call_max_strike?.toLocaleString()}</span>
              <span className="text-slate-300">|</span>
              <span className="text-[11px] font-bold text-green-600">地 {put_max_strike?.toLocaleString()}</span>
            </div>
          </div>
        )}
      </div>

      {/* P/C Ratio */}
      <div className="mb-5">
        <PcRatioBar value={pc_ratio} />
      </div>

      {/* 外資選擇權淨部位 */}
      <div className="bg-white/40 rounded-2xl p-4">
        <div className="text-xs font-semibold text-slate-600 mb-3">
          外資選擇權淨部位
          <span className="text-[10px] text-slate-400 font-normal ml-2">多方淨額 (億元)，正=多方偏多</span>
        </div>
        <div className="space-y-3">
          <NetBar label="Call 淨部位（買方看漲）" value={foreign_call_net_yi} max={maxNet} />
          <NetBar label="Put 淨部位（買方看跌）" value={foreign_put_net_yi} max={maxNet} />
        </div>
        {/* OI 摘要 */}
        {(call_total_oi > 0 || put_total_oi > 0) && (
          <div className="mt-3 pt-3 border-t border-white/40 flex justify-between text-[10px] text-slate-400">
            <span>近月 Call OI：{call_total_oi?.toLocaleString()} 口</span>
            <span>近月 Put OI：{put_total_oi?.toLocaleString()} 口</span>
          </div>
        )}
      </div>

      {/* 天地板說明 */}
      {call_max_strike != null && put_max_strike != null && (
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="bg-red-50/60 rounded-xl px-4 py-2.5 border border-red-100">
            <div className="text-[10px] text-red-400 font-medium mb-0.5">天花板壓力（Call 最大OI）</div>
            <div className="text-xl font-black text-red-500 tabular-nums">{call_max_strike?.toLocaleString()}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">市場預期近月上方壓力</div>
          </div>
          <div className="bg-green-50/60 rounded-xl px-4 py-2.5 border border-green-100">
            <div className="text-[10px] text-green-600 font-medium mb-0.5">地板支撐（Put 最大OI）</div>
            <div className="text-xl font-black text-green-600 tabular-nums">{put_max_strike?.toLocaleString()}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">市場預期近月下方支撐</div>
          </div>
        </div>
      )}
    </div>
  )
}
