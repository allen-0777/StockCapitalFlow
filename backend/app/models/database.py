from sqlalchemy import create_engine, Column, String, Date, Numeric, Integer, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.dialects.sqlite import insert
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'data.db')}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    notify_token = Column(String, nullable=True)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stock_id = Column(String, nullable=False)


class Stock(Base):
    __tablename__ = "stocks"
    stock_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)


class DailyChip(Base):
    __tablename__ = "daily_chips"
    date = Column(Date, primary_key=True)
    stock_id = Column(String, primary_key=True)
    foreign_buy = Column(Numeric, nullable=True)
    trust_buy = Column(Numeric, nullable=True)
    dealer_buy = Column(Numeric, nullable=True)
    margin_long = Column(Integer, nullable=True)
    margin_short = Column(Integer, nullable=True)


class BrokerDaily(Base):
    __tablename__ = "broker_daily"
    date = Column(String, primary_key=True)
    stock_id = Column(String, primary_key=True)
    branch_id = Column(String, primary_key=True)
    branch_name = Column(String, nullable=True)
    buy_shares = Column(Integer, default=0)
    sell_shares = Column(Integer, default=0)


class StockPrice(Base):
    __tablename__ = "stock_prices"
    date = Column(String, primary_key=True)
    stock_id = Column(String, primary_key=True)
    close = Column(Numeric, nullable=True)
    volume = Column(Integer, nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        existing = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
        if existing == 0:
            db.execute(text("INSERT INTO users (id, username) VALUES (1, 'default')"))
            db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
