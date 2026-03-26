import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from 'recharts'
import { TrendingUp, AlertCircle, RefreshCw } from 'lucide-react'

const LINE_COLORS = [
  '#2563eb',
  '#059669',
  '#d97706',
  '#dc2626',
  '#7c3aed',
  '#db2777',
  '#0d9488',
  '#4f46e5',
]

function mergeChartRows(pack) {
  if (!pack?.benchmark?.length) return []
  const byDate = new Map()
  for (const p of pack.benchmark) {
    byDate.set(p.date, { date: p.date, bench: p.norm })
  }
  const seriesEntries = Object.entries(pack.series || {})
  for (const [sid, meta] of seriesEntries) {
    for (const p of meta.points || []) {
      const row = byDate.get(p.date) || { date: p.date }
      row[sid] = p.norm
      byDate.set(p.date, row)
    }
  }
  return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date))
}

function rankHeatColor(rank, maxRank) {
  if (rank == null || maxRank == null || maxRank < 1) return 'bg-slate-200'
  const t = (rank - 1) / Math.max(maxRank - 1, 1)
  if (t <= 0.15) return 'bg-emerald-500'
  if (t <= 0.35) return 'bg-teal-400'
  if (t <= 0.55) return 'bg-amber-300'
  if (t <= 0.75) return 'bg-orange-400'
  return 'bg-rose-400'
}

