import { create } from 'zustand'
import { apiKeyHeaders } from '../apiHeaders'

const useStore = create((set) => ({
  activeTab: 'overview',
  watchlist: [],

  setActiveTab: (tab) => set({ activeTab: tab }),
  setWatchlist: (list) => set({ watchlist: list }),

  addStock: async (stockId) => {
    await fetch(`/api/v1/users/1/watchlist`, {
      method: 'POST',
      headers: { ...apiKeyHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ stock_id: stockId }),
    })
  },

  removeStock: async (stockId) => {
    await fetch(`/api/v1/users/1/watchlist/${stockId}`, { method: 'DELETE', headers: apiKeyHeaders })
  },
}))

export default useStore
