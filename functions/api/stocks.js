// functions/api/stocks.js
// GET /api/stocks?q=&market=&industry=&skip=0&limit=200
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
    const q = url.searchParams.get('q') || '';
      const market = url.searchParams.get('market') || '';
        const industry = url.searchParams.get('industry') || '';
          const skip = parseInt(url.searchParams.get('skip') || '0', 10);
            const limit = Math.min(parseInt(url.searchParams.get('limit') || '200', 10), 500);

              // 4-digit stock code, first digit 1-9
                let sql = `SELECT stock_id, stock_name, market, industry, close_price, change, change_pct, updated_at
                    FROM stocks
                        WHERE length(stock_id) = 4 AND substr(stock_id,1,1) BETWEEN '1' AND '9'`;
                          const params = [];

                            if (q) {
                                sql += ` AND (stock_id LIKE ? OR stock_name LIKE ?)`;
                                    params.push(`%${q}%`, `%${q}%`);
                                      }
                                        if (market) {
                                            sql += ` AND market = ?`;
                                                params.push(market);
                                                  }
                                                    if (industry) {
                                                        sql += ` AND industry = ?`;
                                                            params.push(industry);
                                                              }
                                                                sql += ` ORDER BY stock_id LIMIT ? OFFSET ?`;
                                                                  params.push(limit, skip);

                                                                    try {
                                                                        const { results } = await env.DB.prepare(sql).bind(...params).all();
                                                                            return Response.json(results);
                                                                              } catch (e) {
                                                                                  return Response.json({ error: e.message }, { status: 500 });
                                                                                    }
                                                                                    }
