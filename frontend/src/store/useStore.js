import { create } from 'zustand'

const useStore = create((set) => ({
  activeTab: 'overview',
  watchlist: [],

  setActiveTab: (tab) => set({ activeTab: tab }),
  setWatchlist: (list) => set({ watchlist: list }),

  addStock: async (stockId) => {
    await fetch(`/api/v1/users/1/watchlist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stock_id: stockId }),
    })
  },

  removeStock: async (stockId) => {
    await fetch(`/api/v1/users/1/watchlist/${stockId}`, { method: 'DELETE' })
  },
}))

export default useStore
