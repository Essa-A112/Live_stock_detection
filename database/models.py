from sqlalchemy import Column, Integer, String, Float, DateTime, Date, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime


class Base(DeclarativeBase):
    pass


class StockPrice(Base):
    __tablename__ = "stock_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_ticker_date"),)


class CompanyInfo(Base):
    __tablename__ = "company_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, unique=True, index=True)
    name = Column(String(256))
    sector = Column(String(128))
    industry = Column(String(128))
    market_cap = Column(Float)
    pe_ratio = Column(Float)
    eps = Column(Float)
    beta = Column(Float)
    dividend_yield = Column(Float)
    description = Column(String(4096))
    website = Column(String(256))
    employees = Column(Integer)
    current_price = Column(Float)
    week_52_high = Column(Float)
    week_52_low = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class TechnicalIndicator(Base):
    __tablename__ = "technical_indicators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False)
    rsi = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_hist = Column(Float)
    bb_upper = Column(Float)
    bb_middle = Column(Float)
    bb_lower = Column(Float)
    sma20 = Column(Float)
    sma50 = Column(Float)
    ema20 = Column(Float)
    volatility = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_ind_ticker_date"),)
