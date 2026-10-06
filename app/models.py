from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy import JSON, Boolean, false as sa_false, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import config


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    plan: Mapped[str] = mapped_column(String(30), default="trial")
    case_quota: Mapped[int] = mapped_column(Integer, default=10)  # legacy, unused: billing is credit based
    credits: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 1 credit = 1 document analysed
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(300))
    address: Mapped[str] = mapped_column(String(300), default="")
    region: Mapped[str] = mapped_column(String(20), default="flanders")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|analyzed
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # LLM cross-document synthesis
    analyzed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    documents: Mapped[list[Document]] = relationship(back_populates="case", cascade="all, delete-orphan")
    findings: Mapped[list[Finding]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="Finding.id"
    )


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    billed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())  # credit already charged
    ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # optional LLM read (never affects the score)
    filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    doc_type: Mapped[str] = mapped_column(String(30), default="unknown")
    classification_confidence: Mapped[float] = mapped_column(default=0.0)
    pages: Mapped[list] = mapped_column(JSON, default=list)  # [text per page]
    fields: Mapped[dict] = mapped_column(JSON, default=dict)  # name -> {value, page, excerpt}
    ocr_pages: Mapped[list] = mapped_column(JSON, default=list)  # [{"page": n, "confidence": c}]
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    case: Mapped[Case] = relationship(back_populates="documents")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(40))
    rule_version: Mapped[str] = mapped_column(String(40))
    domain: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10))  # info|low|medium|high
    kind: Mapped[str] = mapped_column(String(20))  # fact|inference|risk|action
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    question_for: Mapped[str] = mapped_column(String(40), default="")  # notary|seller|syndic
    sources: Mapped[list] = mapped_column(JSON, default=list)  # [{doc_id, filename, page, excerpt}]
    review_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|confirmed|dismissed
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    case: Mapped[Case] = relationship(back_populates="findings")
    comments: Mapped[list[Comment]] = relationship(cascade="all, delete-orphan", order_by="Comment.id")


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # sha256; the key itself is shown once
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Payment(Base):
    """Kept for accounting. session_id as primary key makes the Stripe webhook idempotent."""
    __tablename__ = "payments"
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    credits: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    case_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


engine = create_engine(
    config.DB_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if config.DB_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    """Apply Alembic migrations (schema is owned by migrations/, not create_all)."""
    if not config.AUTO_MIGRATE:
        return
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(cfg, "head")
