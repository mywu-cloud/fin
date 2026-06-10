import { useAppStore } from '../store'
import styles from './StockSearch.module.css'

export default function StockSearch() {
  const searchQuery = useAppStore(s => s.searchQuery)
  const marketFilter = useAppStore(s => s.marketFilter)
  const setSearchQuery = useAppStore(s => s.setSearchQuery)
  const setMarketFilter = useAppStore(s => s.setMarketFilter)

  return (
    <div className={styles.container}>
      <input
        type="text"
        className={styles.input}
        placeholder="搜尋股號或股名..."
        value={searchQuery}
        onChange={e => setSearchQuery(e.target.value)}
      />
      <div className={styles.filters}>
        <button
          className={`${styles.filterBtn} ${marketFilter === '' ? styles.active : ''}`}
          onClick={() => setMarketFilter('')}
        >
          全部
        </button>
        <button
          className={`${styles.filterBtn} ${marketFilter === 'TWSE' ? styles.active : ''}`}
          onClick={() => setMarketFilter('TWSE')}
        >
          上市
        </button>
        <button
          className={`${styles.filterBtn} ${marketFilter === 'TPEx' ? styles.active : ''}`}
          onClick={() => setMarketFilter('TPEx')}
        >
          上櫃
        </button>
      </div>
    </div>
  )
}
