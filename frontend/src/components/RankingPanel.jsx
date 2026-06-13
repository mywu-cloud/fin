import { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../store'
import styles from './RankingPanel.module.css'

const COLS = [
    { key: 'rank', label: '排名', align: 'center' },
    { key: 'stock_id', label: '代碼', align: 'center' },
    { key: 'stock_name', label: '股票', align: 'left' },
    { key: 'close_price', label: '成交價', align: 'right' },
    { key: 'revenue', label: '營收(千)', align: 'right' },
    { key: 'revenue_mom', label: '月增率%', align: 'right' },
    { key: 'revenue_yoy', label: '年增率%', align: 'right' },
  ]

function fmt(v, decimals = 2) {
    if (v == null || v === '') return '--'
    const n = parseFloat(v)
    if (isNaN(n)) return '--'
    return n.toLocaleString('zh-TW', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
  }

export default function RankingPanel() {
    const stocks = useAppStore(s => s.stocks)
    const [rows, setRows] = useState([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const [sortKey, setSortKey] = useState('revenue_mom')
    const [sortDir, setSortDir] = useState('desc')
    const [marketFilter, setMarketFilter] = useState('all')

    const loadRanking = useCallback(async () => {
          if (!stocks || stocks.length === 0) return
          setLoading(true)
          setError('')
          const results = []
          const target = stocks.filter(s =>
                                             marketFilter === 'all' ? true : s.market === marketFilter
                                           )
          for (let i = 0; i < target.length; i++) {
                  const s = target[i]
                  try {
                            const res = await fetch(`/api/revenue/${s.stock_id}?years=1`)
                            if (!res.ok) continue
                            const data = await res.json()
                            if (!data || data.length === 0) continue
                            const latest = data.reduce((a, b) => {
                                        if (a.year !== b.year) return a.year > b.year ? a : b
                                        return a.month > b.month ? a : b
                                      }, data[0])
                            if (latest.revenue_mom == null) continue
                            results.push({
                                        stock_id: s.stock_id,
                                        stock_name: s.stock_name,
                                        close_price: s.close_price,
                                        revenue: latest.revenue,
                                        revenue_mom: latest.revenue_mom,
                                        revenue_yoy: latest.revenue_yoy,
                                        year: latest.year,
                                        month: latest.month,
                                      })
                          } catch (e) {
                            // skip
                          }
                }
          setRows(results)
          setLoading(false)
        }, [stocks, marketFilter])

    useEffect(() => {
          if (stocks && stocks.length > 0) {
                  loadRanking()
                }
        }, [stocks, marketFilter])

    const sorted = [...rows].sort((a, b) => {
          const av = a[sortKey]
          const bv = b[sortKey]
          if (av == null && bv == null) return 0
          if (av == null) return 1
          if (bv == null) return -1
          const diff = parseFloat(av) - parseFloat(bv)
          return sortDir === 'asc' ? diff : -diff
        })

    const handleSort = (key) => {
          if (sortKey === key) {
                  setSortDir(d => d === 'asc' ? 'desc' : 'asc')
                } else {
                  setSortKey(key)
                  setSortDir('desc')
                }
        }

    const sortIcon = (key) => {
          if (sortKey !== key) return ' ⇅'
          return sortDir === 'asc' ? ' ▲' : ' ▼'
        }

    return (
          <div className={styles.wrap}>
            <div className={styles.toolbar}>
              <h2 className={styles.heading}>台股營收月增率排行</h2>
              <div className={styles.filters}>
                <select
                  className={styles.select}
                  value={marketFilter}
                  onChange={e => setMarketFilter(e.target.value)}
                >
                  <option value="all">所有市場</option>
                  <option value="上市">上市</option>
                  <option value="上櫃">上櫃</option>
                </select>
                <button className={styles.refreshBtn} onClick={loadRanking} disabled={loading}>
                  {loading ? '載入中...' : '🔄 重新載入'}
                </button>
              </div>
            </div>

            {error && <div className={styles.error}>{error}</div>}

            {loading ? (
                      <div className={styles.loading}>
                        <div className={styles.spinner}></div>
                        <p>正在載入營收資料，請稍候...</p>
                      </div>
                    ) : rows.length === 0 ? (
                      <div className={styles.empty}>
                        <p>尚無營收資料。請確認後端 /api/sync 已成功執行並取得資料。</p>
                      </div>
                    ) : (
                      <div className={styles.tableWrap}>
                        <table className={styles.table}>
                          <thead>
                            <tr>
                              {COLS.map(col => (
                                                  <th
                                                    key={col.key}
                                                    className={`${styles.th} ${styles['align-' + col.align]}`}
                                                    onClick={() => col.key !== 'rank' && handleSort(col.key)}
                                                    style={{ cursor: col.key !== 'rank' ? 'pointer' : 'default' }}
                                                  >
                                                    {col.label}{col.key !== 'rank' ? sortIcon(col.key) : ''}
                                                  </th>
                                                ))}
                            </tr>
                          </thead>
                          <tbody>
                            {sorted.map((row, i) => (
                                              <tr key={row.stock_id} className={i % 2 === 0 ? styles.rowEven : styles.rowOdd}>
                                                <td className={`${styles.td} ${styles['align-center']}`}>{i + 1}</td>
                                                <td className={`${styles.td} ${styles['align-center']} ${styles.stockId}`}>{row.stock_id}</td>
                                                <td className={`${styles.td} ${styles['align-left']}`}>{row.stock_name}</td>
                                                <td className={`${styles.td} ${styles['align-right']}`}>{fmt(row.close_price)}</td>
                                                <td className={`${styles.td} ${styles['align-right']}`}>{fmt(row.revenue, 0)}</td>
                                                <td className={`${styles.td} ${styles['align-right']} ${parseFloat(row.revenue_mom) >= 0 ? styles.up : styles.down}`}>
                                                  {fmt(row.revenue_mom)}%
                                                </td>
                                                <td className={`${styles.td} ${styles['align-right']} ${parseFloat(row.revenue_yoy) >= 0 ? styles.up : styles.down}`}>
                                                  {fmt(row.revenue_yoy)}%
                                                </td>
                                              </tr>
                                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
          </div>
        )
  }
