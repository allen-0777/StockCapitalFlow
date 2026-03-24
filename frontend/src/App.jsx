import { useEffect, useState, useCallback } from 'react'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import Widget1_Institutional from './components/Widget1_Institutional'
import Widget2_Watchlist from './components/Widget2_Watchlist'
import Widget3_LiquidGauge from './components/Widget3_LiquidGauge'
import Widget_InstitutionalRanking from './components/Widget_InstitutionalRanking'
import Widget_InstitutionalSummary from './components/Widget_InstitutionalSummary'
import Widget_BrokerFlow from './components/Widget_BrokerFlow'
import Widget_Concentration from './components/Widget_Concentration'
import Widget4_FuturesOI from './components/Widget4_FuturesOI'
import Widget5_Options from './components/Widget5_Options'
import MarketDataFreshnessBar from './components/MarketDataFreshnessBar'
import useStore from './store/useStore'

export default function App() {
  const { setWatchlist, activeTab } = useStore()
  const [marketData, setMarketData] = useState(null)
  const [watchlist, setWatchlistLocal] = useState([])
  const [optionsRefreshNonce, setOptionsRefreshNonce] = useState(0)

  const fetchMarket = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/market/summary')
      if (res.ok) setMarketData(await res.json())
    } catch {}
  }, [])

  const fetchWatchlist = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/users/1/watchlist')
      if (res.ok) {
        const data = await res.json()
        setWatchlistLocal(data)
        setWatchlist(data)
      }
    } catch {}
  }, [setWatchlist])

  const handleRefresh = useCallback(() => {
    fetchMarket()
    fetchWatchlist()
    setOptionsRefreshNonce((n) => n + 1)
  }, [fetchMarket, fetchWatchlist])

  useEffect(() => {
    fetchMarket()
    fetchWatchlist()
  }, [fetchMarket, fetchWatchlist])

  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-800 font-sans overflow-hidden relative">

      {/* 液態背景 Blobs */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden -z-10 pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-96 h-96 bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl opacity-70 animate-blob"></div>
        <div className="absolute top-[20%] right-[-10%] w-96 h-96 bg-cyan-200 rounded-full mix-blend-multiply filter blur-3xl opacity-70 animate-blob animation-delay-2000"></div>
        <div className="absolute bottom-[-20%] left-[20%] w-96 h-96 bg-emerald-100 rounded-full mix-blend-multiply filter blur-3xl opacity-70 animate-blob animation-delay-4000"></div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 h-screen flex flex-col">
        <Header onRefresh={handleRefresh} />

        <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-8 min-h-0">
          <Sidebar />

          <div className="lg:col-span-10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 overflow-y-auto pb-8 z-10 pr-2 custom-scrollbar">
            {activeTab === 'overview' && (
              <>
                <MarketDataFreshnessBar data={marketData} />
                <Widget1_Institutional data={marketData} />
                <Widget2_Watchlist watchlist={watchlist} onRefresh={fetchWatchlist} />
                <Widget3_LiquidGauge data={marketData} />
                <Widget4_FuturesOI data={marketData} />
                <Widget5_Options refreshNonce={optionsRefreshNonce} />
              </>
            )}
            {activeTab === 'institutional' && (
              <>
                <div className="lg:col-span-2 md:col-span-2">
                  <Widget_InstitutionalRanking />
                </div>
                <div className="lg:col-span-1">
                  <Widget_InstitutionalSummary marketData={marketData} />
                </div>
              </>
            )}
            {activeTab === 'broker' && (
              <Widget_BrokerFlow />
            )}
            {activeTab === 'concentration' && (
              <Widget_Concentration />
            )}
          </div>
        </div>
      </div>

    </div>
  )
}
