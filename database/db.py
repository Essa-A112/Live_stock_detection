import os
from datetime import datetime, timedelta
from contextlib import contextmanager

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker, Session

from database.models import Base, StockPrice, CompanyInfo, TechnicalIndicator

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stock_data.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db():
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def is_cache_fresh(ticker: str, db: Session, max_age_minutes: int = 60) -> bool:
    cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
    row = db.query(StockPrice).filter(
        StockPrice.ticker == ticker,
        StockPrice.created_at >= cutoff,
    ).first()
    return row is not None


def get_cached_prices(ticker: str, db: Session):
    rows = (
        db.query(StockPrice)
        .filter(StockPrice.ticker == ticker)
        .order_by(StockPrice.date)
        .all()
    )
    return rows


def get_cached_company(ticker: str, db: Session):
    return db.query(CompanyInfo).filter(CompanyInfo.ticker == ticker).first()


def get_cached_indicators(ticker: str, db: Session):
    rows = (
        db.query(TechnicalIndicator)
        .filter(TechnicalIndicator.ticker == ticker)
        .order_by(TechnicalIndicator.date)
        .all()
    )
    return rows


def upsert_prices(ticker: str, rows: list[dict], db: Session):
    db.execute(delete(StockPrice).where(StockPrice.ticker == ticker))
    for row in rows:
        db.add(StockPrice(
            ticker=ticker,
            date=row["date"],
            open=row.get("open"),
            high=row.get("high"),
            low=row.get("low"),
            close=row.get("close"),
            volume=row.get("volume"),
        ))


def upsert_company(ticker: str, info: dict, db: Session):
    db.execute(delete(CompanyInfo).where(CompanyInfo.ticker == ticker))
    db.add(CompanyInfo(
        ticker=ticker,
        name=info.get("name"),
        sector=info.get("sector"),
        industry=info.get("industry"),
        market_cap=info.get("market_cap"),
        pe_ratio=info.get("pe_ratio"),
        eps=info.get("eps"),
        beta=info.get("beta"),
        dividend_yield=info.get("dividend_yield"),
        description=info.get("description"),
        website=info.get("website"),
        employees=info.get("employees"),
        current_price=info.get("current_price"),
        week_52_high=info.get("week_52_high"),
        week_52_low=info.get("week_52_low"),
    ))


def upsert_indicators(ticker: str, rows: list[dict], db: Session):
    db.execute(delete(TechnicalIndicator).where(TechnicalIndicator.ticker == ticker))
    for row in rows:
        db.add(TechnicalIndicator(
            ticker=ticker,
            date=row["date"],
            rsi=row.get("rsi"),
            macd=row.get("macd"),
            macd_signal=row.get("macd_signal"),
            macd_hist=row.get("macd_hist"),
            bb_upper=row.get("bb_upper"),
            bb_middle=row.get("bb_middle"),
            bb_lower=row.get("bb_lower"),
            sma20=row.get("sma20"),
            sma50=row.get("sma50"),
            ema20=row.get("ema20"),
            volatility=row.get("volatility"),
        ))
