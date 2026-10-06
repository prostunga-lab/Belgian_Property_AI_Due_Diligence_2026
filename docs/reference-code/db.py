import os
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

URL = os.getenv("DATABASE_URL", "sqlite:///./saas.db")
engine = create_engine(URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def now():
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    pw_hash: Mapped[str] = mapped_column(String(200))
    credits: Mapped[int] = mapped_column(Integer, default=0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Analysis(Base):  # on stocke le résultat, jamais le PDF
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    doc_type: Mapped[str] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Payment(Base):  # conservé pour la comptabilité; session_id unique = webhook idempotent
    __tablename__ = "payments"
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    credits: Mapped[int] = mapped_column(Integer)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
