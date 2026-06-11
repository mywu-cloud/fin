"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db, init_db
from .models import Stock, MonthRevenue
from .sync import run_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _safe_sync(full: bool = False) -> None:
    """Run sync, swallow exceptions so server keeps running."""
    try:
        await run_sync(full=full)
    except Exception as exc:
        logger.error("run_sync error: %s", exc, exc_info=True)


async def _daily_scheduler() -> None:
    """Pure-asyncio loop: fire sync every day at 18:30 CST."""
    while True:
        try:
            now = datetime.now()
            # Seconds until next 18:30
            target_hour, target_min = 18, 30
            secs_today = (target_hour * 60 + target_min) * 60
            secs_now = (now.hour * 60 + now.minute) * 60 + now.second
            wait = secs_today - secs_now
            if wait <= 0:
                wait += 86400  # already past 18:30, wait until tomorrow
            logger.info("Daily sync scheduled in %.0f minutes", wait / 60)
            await asyncio.sleep(wait)
            logger.info("Running scheduled daily sync")
            await _safe_sync(full=False)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Scheduler loop error: %s", exc)
            await asyncio.sleep(3600)  # retry in 1h


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("DB initialised")

    # Startup sync (non-blocking)
    asyncio.create_task(_safe_sync(full=False))

    # Daily scheduler (pure asyncio, no APScheduler)
    sched_task = asyncio.create_task(_daily_scheduler())

    yield

    sched_task.cancel()
    try:
        await sched_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutdown complete")


app = FastAPI(title="Taiwan Stock Revenue API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/stocks")
async def list_stocks(
    q: str = Query(default=""),
    market: str = Query(default=""),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Stock)
    if q:
        stmt = stmt.where(
            (Stock.stock_id.ilike("%" + q + "%")) |
            (Stock.stock_name.ilike("%" + q + "%"))
        )
    if market:
        stmt = stmt.where(Stock.market == market)
    stmt = stmt.order_by(Stock.stock_id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    stocks = result.scalars().all()
    return [
        {
            "stock_id": s.stock_id,
            "stock_name": s.stock_name,
            "market": s.market,
            "close_price": s.close_price,
            "updated_at": s.updated_at,
        }
        for s in stocks
    ]


@app.get("/api/stocks/count")
async def count_stocks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count()).select_from(Stock))
    return {"count": result.scalar()}


@app.get("/api/stocks/{stock_id}")
async def get_stock(stock_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.stock_id == stock_id))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    return {
        "stock_id": stock.stock_id,
        "stock_name": stock.stock_name,
        "market": stock.market,
        "close_price": stock.close_price,
        "updated_at": stock.updated_at,
    }


@app.get("/api/revenue/{stock_id}")
async def get_revenue(
    stock_id: str,
    years: int = Query(default=3, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MonthRevenue)
        .where(MonthRevenue.stock_id == stock_id)
        .order_by(MonthRevenue.year.desc(), MonthRevenue.month.desc())
        .limit(years * 12)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="No revenue data found")
    return [
        {
            "year": r.year,
            "month": r.month,
            "revenue": r.revenue,
            "revenue_mom": r.revenue_mom,
            "revenue_yoy": r.revenue_yoy,
            "cumulative_revenue": r.cumulative_revenue,
            "cumulative_yoy": r.cumulative_yoy,
        }
        for r in rows
    ]


@app.post("/api/sync")
async def trigger_sync(full: bool = False):
    asyncio.create_task(_safe_sync(full=full))
    return {"status": "sync started", "full": full}
