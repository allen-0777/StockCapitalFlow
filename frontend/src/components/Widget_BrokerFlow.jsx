import { useState } from 'react'
import { Search, TrendingUp, TrendingDown, Loader2 } from 'lucide-react'

function FlowRow({ rank, item }) {
  const isBuy = item.net_shares >= 0
  return (
    <div className="flex items-center px-3 py-2.5 rounded-2xl hover:bg-white/60 transition-all border border-transparent hover:border-white/80">
      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0
        ${rank === 1 ? 'bg-yellow-400 text-white' : rank === 2 ? 'bg-slate-300 text-white' : rank === 3 ? 'bg-amber-600 text-white' : 'bg-slate-100 text-slate-500'}`}>
        {rank}
      </div>
      <div className="ml-3 flex-1 min-w-0">
        <div className="font-medium text-slate-700 text-sm truncate">{item.branch_name}</div>
        <div className="text-xs text-slate-400">{item.branch_id}</div>
      </div>
      <div className="text-xs text-slate-400 mx-3 hidden sm:block tabular-nums">
        <span className="text-red-400">買 {item.buy_shares.toLocaleString()}</span>
        <span className="mx-1 text-slate-300">/</span>
        <span className="text-green-500">賣 {item.sell_shares.toLocaleString()}</span>
      </div>
      <div className={`ml-auto flex items-center font-bold text-sm shrink-0 tabular-nums ${isBuy ? 'text-red-500' : 'text-green-500'}`}>
        {isBuy ? <TrendingUp size={13} className="mr-1 shrink-0" /> : <TrendingDown size={13} className="mr-1 shrink-0" />}
        {isBuy ? `+${item.net_shares.toLocaleString()}` : item.net_shares.toLocaleString()}
      </div>
    </div>
  )
}

function KeyRow({ rank, item }) {
  const winPct = Math.round(item.win_rate * 100)
  const avgRet = (item.avg_return * 100).toFixed(1)
  const isPos = item.avg_return >= 0
  return (
    <div className="flex items-center px-3 py-2.5 rounded-2xl hover:bg-white/60 transition-all border border-transparent hover:border-white/80">
      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0
        ${rank === 1 ? 'bg-yellow-400 text-white' : rank === 2 ? 'bg-slate-300 text-white' : rank === 3 ? 'bg-amber-600 text-white' : 'bg-slate-100 text-slate-500'}`}>
        {rank}
      </div>
      <div className="ml-3 flex-1 min-w-0">
        <div className="font-medium text-slate-700 text-sm truncate">{item.branch_name}</div>
        <div className="text-xs text-slate-400">{item.buy_count} 次買超</div>
      </div>
      <div className="flex items-center gap-3 shrink-0 ml-2">
        <div className="text-center hidden sm:block">
          <div className="text-xs text-slate-400">勝率</div>
          <div className={`text-sm font-bold tabular-nums ${winPct >= 60 ? 'text-red-500' : winPct >= 45 ? 'text-orange-400' : 'text-slate-500'}`}>
            {winPct}%
          </div>
        </div>
        <div className="text-center">
          <div className="text-xs text-slate-400">均報酬</div>
          <div className={`text-sm font-bold tabular-nums ${isPos ? 'text-red-500' : 'text-green-500'}`}>
            {isPos ? '+' : ''}{avgRet}%
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Widget_BrokerFlow() {
  const [stockId, setStockId] = useState('')
  const [inputVal, setInputVal] = useState('')
  const [stockName, setStockName] = useState('')
  const [flowData, setFlowData] = useState([])
  const [keyData, setKeyData] = useState([])
  const [loading, setLoading] = useState(false)
  const [fetching, setFetching] = useState(false)
  const [error, setError] = useState('')
  const [hasData, setHasData] = useState(false)

  async function loadData(sid) {
    setLoading(true)
    setError('')
    try {
      const [flowRes, keyRes] = await Promise.all([
        fetch(`/api/v1/stocks/${sid}/broker/flow?days=30`),
        fetch(`/api/v1/stocks/${sid}/broker/keypoints?lookforward=5&days=90`),
      ])
      const flow = await flowRes.json()
      const key = await keyRes.json()
      setStockName(flow.stock_name || sid)
      setFlowData(flow.branches || [])
      setKeyData(key.branches || [])
      setHasData(true)
    } catch {
      setError('載入失敗，請稍後再試')
    } finally {
      setLoading(false)
    }
  }

  async function handleSearch() {
    const sid = inputVal.trim()
    if (!sid) return
    setStockId(sid)
    setHasData(false)
    setFlowData([])
    setKeyData([])

    // 先嘗試載入資料，若無資料則觸發抓取
    setLoading(true)
    setError('')
    try {
      const [flowRes, keyRes] = await Promise.all([
        fetch(`/api/v1/stocks/${sid}/broker/flow?days=30`),
        fetch(`/api/v1/stocks/${sid}/broker/keypoints?lookforward=5&days=90`),
      ])
      const flow = await flowRes.json()
      const key = await keyRes.json()

      if ((flow.branches || []).length === 0) {
        // 無資料，自動觸發抓取
        setLoading(false)
        setFetching(true)
        const fetchRes = await fetch(`/api/v1/stocks/${sid}/broker/fetch`, { method: 'POST' })
        if (!fetchRes.ok) throw new Error('抓取失敗')
        setFetching(false)
        await loadData(sid)
      } else {
        setStockName(flow.stock_name || sid)
        setFlowData(flow.branches || [])
        setKeyData(key.branches || [])
        setHasData(true)
        setLoading(false)
      }
    } catch (e) {
      setError(e.message || '發生錯誤')
      setLoading(false)
      setFetching(false)
    }
  }

  return (
    <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 flex flex-col">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-5 gap-3">
        <div className="shrink-0">
          <h2 className="text-xl font-bold text-slate-800">
            券商分點進出
            {stockName && stockId && (
              <span className="ml-2 text-base font-medium text-blue-500">{stockId} {stockName}</span>
            )}
          </h2>
          <p className="text-sm text-slate-500 mt-0.5">關鍵分點識別 · 歷史買後漲幅回測</p>
        </div>

        {/* 搜尋框 */}
        <div className="flex items-center gap-2">
          <div className="flex glass-card rounded-2xl overflow-hidden items-center px-3 py-2 gap-2">
            <Search size={15} className="text-slate-400 shrink-0" />
            <input
              type="text"
              value={inputVal}
              onChange={e => setInputVal(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="輸入股號，如 2330"
              className="bg-transparent text-sm text-slate-700 placeholder-slate-400 outline-none w-36"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={loading || fetching}
            className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white text-sm font-medium rounded-2xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            查詢
          </button>
        </div>
      </div>

      {/* 狀態提示 */}
      {(loading || fetching) && (
        <div className="flex-1 flex flex-col items-center justify-center py-16 text-slate-400">
          <Loader2 size={32} className="animate-spin mb-3" />
          <p className="text-sm">{fetching ? '首次查詢，正在從 FinMind 抓取資料（約 10-30 秒）...' : '載入中...'}</p>
        </div>
      )}
      {!loading && !fetching && error && (
        <div className="flex-1 flex items-center justify-center py-16">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}
      {!loading && !fetching && !error && !hasData && (
        <div className="flex-1 flex items-center justify-center py-16 text-slate-400">
          <p className="text-sm">輸入股號後點選查詢，即可查看券商分點進出與關鍵分點回測</p>
        </div>
      )}

      {/* 資料區：左右兩欄 */}
      {!loading && !fetching && !error && hasData && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 min-h-0">

          {/* 左欄：近期主力動向 */}
          <div className="flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-slate-600">近期主力動向</h3>
              <span className="text-xs text-slate-400">最近 30 日（張）</span>
            </div>
            <div className="flex items-center px-3 mb-1 text-xs text-slate-400 font-semibold tracking-wider">
              <div className="w-6 shrink-0">#</div>
              <div className="ml-3 flex-1">分點名稱</div>
              <div className="ml-auto shrink-0">淨買超</div>
            </div>
            <div className="overflow-y-auto custom-scrollbar space-y-0.5 flex-1">
              {flowData.length === 0 ? (
                <p className="text-slate-400 text-sm text-center py-8">無近期分點資料</p>
              ) : flowData.map((item, idx) => (
                <FlowRow key={item.branch_id} rank={idx + 1} item={item} />
              ))}
            </div>
          </div>

          {/* 右欄：關鍵分點回測 */}
          <div className="flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-slate-600">關鍵分點回測</h3>
              <span className="text-xs text-slate-400">90日 · 買後5日報酬</span>
            </div>
            <div className="flex items-center px-3 mb-1 text-xs text-slate-400 font-semibold tracking-wider">
              <div className="w-6 shrink-0">#</div>
              <div className="ml-3 flex-1">分點名稱</div>
              <div className="shrink-0 hidden sm:block mr-8">勝率</div>
              <div className="ml-auto shrink-0">均報酬</div>
            </div>
            <div className="overflow-y-auto custom-scrollbar space-y-0.5 flex-1">
              {keyData.length === 0 ? (
                <p className="text-slate-400 text-sm text-center py-8">
                  {flowData.length > 0 ? '回測資料不足（需要股價資料）' : '無分點資料'}
                </p>
              ) : keyData.map((item, idx) => (
                <KeyRow key={item.branch_id} rank={idx + 1} item={item} />
              ))}
            </div>
          </div>

        </div>
      )}
    </div>
  )
}
