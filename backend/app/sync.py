"""
Data synchronisation helpers.
Sources:
  - TWSE OpenAPI  (listed stocks + close price + industry)
  - TPEx OpenAPI  (OTC stocks + close price + industry)
  - FinMind API   (TaiwanStockMonthRevenue)

FinMind TaiwanStockMonthRevenue field mapping:
  date           - 公告日 (YYYY-MM-01), NOT the revenue month
  stock_id       - stock code
  revenue_year   - actual year of the revenue month
  revenue_month  - actual month number (1-12)
  revenue        - monthly revenue in NT$
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .database import engine, AsyncSessionLocal, init_db
from .models import Stock, MonthRevenue

logger = logging.getLogger(__name__)

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "")
FINMIND_API = "https://api.finmindtrade.com/api/v4/data"

# ---------------------------------------------------------------------------
# Industry mapping helpers
# ---------------------------------------------------------------------------

async def _fetch_twse_industry_map(client: httpx.AsyncClient) -> Dict[str, str]:
    """Fetch 產業別 for TWSE listed stocks.
    Uses t187ap03_L endpoint: fields include 公司代號, 產業別
    """
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        result: Dict[str, str] = {}
        for item in data:
            code = str(item.get("公司代號", "") or item.get("stock_id", "")).strip()
            industry = str(item.get("產業別", "") or item.get("industry", "")).strip()
            if code and industry:
                result[code] = industry
        logger.info("TWSE industry map: %d entries", len(result))
        return result
    except Exception as e:
        logger.warning("TWSE industry map fetch error: %s", e)
        return {}


async def _fetch_tpex_industry_map(client: httpx.AsyncClient) -> Dict[str, str]:
    """Fetch 產業別 for TPEx OTC stocks.
    Uses mopsfin_t21sc03 endpoint: fields include SecuritiesCompanyCode, IndustryCode
    Also try tpex_mainboard_peratio_analysis which has 產業別
    """
    # Try primary endpoint
    url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t21sc03"
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            result: Dict[str, str] = {}
            sample_keys = list(data[0].keys()) if data else []
            logger.info("TPEx industry endpoint keys: %s", sample_keys)
            for item in data:
                # Try common field name patterns
                code = (
                    str(item.get("SecuritiesCompanyCode", "")
                        or item.get("公司代號", "")
                        or item.get("代號", "")).strip()
                )
                industry = (
                    str(item.get("IndustryCode", "")
                        or item.get("產業別", "")
                        or item.get("產業類別", "")).strip()
                )
                if code and industry:
                    result[code] = industry
            logger.info("TPEx industry map: %d entries", len(result))
            return result
    except Exception as e:
        logger.warning("TPEx industry map (primary) error: %s", e)

    # Fallback: try peratio endpoint
    url2 = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
    try:
        r2 = await client.get(url2, timeout=30)
        r2.raise_for_status()
        data2 = r2.json()
        if isinstance(data2, list) and data2:
            result2: Dict[str, str] = {}
            for item in data2:
                code = str(item.get("SecuritiesCompanyCode", "") or item.get("代號", "")).strip()
                industry = str(item.get("IndustryCode", "") or item.get("產業別", "")).strip()
                if code and industry:
                    result2[code] = industry
            logger.info("TPEx industry map (fallback): %d entries", len(result2))
            return result2
    except Exception as e2:
        logger.warning("TPEx industry map (fallback) error: %s", e2)

    return {}


# ---------------------------------------------------------------------------
# Stock list helpers
# ---------------------------------------------------------------------------

async def _fetch_twse_stocks(
    client: httpx.AsyncClient,
    industry_map: Dict[str, str],
) -> List[Dict]:
    """Fetch listed (上市) stocks from TWSE OpenAPI."""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        stocks = []
        for item in data:
            code = item.get("Code", "").strip()
            name = item.get("Name", "").strip()
            close_raw = item.get("ClosingPrice", "")
            if not code or not name:
                continue
            try:
                close = float(str(close_raw).replace(",", "")) if close_raw else None
            except (ValueError, AttributeError):
                close = None
            stocks.append({
                "stock_id": code,
                "stock_name": name,
                "market": "TWSE",
                "industry": industry_map.get(code),
                "close_price": close,
            })
        logger.info("TWSE: fetched %d stocks", len(stocks))
        if stocks:
            logger.info("TWSE sample (first 3): %s", stocks[:3])
        return stocks
    except Exception as e:
        logger.error("TWSE fetch error: %s", e)
        return []


async def _fetch_tpex_stocks(
    client: httpx.AsyncClient,
    industry_map: Dict[str, str],
) -> List[Dict]:
    """Fetch OTC (上櫃) stocks from TPEx OpenAPI."""
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        stocks = []
        for item in data:
            code = item.get("SecuritiesCompanyCode", "").strip()
            name = item.get("CompanyName", "").strip()
            close_raw = item.get("Close", "")
            if not code or not name:
                continue
            try:
                close = float(str(close_raw).replace(",", "")) if close_raw else None
            except (ValueError, AttributeError):
                close = None
            # TPEx close quote endpoint also contains industry in some versions
            industry = (
                industry_map.get(code)
                or item.get("IndustryCode", "")
                or item.get("產業別", "")
                or None
            )
            stocks.append({
                "stock_id": code,
                "stock_name": name,
                "market": "TPEx",
                "industry": industry,
                "close_price": close,
            })
        logger.info("TPEx: fetched %d stocks", len(stocks))
        if stocks:
            logger.info("TPEx sample (first 3): %s", stocks[:3])
        return stocks
    except Exception as e:
        logger.error("TPEx fetch error: %s", e)
        return []


# ---------------------------------------------------------------------------
# FinMind revenue helper
# ---------------------------------------------------------------------------

async def _fetch_finmind_revenue(
    client: httpx.AsyncClient, stock_id: str, start_date: str = "2015-01-01"
) -> List[Dict]:
    """Fetch monthly revenue for a single stock from FinMind."""
    params = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": stock_id,
        "start_date": start_date,
        "token": FINMIND_TOKEN,
    }
    try:
        r = await client.get(FINMIND_API, params=params, timeout=60)
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != 200:
            logger.warning(
                "FinMind %s: status=%s msg=%s",
                stock_id, payload.get("status"), payload.get("msg"),
            )
            return []
        rows = payload.get("data", [])
        if stock_id == "2330" and rows:
            logger.info("FinMind 2330 sample (first 3): %s", rows[:3])
        return rows
    except Exception as e:
        logger.error("FinMind %s error: %s", stock_id, e)
        return []


# ---------------------------------------------------------------------------
# Database upsert helpers
# ---------------------------------------------------------------------------

async def _upsert_stocks(stocks: List[Dict]) -> None:
    """Upsert stock list into DB as a single atomic batch."""
    if not stocks:
        return
    now = datetime.utcnow().isoformat()
    rows = [
        {
            "stock_id": s["stock_id"],
            "stock_name": s["stock_name"],
            "market": s["market"],
            "industry": s.get("industry"),
            "close_price": s.get("close_price"),
            "updated_at": now,
        }
        for s in stocks
    ]
    stmt = sqlite_insert(Stock)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id"],
        set_={
            "stock_name": stmt.excluded.stock_name,
            "market": stmt.excluded.market,
            "industry": stmt.excluded.industry,
            "close_price": stmt.excluded.close_price,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    async with engine.begin() as conn:
        await conn.execute(stmt, rows)
    logger.info("Upserted %d stocks", len(rows))


def _calc_pct_change(
    new_val: Optional[int], old_val: Optional[int]
) -> Optional[float]:
    if new_val is None or old_val is None or old_val == 0:
        return None
    return round((new_val - old_val) / abs(old_val) * 100, 2)


async def _upsert_revenues(rows: List[Dict]) -> None:
    """Upsert monthly revenue rows as a single atomic batch."""
    if not rows:
        return

    rev_map: Dict[Tuple[int, int], int] = {}
    for r in rows:
        y = int(r.get("revenue_year", 0) or 0)
        m = int(r.get("revenue_month", 0) or 0)
        rev = int(r.get("revenue", 0) or 0)
        if y and m:
            rev_map[(y, m)] = rev

    db_rows = []
    for r in rows:
        try:
            stock_id = r.get("stock_id", "").strip()
            y = int(r.get("revenue_year", 0) or 0)
            m = int(r.get("revenue_month", 0) or 0)
            if not stock_id or not y or not m:
                continue
            revenue = int(r.get("revenue", 0) or 0)

            prev_m_key = (y, m - 1) if m > 1 else (y - 1, 12)
            revenue_mom = _calc_pct_change(revenue, rev_map.get(prev_m_key))
            revenue_yoy = _calc_pct_change(revenue, rev_map.get((y - 1, m)))

            cumulative_revenue: Optional[int] = sum(
                rev_map.get((y, mo), 0) for mo in range(1, m + 1)
                if (y, mo) in rev_map
            ) or None
            cum_prev: Optional[int] = sum(
                rev_map.get((y - 1, mo), 0) for mo in range(1, m + 1)
                if (y - 1, mo) in rev_map
            ) or None
            cumulative_yoy = _calc_pct_change(cumulative_revenue, cum_prev)

            db_rows.append({
                "stock_id": stock_id,
                "year": y,
                "month": m,
                "revenue": revenue,
                "revenue_mom": revenue_mom,
                "revenue_yoy": revenue_yoy,
                "cumulative_revenue": cumulative_revenue,
                "cumulative_yoy": cumulative_yoy,
            })
        except Exception as e:
            logger.warning("Revenue row error: %s | row=%s", e, r)

    if not db_rows:
        return

    stmt = sqlite_insert(MonthRevenue)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_stock_ym",
        set_={
            "revenue": stmt.excluded.revenue,
            "revenue_mom": stmt.excluded.revenue_mom,
            "revenue_yoy": stmt.excluded.revenue_yoy,
            "cumulative_revenue": stmt.excluded.cumulative_revenue,
            "cumulative_yoy": stmt.excluded.cumulative_yoy,
        },
    )
    async with engine.begin() as conn:
        await conn.execute(stmt, db_rows)
    logger.info(
        "Upserted %d revenue rows for %s",
        len(db_rows),
        db_rows[0]["stock_id"] if db_rows else "?",
    )


# ---------------------------------------------------------------------------
# Main sync entry point
# ---------------------------------------------------------------------------

async def run_sync(full: bool = False) -> None:
    """
    full=True  - fetch ALL stocks' revenue history
    full=False - update stock list + prices + recent revenue for priority stocks
    """
    logger.info("run_sync started (full=%s)", full)
    await init_db()

    async with httpx.AsyncClient() as client:
        # 1. Fetch industry maps in parallel
        twse_ind, tpex_ind = await asyncio.gather(
            _fetch_twse_industry_map(client),
            _fetch_tpex_industry_map(client),
        )

        # 2. Fetch stock lists with industry info
        twse_stocks, tpex_stocks = await asyncio.gather(
            _fetch_twse_stocks(client, twse_ind),
            _fetch_tpex_stocks(client, tpex_ind),
        )
        all_stocks = twse_stocks + tpex_stocks
        await _upsert_stocks(all_stocks)

        if not all_stocks:
            logger.warning("No stocks fetched; skipping revenue sync")
            return

        # 3. Revenue sync
        if full:
            stock_ids = [s["stock_id"] for s in all_stocks]
            start_date = "2010-01-01"
        else:
            priority_ids = [
                "2330", "2317", "2454", "2382", "2308",
                "2303", "3711", "2412", "1301", "1303",
                "2881", "2882", "2886", "2891", "5880",
            ]
            stock_ids = priority_ids
            today = date.today()
            start_date = "{}-01-01".format(today.year - 1 if today.month >= 4 else today.year - 2)

        logger.info("Fetching revenue for %d stocks from %s", len(stock_ids), start_date)

        sem = asyncio.Semaphore(3)

        async def fetch_and_store(sid: str) -> None:
            async with sem:
                rows = await _fetch_finmind_revenue(client, sid, start_date)
                if rows:
                    logger.info("  %s: %d revenue rows", sid, len(rows))
                    await _upsert_revenues(rows)
                await asyncio.sleep(0.3)

        await asyncio.gather(*[fetch_and_store(sid) for sid in stock_ids])

    logger.info("run_sync completed")
