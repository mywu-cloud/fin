import { create } from 'zustand'

const API_BASE = '/api'

export const useAppStore = create((set, get) => ({
  // Stock list
  stocks: [],
  stocksLoading: false,
  stocksError: null,
  searchQuery: '',
  marketFilter: '',      // '' | 'TWSE' | 'TPEx'
  industryFilter: '',    // '' or industry name
  hasSearched: false,    // true after first user-initiated search/filter

  // Industries
  industries: [],        // list of industry names for current marketFilter

  // Selected stock & revenue
  selectedStock: null,
  revenue: [],
  revenueLoading: false,
  revenueError: null,
  revenueYears: 3,

  // Actions
  setSearchQuery: (q) => {
    set({ searchQuery: q, hasSearched: true })
  },

  setMarketFilter: (m) => {
    // Reset industry when switching market
    set({ marketFilter: m, industryFilter: '', hasSearched: true })
    // Fetch industries for this market
    get().fetchIndustries(m)
  },

  setIndustryFilter: (ind) => {
    set({ industryFilter: ind, hasSearched: true })
  },

  fetchIndustries: async (market) => {
    try {
      const params = new URLSearchParams()
      if (market) params.set('market', market)
      const res = await fetch(`${API_BASE}/industries?${params}`)
      if (!res.ok) return
      const data = await res.json()
      set({ industries: data })
    } catch {
      set({ industries: [] })
    }
  },

  fetchStocks: async () => {
    const { searchQuery, marketFilter, industryFilter } = get()
    set({ stocksLoading: true, stocksError: null })
    try {
      const params = new URLSearchParams({ limit: 200, skip: 0 })
      if (searchQuery) params.set('q', searchQuery)
      if (marketFilter) params.set('market', marketFilter)
      if (industryFilter) params.set('industry', industryFilter)
      const res = await fetch(`${API_BASE}/stocks?${params}`)
      if (!res.ok) throw new Error('Failed to fetch stocks')
      const data = await res.json()
      set({ stocks: data, stocksLoading: false })
    } catch (e) {
      set({ stocksError: e.message, stocksLoading: false })
    }
  },

  fetchStockCount: async () => {
    try {
      const res = await fetch(`${API_BASE}/stocks/count`)
      if (!res.ok) return
      const data = await res.json()
      set({ totalStocks: data.count })
    } catch {
      // silent
    }
  },

  selectStock: async (stock) => {
    set({ selectedStock: stock, revenueLoading: true, revenueError: null, revenue: [] })
    const { revenueYears } = get()
    try {
      const res = await fetch(`${API_BASE}/revenue/${stock.stock_id}?years=${revenueYears}`)
      if (!res.ok) {
        if (res.status === 404) throw new Error('尚無營收資料')
        throw new Error('Failed to fetch revenue')
      }
      const data = await res.json()
      set({ revenue: data, revenueLoading: false })
    } catch (e) {
      set({ revenueError: e.message, revenueLoading: false })
    }
  },

  triggerSync: async (full = false) => {
    try {
      const res = await fetch(`${API_BASE}/sync?full=${full}`, { method: 'POST' })
      if (!res.ok) throw new Error('Sync failed')
      return true
    } catch (e) {
      console.error('Sync error:', e)
      return false
    }
  },

  totalStocks: 0,
  setRevenueYears: (y) => set({ revenueYears: y }),
}))
