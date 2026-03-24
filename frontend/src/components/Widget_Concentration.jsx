import { useState, useCallback, useMemo } from 'react'
import { Search, Loader2, Users } from 'lucide-react'

// FinMind 回傳單位是「股」，除以 1000 才是「張」
function toZhang(shares) { return Math.round(shares / 1000) }

function fmtZhang(zhang) {
  const sign = zhang >= 0 ? '+' : ''
  return sign + zhang.toLocaleString()
}

function Cell({ val }) {
  const z = toZhang(val)
  const color = z > 0 ? 'text-red-500' : z < 0 ? 'text-emerald-500' : 'text-slate-400'
  return <td className={`text-right tabular-nums text-sm py-2 px-2 whitespace-nowrap ${color}`}>{fmtZhang(z)}</td>
}

function TotalCell({ row }) {
  const z = toZhang(row.foreign + row.trust + row.dealer)
  const color = z > 0 ? 'text-red-600 font-bold' : z < 0 ? 'text-emerald-600 font-bold' : 'text-slate-400'
  return <td className={`text-right tabular-nums text-sm py-2 px-2 whitespace-nowrap ${color}`}>{fmtZhang(z)}</td>
}

function SumRow({ rows }) {
  const f = rows.reduce((a, r) => a + r.foreign, 0)
  const t = rows.reduce((a, r) => a + r.trust, 0)
  const d = rows.reduce((a, r) => a + r.dealer, 0)
  const total = f + t + d
  const fz = toZhang(f), tz = toZhang(t), dz = toZhang(d), totZ = toZhang(total)
  const col = v => v > 0 ? 'text-red-500' : v < 0 ? 'text-emerald-500' : 'text-slate-400'
  return (
    <tr className="border-t-2 border-slate-200 bg-slate-50/60">
      <td className="text-xs text-slate-500 font-semibold py-2 px-2 whitespace-nowrap">近10日合計</td>
      <td className={`text-right tabular-nums text-sm py-2 px-2 font-semibold whitespace-nowrap ${col(fz)}`}>{fmtZhang(fz)}</td>
      <td className={`text-right tabular-nums text-sm py-2 px-2 font-semibold whitespace-nowrap ${col(tz)}`}>{fmtZhang(tz)}</td>
      <td className={`text-right tabular-nums text-sm py-2 px-2 font-semibold whitespace-nowrap ${col(dz)}`}>{fmtZhang(dz)}</td>
      <td className={`text-right tabular-nums text-sm py-2 px-2 font-bold whitespace-nowrap ${col(totZ)}`}>{fmtZhang(totZ)}</td>
    </tr>
  )
}

function ConsecutiveDays(rows, field) {
  if (!rows.length) return 0
  const last = rows[rows.length - 1][field]
  const isBuy = last > 0
  let count = 0
  for (let i = rows.length - 1; i >= 0; i--) {
    if ((isBuy && rows[i][field] > 0) || (!isBuy && rows[i][field] < 0)) count++
    else break
  }
  return isBuy ? count : -count
}

function ConsecutiveTag({ label, rows, keyName, color }) {
  const n = ConsecutiveDays(rows, keyName)
  const isBuy = n > 0
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-500 text-xs" style={{ color }}>{label}</span>
      <span className={`font-bold ${isBuy ? 'text-red-500' : 'text-emerald-500'}`}>
        {isBuy ? `連買 ${n} 日` : `連賣 ${Math.abs(n)} 日`}
      </span>
    </div>
  )
}