export default function Widget_IndustryRotation() {
  const [rotation, setRotation] = useState(null)
  const [pack, setPack] = useState(null)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(true)
  const [hidden, setHidden] = useState(() => new Set())

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const [rRes, cRes] = await Promise.all([
        fetch('/api/v1/market/rotation?lookback=120'),
        fetch('/api/v1/industries/chart-pack?days=160'),
      ])
      if (rRes.ok) setRotation(await rRes.json())
      else setRotation({ industries: [], note: `輪動 API ${rRes.status}` })

      if (cRes.ok) setPack(await cRes.json())
      else setPack(null)
    } catch (e) {
      setErr(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const chartRows = useMemo(() => mergeChartRows(pack || {}), [pack])
  const seriesKeys = useMemo(
    () => Object.keys(pack?.series || {}),
    [pack]
  )

  const maxRank = useMemo(() => {
    const inds = rotation?.industries || []
    const rs = inds.map((i) => i.rank).filter((x) => x != null)
    return rs.length ? Math.max(...rs) : 0
  }, [rotation])

  const barData = useMemo(() => {
    const inds = [...(rotation?.industries || [])]
    return inds
      .filter((i) => i.rank != null)
      .sort((a, b) => a.rank - b.rank)
      .map((i) => ({
        name: i.name.replace(/（\d+）$/, '').slice(0, 8),
        fullName: i.name,
        rank: i.rank,
        rs: i.rs_vs_taiex_pct ?? 0,
        signal: i.rotation_signal,
      }))
  }, [rotation])

  const toggleLine = (key) => {
    setHidden((prev) => {
      const n = new Set(prev)
      if (n.has(key)) n.delete(key)
      else n.add(key)
      return n
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="text-blue-600" size={22} />
          <div>
            <h2 className="text-lg font-semibold text-slate-800">產業輪動與相對強度</h2>
            <p className="text-xs text-slate-500">
              加權報酬指數對照各產業代表股（proxy）；RS = 產業日報酬 − 大盤日報酬。訊號為規則式參考，非投資建議。
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-medium bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          重新整理
        </button>
      </div>

      {err && (
        <div className="flex items-center gap-2 text-rose-600 text-sm glass-card p-3 rounded-2xl">
          <AlertCircle size={18} />
          {err}
        </div>
      )}

      {rotation?.note && (
        <div className="text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-2xl px-4 py-3">
          {rotation.note}
        </div>
      )}

      {pack?.note && !pack?.benchmark?.length && (
        <div className="text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-2xl px-4 py-3">
          {pack.note}
        </div>
      )}

      {/* 排名熱力條 */}
      {(rotation?.industries || []).length > 0 && (
        <div className="glass-card rounded-3xl p-4 sm:p-5 space-y-3">
          <div className="flex justify-between items-baseline">
            <h3 className="text-sm font-semibold text-slate-700">近五日平均排名熱力</h3>
            <span className="text-xs text-slate-400">
              資料日 {rotation.as_of ?? '—'} · 左強右弱
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {[...(rotation.industries || [])]
              .sort((a, b) => (a.avg_rank_5d ?? 99) - (b.avg_rank_5d ?? 99))
              .map((row) => (
                <div
                  key={row.series_id}
                  className="flex flex-col gap-1 min-w-[72px]"
                  title={`${row.name}\n5日均名次 ${row.avg_rank_5d ?? '—'}`}
                >
                  <div
                    className={`h-2 rounded-full ${rankHeatColor(
                      row.avg_rank_5d != null ? Math.round(row.avg_rank_5d) : row.rank,
                      maxRank || 8
                    )}`}
                  />
                  <span className="text-[10px] text-slate-500 leading-tight line-clamp-2">
                    {row.name.replace(/（\d+）$/, '').slice(0, 6)}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* RS 排名長條 */}
      {barData.length > 0 && (
        <div className="glass-card rounded-3xl p-4 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">當日 RS 排名（對大盤超額報酬 %）</h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barData} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" width={56} tick={{ fontSize: 10 }} />
                <Tooltip
                  formatter={(v) => [`${v}%`, 'RS']}
                  labelFormatter={(_, p) => p?.[0]?.payload?.fullName ?? ''}
                />
                <Bar dataKey="rs" radius={[0, 6, 6, 0]}>
                  {barData.map((e) => (
                    <Cell key={e.fullName} fill={e.signal ? '#2563eb' : '#94a3b8'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* 走勢：正規化指數 */}
      {chartRows.length > 0 && (
        <div className="glass-card rounded-3xl p-4 sm:p-5 space-y-3">
          <h3 className="text-sm font-semibold text-slate-700">走勢對照（視窗首日 = 100）</h3>
          <p className="text-xs text-slate-500">點標籤可隱藏／顯示線條。灰線：加權報酬指數。</p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => toggleLine('bench')}
              className={`text-xs px-2 py-1 rounded-lg border ${
                hidden.has('bench') ? 'opacity-40' : ''
              } border-slate-200 bg-slate-100`}
            >
              加權報酬
            </button>
            {seriesKeys.map((sid, i) => (
              <button
                key={sid}
                type="button"
                onClick={() => toggleLine(sid)}
                className={`text-xs px-2 py-1 rounded-lg border ${
                  hidden.has(sid) ? 'opacity-40' : ''
                }`}
                style={{ borderColor: LINE_COLORS[i % LINE_COLORS.length] }}
              >
                {(pack.series[sid].label || sid).slice(0, 10)}
              </button>
            ))}
          </div>
          <div className="h-80 w-full min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartRows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={28} />
                <YAxis tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {!hidden.has('bench') && (
                  <Line type="monotone" dataKey="bench" name="加權報酬" stroke="#64748b" dot={false} strokeWidth={2} />
                )}
                {seriesKeys.map((sid, i) =>
                  hidden.has(sid) ? null : (
                    <Line
                      key={sid}
                      type="monotone"
                      dataKey={sid}
                      name={(pack.series[sid].label || sid).slice(0, 14)}
                      stroke={LINE_COLORS[i % LINE_COLORS.length]}
                      dot={false}
                      strokeWidth={1.5}
                    />
                  )
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* 明細表 */}
      {(rotation?.industries || []).length > 0 && (
        <div className="glass-card rounded-3xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100">
            <h3 className="text-sm font-semibold text-slate-700">輪動訊號明細</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                  <th className="px-4 py-2 font-medium">名次</th>
                  <th className="px-4 py-2 font-medium">產業（proxy）</th>
                  <th className="px-4 py-2 font-medium">RS%</th>
                  <th className="px-4 py-2 font-medium">5日均名次</th>
                  <th className="px-4 py-2 font-medium">訊號</th>
                </tr>
              </thead>
              <tbody>
                {rotation.industries.map((row) => (
                  <tr key={row.series_id} className="border-b border-slate-50 hover:bg-slate-50/80">
                    <td className="px-4 py-2 font-mono">{row.rank ?? '—'}</td>
                    <td className="px-4 py-2 text-slate-800">{row.name}</td>
                    <td className="px-4 py-2 font-mono text-slate-600">
                      {row.rs_vs_taiex_pct != null ? row.rs_vs_taiex_pct : '—'}
                    </td>
                    <td className="px-4 py-2 font-mono">{row.avg_rank_5d ?? '—'}</td>
                    <td className="px-4 py-2">
                      {row.rotation_signal ? (
                        <span className="text-xs font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded-lg">
                          {(row.signal_reasons || []).join(' · ') || '觸發'}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && !(rotation?.industries || []).length && !rotation?.note && (
        <p className="text-sm text-slate-500">尚無資料，請於後端執行產業同步後再試。</p>
      )}
    </div>
  )
}
