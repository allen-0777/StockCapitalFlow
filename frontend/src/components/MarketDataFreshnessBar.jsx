import { CalendarClock, Info } from 'lucide-react'

/** 顯示 YYYY-MM-DD 為 MM-DD */
function shortDate(iso) {
  if (!iso) return '—'
  const s = String(iso)
  return s.length >= 10 ? s.slice(5, 10) : s
}

/**
 * 大盤總覽：各卡片資料來自不同 API／排程，日期可能不一致。
 * 依賴 /api/v1/market/summary 的 *_date 與 options_date。
 */
export default function MarketDataFreshnessBar({ data }) {
  if (!data) return null

  const segments = [
    { label: '法人', date: data.institutional_date },
    { label: '融資券', date: data.margin_date },
    { label: '期貨OI', date: data.futures_oi_date },
    { label: '選擇權', date: data.options_date },
  ].filter((s) => s.date)

  if (segments.length === 0) return null

  const unique = new Set(segments.map((s) => s.date))
  const allAligned = unique.size === 1

  return (
    <div className="rounded-2xl border border-slate-200/90 bg-gradient-to-r from-slate-50/95 to-blue-50/40 px-3 sm:px-4 py-2.5 sm:py-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
        <span className="inline-flex items-center gap-1 sm:gap-1.5 font-semibold text-slate-800 shrink-0 text-xs sm:text-sm">
          <CalendarClock className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-blue-500 shrink-0" aria-hidden />
          資料日
        </span>
        {allAligned ? (
          <span className="text-slate-600">
            各區塊皆為 <strong className="text-slate-900 tabular-nums">{segments[0].date}</strong> 盤後（以上傳成功之資料庫為準）
          </span>
        ) : (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs sm:text-sm">
            {segments.map(({ label, date }) => (
              <span
                key={label}
                className="inline-flex items-baseline gap-1 rounded-lg bg-white/80 px-2 py-0.5 border border-slate-200/80 tabular-nums"
              >
                <span className="text-slate-500">{label}</span>
                <span className="font-semibold text-slate-900">{shortDate(date)}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {!allAligned && (
        <details className="mt-2 group">
          <summary className="flex items-center gap-1 text-xs text-amber-800/90 cursor-pointer list-none [&::-webkit-details-marker]:hidden">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span className="underline decoration-amber-400/80 underline-offset-2">
              為什麼同一頁會有多個日期？
            </span>
          </summary>
          <p className="mt-2 text-xs text-slate-600 leading-relaxed pl-5 border-l-2 border-amber-200/80">
            三大法人與融資券來自<strong>證交所</strong>不同報表，釋出時間常差半天～數日；
            期貨與選擇權來自 <strong>FinMind</strong>，更新節奏又不一樣。
            下方各卡片標題旁的日期為該指標實際對應之交易日，屬正常現象；若需對齊，請以排程全數跑完後再刷新。
          </p>
        </details>
      )}
    </div>
  )
}
