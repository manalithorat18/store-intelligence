from sqlalchemy import create_engine, Column, String, Boolean, Float, Integer, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DB_PATH = os.getenv("DB_PATH", "./data/store.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class EventDB(Base):
    __tablename__ = "events"

    event_id       = Column(String, primary_key=True, index=True)
    store_id       = Column(String, index=True)
    camera_id      = Column(String)
    visitor_id     = Column(String, index=True)
    event_type     = Column(String, index=True)
    timestamp      = Column(String, index=True)
    zone_id        = Column(String, nullable=True)
    dwell_ms       = Column(Integer, default=0)
    is_staff       = Column(Boolean, default=False)
    confidence     = Column(Float, default=1.0)
    queue_depth    = Column(Integer, nullable=True)
    sku_zone       = Column(String, nullable=True)
    session_seq    = Column(Integer, nullable=True)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()