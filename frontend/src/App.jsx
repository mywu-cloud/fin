import { useEffect, useCallback, useRef } from 'react'
import { useAppStore } from './store'
import StockSearch from './components/StockSearch'
import StockList from './components/StockList'
import RevenuePanel from './components/RevenuePanel'
import styles from './App.module.css'

export default function App() {
  const fetchStocks = useAppStore(s => s.fetchStocks)
  const fetchStockCount = useAppStore(s => s.fetchStockCount)
  const searchQuery = useAppStore(s => s.searchQuery)
  const marketFilter = useAppStore(s => s.marketFilter)
  const totalStocks = useAppStore(s => s.totalStocks)
  const triggerSync = useAppStore(s => s.triggerSync)
  const selectedStock = useAppStore(s => s.selectedStock)

  // Debounce helper
  const debounceRef = useRef(null)

  const debouncedFetch = useCallback(() => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      fetchStocks()
    }, 300)
  }, [fetchStocks])

  useEffect(() => {
    fetchStockCount()
    fetchStocks()
  }, [])

  useEffect(() => {
    debouncedFetch()
  }, [searchQuery, marketFilter])

  const handleSync = async () => {
    await triggerSync(false)
    setTimeout(() => {
      fetchStocks()
      fetchStockCount()
    }, 2000)
  }

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <h1 className={styles.title}>台股月營收查詢</h1>
        <div className={styles.headerRight}>
          {totalStocks > 0 && (
            <span className={styles.stockCount}>共 {totalStocks.toLocaleString()} 支股票</span>
          )}
          <button className={styles.syncBtn} onClick={handleSync}>
            🔄 更新資料
          </button>
        </div>
      </header>

      <main className={styles.main}>
        <aside className={styles.sidebar}>
          <StockSearch />
          <StockList />
        </aside>

        <section className={styles.content}>
          {selectedStock ? (
            <RevenuePanel />
          ) : (
            <div className={styles.empty}>
              <div className={styles.emptyIcon}>📊</div>
              <p>請從左側選擇一支股票，查看月營收資料</p>
              {totalStocks === 0 && (
                <p className={styles.emptyHint}>
                  資料庫尚無資料，請點擊「更新資料」按鈕同步
                </p>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
