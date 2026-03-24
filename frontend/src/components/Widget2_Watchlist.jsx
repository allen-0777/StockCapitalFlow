import { useState } from 'react'
import { ChevronRight, Plus, Trash2 } from 'lucide-react'
import useStore from '../store/useStore'

export default function Widget2_Watchlist({ watchlist, onRefresh }) {
  const { addStock, removeStock } = useStore()
  const [input, setInput] = useState('')
  const [adding, setAdding] = useState(false)

  const handleAdd = async () => {
    const sid = input.trim()
    if (!sid) return
    setAdding(true)
    await addStock(sid)
    setInput('')
    setAdding(false)
    onRefresh()
  }

  const handleRemove = async (stockId) => {
    await removeStock(stockId)
    onRefresh()
  }

  return (
    <div className="glass-card rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 flex flex-col">
      <div className="flex justify-between items-center mb-4 sm:mb-6">
        <h2 className="text-lg font-bold text-slate-800">關注清單籌碼動能</h2>
        <div className="flex items-center space-x-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            placeholder="輸入股號"
            className="w-24 px-3 py-1.5 text-sm glass-card rounded-full focus:outline-none focus:ring-2 focus:ring-blue-400/50 placeholder-slate-400"
          />
          <button
            onClick={handleAdd}
            disabled={adding}
            className="p-1.5 rounded-full bg-blue-500 text-white hover:bg-blue-600 transition-colors"
          >
            <Plus size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-4">
        {watchlist.length === 0 && (
          <p className="text-slate-400 text-sm text-center py-8">尚無關注股票，請輸入股號新增</p>
        )}
        {watchlist.map((stock) => {
          const foreignNet = stock.foreign_buy ?? 0
          const isBuy = foreignNet >= 0
          return (
            <div
              key={stock.stock_id}
              className="group flex items-center justify-between p-3 rounded-2xl hover:bg-white/60 transition-all border border-transparent hover:border-white/80 cursor-pointer"
            >
              <div className="flex items-center space-x-4">
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl sm:rounded-2xl bg-gradient-to-br from-slate-100 to-slate-200 flex items-center justify-center font-bold text-slate-600 shadow-inner text-xs">
                  {stock.stock_id}
                </div>
                <div>
                  <div className="font-bold text-slate-800 text-sm sm:text-lg">{stock.name || stock.stock_id}</div>
                  <div className="flex items-center text-xs space-x-2">
                    <span className="text-slate-400">{stock.stock_id}</span>
                    <span className="text-slate-300">|</span>
                    <span className={`font-semibold ${isBuy ? 'text-red-500' : 'text-green-500'}`}>
                      外資 {isBuy ? `+${foreignNet.toFixed(0)}` : foreignNet.toFixed(0)} 千股
                    </span>
                    <span className="text-slate-300">|</span>
                    <span className="text-slate-500 flex items-center">
                      {isBuy ? <span className="text-red-500">買超</span> : <span className="text-green-500">賣超</span>}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleRemove(stock.stock_id)}
                  className="p-1.5 rounded-full text-slate-300 hover:text-red-400 hover:bg-red-50 transition-colors sm:opacity-0 sm:group-hover:opacity-100"
                >
                  <Trash2 size={16} />
                </button>
                <ChevronRight size={18} className="text-slate-300 group-hover:text-blue-500 transition-colors" />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
