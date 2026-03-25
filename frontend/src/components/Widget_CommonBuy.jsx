import { useState, useEffect } from 'react'
import { Handshake, TrendingUp, Loader2 } from 'lucide-react'

function fmtNum(v) {
  const abs = Math.abs(v)
  const sign = v >= 0 ? '+' : '-'
  return sign + abs.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export default function Widget_CommonBuy() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/institutional/common-buy?limit=30')
      .then(r => r.json())
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-6">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-pink-400 to-rose-500 flex items-center justify-center">
            <Handshake size={16} className="text-white" />
          </div>
          <div>
            <div className="font-bold text-slate-700 text-sm">外資投信同買</div>
            <div className="text-[10px] text-slate-400">
              {data?.date ? `${data.date} 盤後資料` : '同日外資 + 投信皆買超'}
            </div>
          </div>
        </div>
        {data?.stocks && (
          <span className="text-xs text-slate-400">{data.stocks.length} 檔</span>
        )}
      </div>

      {loading && (
        <div className="flex items-center justify-center py-10 text-slate-400">
          <Loader2 size={18} className="animate-spin" />
        </div>
      )}

      {!loading && (!data?.stocks?.length) && (
        <div className="text-center py-10 text-slate-400 text-sm">今日無外資投信同買個股</div>
      )}

      {!loading && data?.stocks?.length > 0 && (
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
          <table className="w-full min-w-[28rem] table-fixed border-collapse">
            <colgroup>
              <col style={{ width: '3rem' }} />
              <col style={{ width: '5rem' }} />
              <col />
              <col />
              <col />
            </colgroup>
            <thead>
              <tr className="border-b border-slate-200">
                <th className="text-left text-xs text-slate-400 font-medium py-1.5 px-2">#</th>
                <th className="text-left text-xs text-slate-400 font-medium py-1.5 px-2">代號</th>
                <th className="text-right text-xs font-medium py-1.5 px-2" style={{ color: '#3b82f6' }}>外資</th>
                <th className="text-right text-xs font-medium py-1.5 px-2" style={{ color: '#a855f7' }}>投信</th>
                <th className="text-right text-xs text-slate-400 font-medium py-1.5 px-2">合計</th>
              </tr>
            </thead>
            <tbody>
              {data.stocks.map((s, i) => (
                <tr key={s.stock_id} className={i % 2 === 0 ? 'bg-transparent' : 'bg-slate-50/40'}>
                  <td className="text-xs text-slate-400 py-2 px-2">{i + 1}</td>
                  <td className="py-2 px-2">
                    <div className="text-sm font-medium text-slate-700">{s.stock_id}</div>
                    <div className="text-[10px] text-slate-400 truncate">{s.name}</div>
                  </td>
                  <td className="text-right text-sm tabular-nums py-2 px-2 text-red-500">
                    {fmtNum(s.foreign_buy)}
                  </td>
                  <td className="text-right text-sm tabular-nums py-2 px-2 text-red-500">
                    {fmtNum(s.trust_buy)}
                  </td>
                  <td className="text-right text-sm tabular-nums py-2 px-2 font-bold text-red-600">
                    {fmtNum(s.total)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
