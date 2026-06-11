import { useAppStore } from '../store'
import styles from './StockList.module.css'

function formatChange(change) {
  if (change == null) return null
  const sign = change >= 0 ? '+' : ''
  return `${sign}${change.toFixed(2)}`
}

function formatChangePct(pct) {
  if (pct == null) return null
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

export default function StockList() {
  const stocks = useAppStore(s => s.stocks)
  const stocksLoading = useAppStore(s => s.stocksLoading)
  const stocksError = useAppStore(s => s.stocksError)
  const hasSearched = useAppStore(s => s.hasSearched)
  const selectedStock = useAppStore(s => s.selectedStock)
  const selectStock = useAppStore(s => s.selectStock)

  if (stocksLoading) {
    return (
      <div className={styles.loading}>
        <div className={styles.spinner} />
        <span>載入中...</span>
      </div>
    )
  }

  if (stocksError) {
    return (
      <div className={styles.error}>
        <span>⚠ {stocksError}</span>
      </div>
    )
  }

  if (stocks.length === 0 && !hasSearched) return null

  if (stocks.length === 0) {
    return (
      <div className={styles.empty}>
        <span>沒有符合條件的股票</span>
      </div>
    )
  }

  return (
    <div className={styles.list}>
      {stocks.map(stock => {
        const up = stock.change != null ? stock.change > 0 : null
        const down = stock.change != null ? stock.change < 0 : null
        const colorCls = up ? styles.up : down ? styles.down : styles.flat

        return (
          <button
            key={stock.stock_id}
            className={`${styles.item} ${selectedStock?.stock_id === stock.stock_id ? styles.selected : ''}`}
            onClick={() => selectStock(stock)}
          >
            {/* Left: code + name */}
            <div className={styles.itemLeft}>
              <span className={styles.stockId}>{stock.stock_id}</span>
              <span className={styles.stockName}>{stock.stock_name}</span>
            </div>

            {/* Right: price / change / change_pct */}
            <div className={styles.itemRight}>
              <span className={`${styles.price} ${colorCls}`}>
                {stock.close_price != null ? stock.close_price.toFixed(2) : '--'}
              </span>
              <span className={`${styles.changeRow} ${colorCls}`}>
                {formatChange(stock.change)}
                {stock.change_pct != null && (
                  <span className={styles.changePct}> ({formatChangePct(stock.change_pct)})</span>
                )}
              </span>
            </div>
          </button>
        )
      })}
    </div>
  )
}
