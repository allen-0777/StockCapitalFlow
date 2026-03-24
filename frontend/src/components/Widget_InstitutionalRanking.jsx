import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'

const TYPE_OPTIONS = [
  { value: 'foreign', label: '外資',    short: '外資' },
  { value: 'trust',   label: '投信',    short: '投信' },
  { value: 'dealer',  label: '自營商',  short: '自營' },
  { value: 'total',   label: '三大合計', short: '合計' },
]

const COL_KEYS = ['foreign', 'trust', 'dealer']

function RankRow({ rank, item, col }) {
  const total = (item.foreign_buy ?? 0) + (item.trust_buy ?? 0) + (item.dealer_buy ?? 0)
  const isTotalBuy = total >= 0

  return (
    <div className="group flex items-center px-3 py-2.5 rounded-2xl hover:bg-white/60 transition-all border border-transparent hover:border-white/80">
      {/* 排名 */}
      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0
        ${rank === 1 ? 'bg-yellow-400 text-white' : rank === 2 ? 'bg-slate-300 text-white' : rank === 3 ? 'bg-amber-600 text-white' : 'bg-slate-100 text-slate-500'}`}>
        {rank}
      </div>

      {/* 股號 + 名稱 */}
      <div className="ml-3 w-24 shrink-0 min-w-0">
        <div className="font-bold text-slate-700 text-sm truncate">{item.name}</div>
        <div className="text-xs text-slate-400">{item.stock_id}</div>
      </div>

      {/* 三欄明細：外資／投信／自營，當前排序欄加淡藍底 */}
      <div className="hidden md:grid flex-1 grid-cols-3 gap-1 text-xs text-center mx-3 min-w-0">
        {COL_KEYS.map(k => {
          const v = item[`${k}_buy`]
          const isActive = col === k
          return (
            <span key={k} className={`tabular-nums rounded-lg px-1 py-0.5
              ${isActive ? 'bg-blue-50 font-semibold' : ''}
              ${v >= 0 ? 'text-red-400' : 'text-green-500'}`}>
              {v >= 0 ? `+${v.toFixed(0)}` : v.toFixed(0)}
            </span>
          )
        })}
      </div>

      {/* 三大合計：永遠靠右 */}
      <div className={`ml-auto flex items-center font-bold text-sm shrink-0 tabular-nums ${isTotalBuy ? 'text-red-500' : 'text-green-500'}`}>
        {isTotalBuy ? <TrendingUp size={13} className="mr-1 shrink-0" /> : <TrendingDown size={13} className="mr-1 shrink-0" />}
        {isTotalBuy ? `+${total.toFixed(0)}` : total.toFixed(0)}
      </div>
    </div>
  )
}

export default function Widget_InstitutionalRanking() {
  const [type, setType] = useState('foreign')
  const [order, setOrder] = useState('buy')
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`/api/v1/institutional/ranking?type=${type}&order=${order}&limit=20`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [type, order])

  return (
    <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 flex flex-col h-full">

      {/* Header：標題列 + 控制列，窄版各佔一行 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-5 gap-3">
        <div className="shrink-0">
          <h2 className="text-xl font-bold text-slate-800">個股法人進出排行</h2>
          <p className="text-sm text-slate-500 mt-0.5">單位：千股</p>
        </div>

        {/* 控制列：兩組按鈕，窄版靠左自動折行 */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex glass-card rounded-2xl overflow-hidden">
            {TYPE_OPTIONS.map(o => (
              <button
                key={o.value}
                onClick={() => setType(o.value)}
                className={`px-2.5 py-1.5 text-xs font-medium transition-all whitespace-nowrap ${
                  type === o.value ? 'bg-blue-500 text-white' : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {/* 窄版顯示短名，寬版顯示全名 */}
                <span className="sm:hidden">{o.short}</span>
                <span className="hidden sm:inline">{o.label}</span>
              </button>
            ))}
          </div>

          <div className="flex glass-card rounded-2xl overflow-hidden">
            {[{ value: 'buy', label: '買超', active: 'bg-red-500' }, { value: 'sell', label: '賣超', active: 'bg-green-500' }].map(o => (
              <button
                key={o.value}
                onClick={() => setOrder(o.value)}
                className={`px-3 py-1.5 text-xs font-medium transition-all ${
                  order === o.value ? `${o.active} text-white` : 'text-slate-500 hover:text-slate-700'
                }`}
              >{o.label}</button>
            ))}
          </div>
        </div>
      </div>

      {/* 欄位標題 */}
      <div className="flex items-center px-3 mb-1 text-xs text-slate-400 font-semibold tracking-wider">
        <div className="w-6 shrink-0">#</div>
        <div className="w-24 ml-3 shrink-0">股票</div>
        <div className="hidden md:grid flex-1 grid-cols-3 gap-1 text-center mx-3">
          {[{ key: 'foreign', label: '外資' }, { key: 'trust', label: '投信' }, { key: 'dealer', label: '自營' }].map(({ key, label }) => (
            <span key={key} className={`rounded-lg px-1 py-0.5 ${type === key ? 'bg-blue-50 text-blue-500' : ''}`}>
              {label}{type === key ? ' ↓' : ''}
            </span>
          ))}
        </div>
        <div className="ml-auto shrink-0 text-right">三大合計</div>
      </div>

      {/* 列表 */}
      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-0.5">
        {loading && (
          <p className="text-slate-400 text-sm text-center py-10">載入中...</p>
        )}
        {!loading && data.length === 0 && (
          <p className="text-slate-400 text-sm text-center py-10">尚無個股資料</p>
        )}
        {!loading && data.map((item, idx) => (
          <RankRow key={item.stock_id} rank={idx + 1} item={item} col={type} />
        ))}
      </div>
    </div>
  )
}
