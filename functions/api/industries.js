// functions/api/industries.js
// GET /api/industries?market=TWSE|TPEx
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
    const market = url.searchParams.get('market') || '';

      let sql = `SELECT DISTINCT industry FROM stocks WHERE length(stock_id) = 4 AND substr(stock_id,1,1) BETWEEN '1' AND '9' AND industry IS NOT NULL AND industry != ''`;
        const params = [];

          if (market) {
              sql += ` AND market = ?`;
                  params.push(market);
                    }
                      sql += ` ORDER BY industry`;

                        try {
                            const { results } = await env.DB.prepare(sql).bind(...params).all();
                                return Response.json(results.map(r => r.industry));
                                  } catch (e) {
                                      return Response.json({ error: e.message }, { status: 500 });
                                        }
                                        }