function ShareholdingChart({ data }) {
  if (!data || data.length < 2) return (
    <div className="text-slate-400 text-xs text-center py-6">外資持股資料不足</div>
  )
  const values = data.map(d => d.foreign_ratio)
  const min = Math.min(...values), max = Math.max(...values)
  const range = max - min || 0.01
  const W = 200, H = 60
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * W
    const y = H - ((d.foreign_ratio - min) / range) * (H - 10) - 5
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const latest = values[values.length - 1]
  const prev   = values[values.length - 2]
  const diff   = (latest - prev).toFixed(2)
  const isUp   = latest >= prev
  const color  = isUp ? '#3b82f6' : '#10b981'
  const lastPt = pts.split(' ').pop().split(',')

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-end gap-2">
        <span className="text-3xl font-bold text-slate-700">{latest.toFixed(2)}%</span>
        <span className={`text-sm font-semibold mb-1 ${isUp ? 'text-red-500' : 'text-emerald-500'}`}>
          {isUp ? '▲' : '▼'} {Math.abs(diff)}%
        </span>
        <span className="text-[10px] text-slate-400 mb-1">較昨日</span>
        <span className="text-xs text-slate-400 mb-1 ml-auto">{data[data.length-1].date}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 60 }}>
        <defs>
          <linearGradient id="fg-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.2" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={`0,${H} ${pts} ${W},${H}`} fill="url(#fg-grad)" />
        <polyline points={pts} fill="none" stroke={color} strokeWidth="1.8"
          strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={lastPt[0]} cy={lastPt[1]} r="3" fill={color} />
      </svg>
      <div className="flex justify-between text-xs text-slate-500">
        <span>近期最低 <span className="font-bold text-emerald-500">{Math.min(...values).toFixed(2)}%</span></span>
        <span>近期最高 <span className="font-bold text-red-500">{Math.max(...values).toFixed(2)}%</span></span>
      </div>
    </div>
  )
}

