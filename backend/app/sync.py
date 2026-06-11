"""
Data synchronisation helpers.

Sources:
  - TWSE OpenAPI  (listed stocks + close price)
  - TPEx OpenAPI  (OTC stocks  + close price)
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

from .database import AsyncSessionLocal, init_db
from .models import Stock, MonthRevenue

logger = logging.getLogger(__name__)

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "")
FINMIND_API = "https://api.finmindtrade.com/api/v4/data"


# ---------------------------------------------------------------------------
# Stock list helpers
# ---------------------------------------------------------------------------

async def _fetch_twse_stocks(client: httpx.AsyncClient) -> List[Dict]:
    """Fetch listed (上市) stocks from TWSE OpenAPI."""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        # Fields: Code, Name, ClosingPrice (string with commas)
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
                "close_price": close,
            })
        logger.info("TWSE: fetched %d stocks", len(stocks))
        if stocks:
            logger.info("TWSE sample (first 5): %s", stocks[:5])
        return stocks
    except Exception as e:
        logger.error("TWSE fetch error: %s", e)
        return []


async def _fetch_tpex_stocks(client: httpx.AsyncClient) -> List[Dict]:
    """Fetch OTC (上櫃) stocks from TPEx OpenAPI."""
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        # Fields: SecuritiesCompanyCode, CompanyName, Close (string)
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
            stocks.append({
                "stock_id": code,
                "stock_name": name,
                "market": "TPEx",
                "close_price": close,
            })
        logger.info("TPEx: fetched %d stocks", len(stocks))
        if stocks:
            logger.info("TPEx sample (first 5): %s", stocks[:5])
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
    """Fetch monthly revenue for a single stock from FinMind.

    Returned row fields:
      date           - report date "YYYY-MM-01"
      stock_id       - e.g. "2330"
      revenue_year   - year of the revenue month (int)
      revenue_month  - month number 1-12 (int)
      revenue        - NT$ amount
    """
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
            logger.info("FinMind 2330 sample (first 5): %s", rows[:5])
            logger.info("FinMind 2330 field names: %s", list(rows[0].keys()))
        return rows
    except Exception as e:
        logger.error("FinMind %s error: %s", stock_id, e)
        return []


# ---------------------------------------------------------------------------
# Database upsert helpers
# ---------------------------------------------------------------------------

async def _upsert_stocks(stocks: List[Dict]) -> None:
    """Upsert stock list into DB."""
    if not stocks:
        return
    now = datetime.utcnow().isoformat()
    async with AsyncSessionLocal() as session:
        for s in stocks:
            stmt = sqlite_insert(Stock).values(
                stock_id=s["stock_id"],
                stock_name=s["stock_name"],
                market=s["market"],
                close_price=s.get("close_price"),
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["stock_id"],
                set_={
                    "stock_name": stmt.excluded.stock_name,
                    "market": stmt.excluded.market,
                    "close_price": stmt.excluded.close_price,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
        await session.commit()
    logger.info("Upserted %d stocks", len(stocks))


def _calc_pct_change(new_val: Optional[int], old_val: Optional[int]) -> Optional[float]:
    """Calculate percentage change from old to new."""
    if new_val is None or old_val is None or old_val == 0:
        return None
    return round((new_val - old_val) / abs(old_val) * 100, 2)


async def _upsert_revenues(rows: List[Dict]) -> None:
    """Upsert monthly revenue rows.

    FinMind fields:
      revenue_year  (int)  - actual year
      revenue_month (int)  - actual month 1-12
      revenue       (int)  - NT$
    """
    if not rows:
        return

    # Build a lookup {(year, month): revenue} for MoM/YoY
    rev_map: Dict[Tuple[int, int], int] = {}
    for r in rows:
        y = int(r.get("revenue_year", 0) or 0)
        m = int(r.get("revenue_month", 0) or 0)
        rev = int(r.get("revenue", 0) or 0)
        if y and m:
            rev_map[(y, m)] = rev

    async with AsyncSessionLocal() as session:
        for r in rows:
            try:
                stock_id = r.get("stock_id", "").strip()
                y = int(r.get("revenue_year", 0) or 0)
                m = int(r.get("revenue_month", 0) or 0)
                if not stock_id or not y or not m:
                    continue
                revenue = int(r.get("revenue", 0) or 0)

                # MoM: compare to previous month
                prev_m_key = (y, m - 1) if m > 1 else (y - 1, 12)
                prev_rev = rev_map.get(prev_m_key)
                revenue_mom = _calc_pct_change(revenue, prev_rev)

                # YoY: compare to same month last year
                yoy_rev = rev_map.get((y - 1, m))
                revenue_yoy = _calc_pct_change(revenue, yoy_rev)

                # Cumulative: sum Jan..month within same year present in batch
                cumulative_revenue = sum(
                    rev_map.get((y, mo), 0) for mo in range(1, m + 1)
                    if (y, mo) in rev_map
                ) or None

                # Cumulative YoY
                cum_prev = sum(
                    rev_map.get((y - 1, mo), 0) for mo in range(1, m + 1)
                    if (y - 1, mo) in rev_map
                ) or None
                cumulative_yoy = _calc_pct_change(cumulative_revenue, cum_prev)

                stmt = sqlite_insert(MonthRevenue).values(
                    stock_id=stock_id,
                    year=y,
                    month=m,
                    revenue=revenue,
                    revenue_mom=revenue_mom,
                    revenue_yoy=revenue_yoy,
                    cumulative_revenue=cumulative_revenue,
                    cumulative_yoy=cumulative_yoy,
                )
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
                await session.execute(stmt)
            except Exception as e:
                logger.warning("Revenue row error: %s | row=%s", e, r)
        await session.commit()
    logger.info("Upserted %d revenue rows", len(rows))


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
        # 1. Fetch stock lists from TWSE + TPEx
        twse_stocks, tpex_stocks = await asyncio.gather(
            _fetch_twse_stocks(client),
            _fetch_tpex_stocks(client),
        )
        all_stocks = twse_stocks + tpex_stocks
        await _upsert_stocks(all_stocks)

        if not all_stocks:
            logger.warning("No stocks fetched; skipping revenue sync")
            return

        # 2. Determine stocks & date range
        if full:
            stock_ids = [s["stock_id"] for s in all_stocks]
            start_date = "2010-01-01"
        else:
            # Incremental: priority large-cap stocks
            priority_ids = [
                "2330", "2317", "2454", "2382", "2308",
                "2303", "3711", "2412", "1301", "1303",
                "2881", "2882", "2886", "2891", "5880",
            ]
            stock_ids = priority_ids
            today = date.today()
            # Go back ~15 months to compute full YoY
            if today.month >= 4:
                start_date = "{}-01-01".format(today.year - 1)
            else:
                start_date = "{}-01-01".format(today.year - 2)

        logger.info("Fetching revenue for %d stocks from %s", len(stock_ids), start_date)

        # 3. Fetch with rate-limiting
        sem = asyncio.Semaphore(3)

        async def fetch_and_store(sid: str) -> None:
            async with sem:
                rows = await _fetch_finmind_revenue(client, sid, start_date)
                if rows:
                    logger.info("  %s: %d revenue rows", sid, len(rows))
                    await _upsert_revenues(rows)
                await asyncio.sleep(0.3)

        tasks = [fetch_and_store(sid) for sid in stock_ids]
        await asyncio.gather(*tasks)

    logger.info("run_sync completed")
