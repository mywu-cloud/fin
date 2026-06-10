import { useAppStore } from '../store'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, ReferenceLine, Legend
} from 'recharts'
import styles from './RevenuePanel.module.css'

// Revenue is stored in NT$; display in 億 (100M) or 千萬 (10M)
function fmtRevenue(val) {
  if (val == null) return '-'
  const n = Number(val)
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(2) + ' 億'
  if (n >= 100_000_000) return (n / 100_000_000).toFixed(2) + ' 億'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + ' 百萬'
  return n.toLocaleString()
}

// Short form for chart axis ticks
function fmtRevenueAxis(val) {
  if (val == null) return ''
  const n = Number(val)
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + '億'
  if (n >= 100_000_000) return (n / 100_000_000).toFixed(0) + '億'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(0) + 'M'
  return n.toLocaleString()
}

function fmtPct(val) {
  if (val == null) return '-'
  const n = Number(val)
  const sign = n > 0 ? '+' : ''
  return sign + n.toFixed(2) + '%'
}

function PctBadge({ val }) {
  if (val == null) return <span className={styles.neutral}>-</span>
  const n = Number(val)
  const cls = n > 0 ? styles.up : n < 0 ? styles.down : styles.neutral
  return <span className={cls}>{fmtPct(val)}</span>
}

export default function RevenuePanel() {
  const selectedStock = useAppStore(s => s.selectedStock)
  const revenue = useAppStore(s => s.revenue)
  const revenueLoading = useAppStore(s => s.revenueLoading)
  const revenueError = useAppStore(s => s.revenueError)
  const revenueYears = useAppStore(s => s.revenueYears)
  const setRevenueYears = useAppStore(s => s.setRevenueYears)
  const selectStock = useAppStore(s => s.selectStock)

  if (!selectedStock) return null

  // Sort ascending for chart
  const sortedRevenue = [...revenue].sort((a, b) =>
    a.year !== b.year ? a.year - b.year : a.month - b.month
  )

  const chartData = sortedRevenue.map(r => ({
    label: `${r.year}-${String(r.month).padStart(2, '0')}`,
    revenue: r.revenue,
    yoy: r.revenue_yoy,
    mom: r.revenue_mom,
  }))

  const handleYearsChange = (y) => {
    setRevenueYears(y)
    selectStock(selectedStock)
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div className={styles.stockInfo}>
          <h2 className={styles.stockId}>{selectedStock.stock_id}</h2>
          <span className={styles.stockName}>{selectedStock.stock_name}</span>
          <span className={`${styles.market} ${selectedStock.market === 'TWSE' ? styles.twse : styles.tpex}`}>
            {selectedStock.market === 'TWSE' ? '上市' : '上櫃'}
          </span>
          {selectedStock.close_price != null && (
            <span className={styles.closePrice}>{selectedStock.close_price.toFixed(2)}</span>
          )}
        </div>
        <div className={styles.yearSelector}>
          {[1, 2, 3, 5].map(y => (
            <button
              key={y}
              className={`${styles.yearBtn} ${revenueYears === y ? styles.activeYear : ''}`}
              onClick={() => handleYearsChange(y)}
            >
              {y}年
            </button>
          ))}
        </div>
      </div>

      {revenueLoading && (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>載入營收資料...</span>
        </div>
      )}

      {revenueError && (
        <div className={styles.error}>{revenueError}</div>
      )}

      {!revenueLoading && !revenueError && revenue.length > 0 && (
        <>
          {/* Revenue Bar Chart */}
          <div className={styles.chartSection}>
            <h3 className={styles.chartTitle}>月營收 (NT$)</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 8, right: 20, left: 20, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                  angle={-45}
                  textAnchor="end"
                  interval={Math.max(0, Math.floor(chartData.length / 12) - 1)}
                />
                <YAxis
                  tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                  tickFormatter={fmtRevenueAxis}
                  width={65}
                />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
                  labelStyle={{ color: 'var(--text-primary)' }}
                  formatter={(val) => [fmtRevenue(val), '月營收']}
                />
                <Bar dataKey="revenue" fill="var(--accent)" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* YoY/MoM Line Chart */}
          <div className={styles.chartSection}>
            <h3 className={styles.chartTitle}>年增率 / 月增率 (%)</h3>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData} margin={{ top: 8, right: 20, left: 10, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                  angle={-45}
                  textAnchor="end"
                  interval={Math.max(0, Math.floor(chartData.length / 12) - 1)}
                />
                <YAxis
                  tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                  tickFormatter={v => v + '%'}
                  width={55}
                />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
                  labelStyle={{ color: 'var(--text-primary)' }}
                  formatter={(val, name) => [fmtPct(val), name === 'yoy' ? '年增率' : '月增率']}
                />
                <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="4 2" />
                <Legend
                  formatter={(val) => val === 'yoy' ? '年增率' : '月增率'}
                  wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 12 }}
                />
                <Line type="monotone" dataKey="yoy" stroke="var(--up)" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="mom" stroke="var(--down)" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Revenue Table */}
          <div className={styles.tableSection}>
            <h3 className={styles.chartTitle}>月營收明細</h3>
            <div className={styles.tableWrapper}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>年月</th>
                    <th>月營收</th>
                    <th>月增率</th>
                    <th>年增率</th>
                    <th>累計營收</th>
                    <th>累計年增率</th>
                  </tr>
                </thead>
                <tbody>
                  {revenue.map(r => (
                    <tr key={`${r.year}-${r.month}`}>
                      <td className={styles.dateCell}>{r.year}/{String(r.month).padStart(2, '0')}</td>
                      <td className={styles.numCell}>{fmtRevenue(r.revenue)}</td>
                      <td><PctBadge val={r.revenue_mom} /></td>
                      <td><PctBadge val={r.revenue_yoy} /></td>
                      <td className={styles.numCell}>{fmtRevenue(r.cumulative_revenue)}</td>
                      <td><PctBadge val={r.cumulative_yoy} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!revenueLoading && !revenueError && revenue.length === 0 && (
        <div className={styles.noData}>此股票尚無營收資料，請點擊「更新資料」同步。</div>
      )}
    </div>
  )
}
