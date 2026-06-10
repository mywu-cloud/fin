"""
Data synchronisation helpers.

Sources:
  - TWSE OpenAPI  (listed stocks + close price)
  - TPEx OpenAPI  (OTC stocks  + close price)
  - FinMind API   (TaiwanStockMonthRevenue)
"""
import asyncio
import logging
import os
from datetime import date, datetime

import httpx
from sqlalchemy import select, insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .database import AsyncSessionLocal, init_db
from .models import Stock, MonthRevenue

logger = logging.getLogger(__name__)

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "")
FINMIND_API = "https://api.finmindtrade.com/api/v4/data"

# ---------------------------------------------------------------------------
# Stock list helpers
# ---------------------------------------------------------------------------

async def _fetch_twse_stocks(client: httpx.AsyncClient) -> list[dict]:
    """Fetch listed (上市) stocks from TWSE OpenAPI."""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        # Field mapping: Code, Name, ClosingPrice
        stocks = []
        for item in data:
            code = item.get("Code", "").strip()
            name = item.get("Name", "").strip()
            close_raw = item.get("ClosingPrice", "")
            if not code or not name:
                continue
            try:
                close = float(close_raw.replace(",", "")) if close_raw else None
            except (ValueError, AttributeError):
                close = None
            stocks.append({"stock_id": code, "stock_name": name, "market": "TWSE", "close_price": close})
        logger.info(f"TWSE: fetched {len(stocks)} stocks")
        if stocks:
            logger.info(f"TWSE sample: {stocks[:5]}")
        return stocks
    except Exception as e:
        logger.error(f"TWSE fetch error: {e}")
        return []


async def _fetch_tpex_stocks(client: httpx.AsyncClient) -> list[dict]:
    """Fetch OTC (上櫃) stocks from TPEx OpenAPI."""
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        # Field mapping: SecuritiesCompanyCode, CompanyName, Close
        stocks = []
        for item in data:
            code = item.get("SecuritiesCompanyCode", "").strip()
            name = item.get("CompanyName", "").strip()
            close_raw = item.get("Close", "")
            if not code or not name:
                continue
            try:
                close = float(close_raw.replace(",", "")) if close_raw else None
            except (ValueError, AttributeError):
                close = None
            stocks.append({"stock_id": code, "stock_name": name, "market": "TPEx", "close_price": close})
        logger.info(f"TPEx: fetched {len(stocks)} stocks")
        if stocks:
            logger.info(f"TPEx sample: {stocks[:5]}")
        return stocks
    except Exception as e:
        logger.error(f"TPEx fetch error: {e}")
        return []


# ---------------------------------------------------------------------------
# FinMind revenue helper
# ---------------------------------------------------------------------------

async def _fetch_finmind_revenue(
    client: httpx.AsyncClient, stock_id: str, start_date: str = "2015-01-01"
) -> list[dict]:
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
            logger.warning(f"FinMind {stock_id}: status={payload.get('status')} msg={payload.get('msg')}")
            return []
        rows = payload.get("data", [])
        return rows
    except Exception as e:
        logger.error(f"FinMind {stock_id} error: {e}")
        return []


# ---------------------------------------------------------------------------
# Database upsert helpers
# ---------------------------------------------------------------------------

async def _upsert_stocks(stocks: list[dict]):
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
    logger.info(f"Upserted {len(stocks)} stocks")


async def _upsert_revenues(rows: list[dict]):
    """Upsert monthly revenue rows into DB.
    
    FinMind fields: stock_id, date (YYYY-MM-01), revenue, revenue_month,
    revenue_year, revenue_YoY (or similar), revenue_MoM
    """
    if not rows:
        return
    async with AsyncSessionLocal() as session:
        for r in rows:
            try:
                stock_id = r.get("stock_id", "")
                # date is like "2024-01-01"
                d = r.get("date", "")
                if not d or not stock_id:
                    continue
                parts = d.split("-")
                year, month = int(parts[0]), int(parts[1])
                revenue = int(r.get("revenue", 0) or 0)
                revenue_mom = _safe_float(r.get("revenue_MoM") or r.get("revenue_mom"))
                revenue_yoy = _safe_float(r.get("revenue_YoY") or r.get("revenue_yoy"))
                cum_rev_raw = r.get("cum_revenue") or r.get("cumulative_revenue")
                cumulative_revenue = int(cum_rev_raw) if cum_rev_raw else None
                cum_yoy_raw = r.get("cum_revenue_YoY") or r.get("cumulative_revenue_yoy")
                cumulative_yoy = _safe_float(cum_yoy_raw)

                stmt = sqlite_insert(MonthRevenue).values(
                    stock_id=stock_id,
                    year=year,
                    month=month,
                    revenue=revenue,
                    revenue_mom=revenue_mom,
                    revenue_yoy=revenue_yoy,
                    cumulative_revenue=cumulative_revenue,
                    cumulative_yoy=cumulative_yoy,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=None,
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
                logger.warning(f"Revenue row error: {e} | row={r}")
        await session.commit()


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Main sync entry point
# ---------------------------------------------------------------------------

async def run_sync(full: bool = False):
    """
    full=True  → fetch ALL stocks' revenue history (slow, for initial load)
    full=False → only update stock list + close prices + last 2 months revenue
    """
    logger.info(f"run_sync started (full={full})")
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

        # 2. Determine which stocks to fetch revenue for
        if full:
            stock_ids = [s["stock_id"] for s in all_stocks]
            start_date = "2010-01-01"
        else:
            # Incremental: only main index stocks or those already in DB
            # For quick startup, just do top stocks + any already in DB
            priority_ids = ["2330", "2317", "2454", "2382", "2308",
                            "2303", "3711", "2412", "1301", "1303"]
            stock_ids = priority_ids
            # Use recent 3 months
            today = date.today()
            if today.month >= 3:
                start_date = f"{today.year}-{today.month-2:02d}-01"
            else:
                start_date = f"{today.year-1}-{12+today.month-2:02d}-01"

        logger.info(f"Fetching revenue for {len(stock_ids)} stocks from {start_date}")

        # 3. Fetch revenue with rate-limiting (avoid API throttle)
        sem = asyncio.Semaphore(3)

        async def fetch_and_store(sid):
            async with sem:
                rows = await _fetch_finmind_revenue(client, sid, start_date)
                if rows:
                    logger.info(f"  {sid}: {len(rows)} revenue rows")
                    if sid == "2330" and rows:
                        logger.info(f"  2330 sample: {rows[:5]}")
                    await _upsert_revenues(rows)
                await asyncio.sleep(0.3)  # be polite to FinMind

        tasks = [fetch_and_store(sid) for sid in stock_ids]
        await asyncio.gather(*tasks)

    logger.info("run_sync completed")
