import { useEffect, useState, useCallback } from 'react'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import BottomTabBar from './components/BottomTabBar'
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
    <div className="min-h-screen bg-[#f8fafc] text-slate-800 font-sans relative">

      {/* Background blobs — smaller on mobile */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden -z-10 pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-64 h-64 sm:w-96 sm:h-96 bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl opacity-40 sm:opacity-70 animate-blob"></div>
        <div className="absolute top-[20%] right-[-10%] w-64 h-64 sm:w-96 sm:h-96 bg-cyan-200 rounded-full mix-blend-multiply filter blur-3xl opacity-40 sm:opacity-70 animate-blob animation-delay-2000"></div>
        <div className="absolute bottom-[-20%] left-[20%] w-64 h-64 sm:w-96 sm:h-96 bg-emerald-100 rounded-full mix-blend-multiply filter blur-3xl opacity-40 sm:opacity-70 animate-blob animation-delay-4000"></div>
      </div>

      {/* Header */}
      <Header onRefresh={handleRefresh} />

      {/* Desktop sidebar + content layout */}
      <div className="max-w-7xl mx-auto lg:px-8 lg:py-6 lg:grid lg:grid-cols-12 lg:gap-8">

        {/* Desktop sidebar (hidden on mobile) */}
        <div className="hidden lg:flex lg:col-span-2">
          <Sidebar />
        </div>

        {/* Main content area */}
        <main className="lg:col-span-10 px-4 pb-20 lg:pb-8 pt-4 lg:pt-0 space-y-4 sm:space-y-6 overflow-y-auto lg:max-h-[calc(100vh-8rem)] custom-scrollbar">

          {activeTab === 'overview' && (
            <>
              <Widget1_Institutional data={marketData} />
              <Widget3_LiquidGauge data={marketData} />
              <Widget4_FuturesOI data={marketData} />
              <Widget5_Options refreshNonce={optionsRefreshNonce} />
              <MarketDataFreshnessBar data={marketData} />
            </>
          )}

          {activeTab === 'institutional' && (
            <>
              <Widget_InstitutionalSummary marketData={marketData} />
              <Widget_InstitutionalRanking />
            </>
          )}

          {activeTab === 'broker' && (
            <Widget_BrokerFlow />
          )}

          {activeTab === 'concentration' && (
            <Widget_Concentration />
          )}

          {activeTab === 'watchlist' && (
            <Widget2_Watchlist watchlist={watchlist} onRefresh={fetchWatchlist} />
          )}

        </main>
      </div>

      {/* Bottom tab bar (mobile only) */}
      <BottomTabBar />

    </div>
  )
}