export default function Widget_Concentration() {
  const [inputVal, setInputVal]   = useState('')
  const [stockLabel, setStockLabel] = useState('')  // "2408 南亞科"
  const [suggestions, setSuggestions] = useState([])
  const [data, setData]           = useState(null)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')

  // 輸入時若含中文，即時搜尋建議
  const handleInput = useCallback(async (val) => {
    setInputVal(val)
    if (!val.trim() || /^\d+$/.test(val)) { setSuggestions([]); return }
    try {
      const res = await fetch(`/api/v1/stocks/search?q=${encodeURIComponent(val.trim())}`)
      if (res.ok) setSuggestions(await res.json())
    } catch { setSuggestions([]) }
  }, [])

  const doSearch = useCallback(async (code, label) => {
    if (!code) return
    setSuggestions([])
    setStockLabel(label)
    setLoading(true); setError(''); setData(null)
    try {
      const res = await fetch(`/api/v1/stocks/${code}/concentration?days=60`)
      if (!res.ok) throw new Error()
      const json = await res.json()
      if (!json.institutional?.length) { setError('查無此股票資料'); return }
      setData(json)
    } catch {
      setError('查詢失敗，請確認股號')
    } finally {
      setLoading(false)
    }
  }, [])

  const handleSearch = useCallback(async () => {
    const val = inputVal.trim()
    if (!val) return
    // 純數字直接查
    if (/^\d+$/.test(val)) { doSearch(val, val); return }
    // 中文：先查一次 search 取第一筆
    try {
      const res = await fetch(`/api/v1/stocks/search?q=${encodeURIComponent(val)}`)
      if (res.ok) {
        const hits = await res.json()
        if (hits.length > 0) doSearch(hits[0].code, `${hits[0].code} ${hits[0].name}`)
        else setError('找不到符合的股票')
      }
    } catch { setError('搜尋失敗') }
  }, [inputVal, doSearch])

  // 近 10 個交易日仍取 API 陣列末段（日期升序），表格改為日期降序顯示（最新在上）
  const recent10 = useMemo(() => {
    if (!data?.institutional?.length) return []
    return [...data.institutional.slice(-10)].reverse()
  }, [data])

  return (
    <div className="lg:col-span-3 glass-card rounded-[2rem] p-6 flex flex-col gap-5">

      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-2xl bg-gradient-to-br from-violet-400 to-purple-500 flex items-center justify-center shrink-0">
          <Users size={18} className="text-white" />
        </div>
        <div>
          <div className="font-bold text-slate-700 text-base">三大法人動向與持股</div>
          <div className="text-xs text-slate-400">三大法人買賣超 · 外資持股比例</div>
        </div>
        <div className="ml-auto relative flex items-center gap-2 bg-white/70 border border-white/80 rounded-2xl px-3 py-1.5 shadow-sm">
          <Search size={14} className="text-slate-400 shrink-0" />
          <input
            className="bg-transparent text-sm text-slate-700 placeholder-slate-300 outline-none w-28"
            placeholder="股號或名稱"
            value={inputVal}
            onChange={e => handleInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
          <button onClick={handleSearch}
            className="text-xs text-blue-500 font-medium hover:text-blue-700 transition-colors">
            查詢
          </button>
          {suggestions.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg z-50 overflow-hidden">
              {suggestions.map(s => (
                <button
                  key={s.code}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50 flex justify-between"
                  onClick={() => { setInputVal(`${s.code} ${s.name}`); doSearch(s.code, `${s.code} ${s.name}`); setSuggestions([]) }}
                >
                  <span className="text-slate-700 font-medium">{s.code}</span>
                  <span className="text-slate-400">{s.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16 gap-2 text-slate-400">
          <Loader2 size={18} className="animate-spin" /><span className="text-sm">載入中…</span>
        </div>
      )}
      {error && !loading && (
        <div className="flex items-center justify-center py-16 text-slate-400 text-sm">{error}</div>
      )}
      {!data && !loading && !error && (
        <div className="flex items-center justify-center py-16 text-slate-300 text-sm">輸入股號查詢籌碼資料</div>
      )}

      {data && !loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">

          {/* 左：法人動向表格 */}
          <div className="bg-white/50 rounded-2xl p-4 flex flex-col gap-3">
            <div className="text-sm font-semibold text-slate-600">
              三大法人買賣超
              <span className="ml-2 text-xs font-normal text-slate-400">單位：張</span>
            </div>

            <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
              <table className="w-full min-w-[32rem] table-fixed border-collapse">
                <colgroup>
                  <col style={{ width: '4.5rem' }} />
                  <col />
                  <col />
                  <col />
                  <col />
                </colgroup>
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left text-xs text-slate-400 font-medium py-1.5 px-2 whitespace-nowrap w-[4.5rem] min-w-[4.5rem]">日期</th>
                    <th className="text-right text-xs font-medium py-1.5 px-2 whitespace-nowrap" style={{ color: '#3b82f6' }}>外資</th>
                    <th className="text-right text-xs font-medium py-1.5 px-2 whitespace-nowrap" style={{ color: '#a855f7' }}>投信</th>
                    <th className="text-right text-xs font-medium py-1.5 px-2 whitespace-nowrap" style={{ color: '#f97316' }}>自營</th>
                    <th className="text-right text-xs text-slate-400 font-medium py-1.5 px-2 whitespace-nowrap">合計</th>
                  </tr>
                </thead>
                <tbody>
                  {recent10.map((row, i) => (
                    <tr key={row.date} className={i % 2 === 0 ? 'bg-transparent' : 'bg-slate-50/40'}>
                      <td className="text-xs text-slate-500 py-2 px-2 tabular-nums whitespace-nowrap align-top">
                        {row.date.slice(5)}
                      </td>
                      <Cell val={row.foreign} />
                      <Cell val={row.trust} />
                      <Cell val={row.dealer} />
                      <TotalCell row={row} />
                    </tr>
                  ))}
                  <SumRow rows={recent10} />
                </tbody>
              </table>
            </div>

            {/* 連買連賣天數 */}
            <div className="mt-1 flex flex-col gap-2 pt-3 border-t border-white/60">
              <ConsecutiveTag label="外資" rows={data.institutional} keyName="foreign" color="#3b82f6" />
              <ConsecutiveTag label="投信" rows={data.institutional} keyName="trust"    color="#a855f7" />
              <ConsecutiveTag label="自營" rows={data.institutional} keyName="dealer"  color="#f97316" />
            </div>
          </div>

          {/* 右：外資持股比例 */}
          <div className="bg-white/50 rounded-2xl p-4 flex flex-col gap-3">
            <div className="text-sm font-semibold text-slate-600">外資持股比例</div>
            <ShareholdingChart data={data.shareholding} />
            <div className="mt-auto p-3 bg-slate-50/80 rounded-xl text-xs text-slate-400 leading-relaxed">
              外資持股比例上升 = 外資長期持續買進累積。
              搭配左側「連買天數」判斷是短期反彈還是主力吸籌。
            </div>
          </div>

        </div>
      )}
    </div>
  )
}
