"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from apscheduler.schedulers.background import BackgroundScheduler

from .database import get_db, init_db
from .models import Stock, MonthRevenue
from .sync import run_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Asia/Taipei")


async def _safe_sync(full: bool = False) -> None:
    """Run sync and swallow exceptions so server keeps running."""
    try:
        await run_sync(full=full)
    except Exception as exc:
        logger.error("run_sync crashed: %s", exc, exc_info=True)


def _schedule_sync() -> None:
    """Called by APScheduler (sync context) — fires async sync task."""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.run_coroutine_threadsafe(_safe_sync(full=False), loop)
    else:
        asyncio.run(_safe_sync(full=False))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    logger.info("DB initialised")

    # Auto-sync on startup (non-blocking background task)
    asyncio.create_task(_safe_sync(full=False))

    # Schedule daily sync at 18:30 (after market close)
    try:
        scheduler.add_job(
            _schedule_sync,
            "cron",
            hour=18,
            minute=30,
            id="daily_sync",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Scheduler started (daily 18:30)")
    except Exception as exc:
        logger.warning("Scheduler failed to start: %s", exc)

    yield

    # Shutdown
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
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
    q: str = Query(default="", description="Search by stock_id or stock_name"),
    market: str = Query(default="", description="TWSE or TPEx"),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Stock)
    if q:
        stmt = stmt.where(
            (Stock.stock_id.ilike("%" + q + "%")) | (Stock.stock_name.ilike("%" + q + "%"))
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
    """Return monthly revenue for a stock, sorted desc."""
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
    """Manually trigger a data sync."""
    asyncio.create_task(_safe_sync(full=full))
    return {"status": "sync started", "full": full}
