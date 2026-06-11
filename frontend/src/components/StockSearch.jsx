import { useAppStore } from '../store'
import styles from './StockSearch.module.css'

export default function StockSearch() {
  const searchQuery = useAppStore(s => s.searchQuery)
  const marketFilter = useAppStore(s => s.marketFilter)
  const industryFilter = useAppStore(s => s.industryFilter)
  const industries = useAppStore(s => s.industries)
  const setSearchQuery = useAppStore(s => s.setSearchQuery)
  const setMarketFilter = useAppStore(s => s.setMarketFilter)
  const setIndustryFilter = useAppStore(s => s.setIndustryFilter)

  return (
    <div className={styles.container}>
      <input
        type="text"
        className={styles.input}
        placeholder="搜尋股號或股名..."
        value={searchQuery}
        onChange={e => setSearchQuery(e.target.value)}
      />

      {/* 上市 / 上櫃 toggle — 全部已移除 */}
      <div className={styles.filters}>
        <button
          className={`${styles.filterBtn} ${marketFilter === 'TWSE' ? styles.active : ''}`}
          onClick={() => setMarketFilter(marketFilter === 'TWSE' ? '' : 'TWSE')}
        >
          上市
        </button>
        <button
          className={`${styles.filterBtn} ${marketFilter === 'TPEx' ? styles.active : ''}`}
          onClick={() => setMarketFilter(marketFilter === 'TPEx' ? '' : 'TPEx')}
        >
          上櫃
        </button>
      </div>

      {/* 產業別下拉選單：只在選了上市或上櫃時顯示 */}
      {marketFilter && industries.length > 0 && (
        <div className={styles.industryRow}>
          <select
            className={styles.industrySelect}
            value={industryFilter}
            onChange={e => setIndustryFilter(e.target.value)}
          >
            <option value="">所有產業</option>
            {industries.map(ind => (
              <option key={ind} value={ind}>{ind}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}
