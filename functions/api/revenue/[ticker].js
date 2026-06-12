// functions/api/revenue/[ticker].js
// GET /api/revenue/:ticker?years=3
export async function onRequestGet({ request, env, params }) {
    const ticker = params.ticker;
    const url = new URL(request.url);
    const years = Math.min(parseInt(url.searchParams.get('years') || '3', 10), 10);
    const limit = years * 12;

  const sql = `SELECT year, month, revenue, revenue_mom, revenue_yoy, cumulative_revenue, cumulative_yoy FROM month_revenues WHERE stock_id = ? ORDER BY year DESC, month DESC LIMIT ?`;

  try {
        const { results } = await env.DB.prepare(sql).bind(ticker, limit).all();
        if (results.length === 0) {
                return Response.json({ detail: 'No revenue data found' }, { status: 404 });
        }
        return Response.json(results);
  } catch (e) {
        return Response.json({ error: e.message }, { status: 500 });
  }
}
