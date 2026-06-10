import { useAppStore } from '../store'
import styles from './StockList.module.css'

export default function StockList() {
  const stocks = useAppStore(s => s.stocks)
  const stocksLoading = useAppStore(s => s.stocksLoading)
  const stocksError = useAppStore(s => s.stocksError)
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

  if (stocks.length === 0) {
    return (
      <div className={styles.empty}>
        <span>沒有符合條件的股票</span>
      </div>
    )
  }

  return (
    <div className={styles.list}>
      {stocks.map(stock => (
        <button
          key={stock.stock_id}
          className={`${styles.item} ${selectedStock?.stock_id === stock.stock_id ? styles.selected : ''}`}
          onClick={() => selectStock(stock)}
        >
          <div className={styles.itemLeft}>
            <span className={styles.stockId}>{stock.stock_id}</span>
            <span className={styles.stockName}>{stock.stock_name}</span>
          </div>
          <div className={styles.itemRight}>
            {stock.close_price != null && (
              <span className={styles.price}>
                {stock.close_price.toFixed(2)}
              </span>
            )}
            <span className={`${styles.market} ${stock.market === 'TWSE' ? styles.twse : styles.tpex}`}>
              {stock.market === 'TWSE' ? '上市' : '上櫃'}
            </span>
          </div>
        </button>
      ))}
    </div>
  )
}
