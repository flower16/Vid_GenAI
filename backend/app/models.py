"""SQLite ORM models.

Tables required by the ingestion spec:
  documents · document_chunks · ingestion_jobs · electricity_plans
  bill_calculations · users · audit_logs
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")
    created_at = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    """One row per ingested PDF. file_hash is the dedup key."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    document_id = Column(String, unique=True, nullable=False, index=True)   # uuid
    file_name = Column(String, nullable=False)
    file_hash = Column(String, unique=True, nullable=False, index=True)     # SHA-256
    provider_name = Column(String)
    plan_name = Column(String)
    document_type = Column(String)          # efl | provider_terms | buyback | tdu | bill
    utility_area = Column(String, default="Oncor")
    pinecone_namespace = Column(String, default="oncor_solar_plans")
    ingestion_status = Column(String, default="pending")  # pending|processing|complete|error
    chunk_count = Column(Integer, default=0)
    stored_path = Column(String)
    upload_date = Column(DateTime, default=datetime.utcnow)

    chunks = relationship("DocumentChunk", back_populates="document",
                          cascade="all, delete-orphan")


class DocumentChunk(Base):
    """Reference to each embedded chunk (text + the Pinecone vector id)."""
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True)
    document_id = Column(String, ForeignKey("documents.document_id"), index=True)
    chunk_index = Column(Integer, nullable=False)
    vector_id = Column(String, nullable=False)   # id used in Pinecone
    text = Column(Text)
    page = Column(Integer)
    section = Column(String)
    mentions_tdu_offset = Column(Boolean, default=False)
    mentions_free_nights = Column(Boolean, default=False)

    document = relationship("Document", back_populates="chunks")
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id = Column(Integer, primary_key=True)
    document_id = Column(String, ForeignKey("documents.document_id"))
    status = Column(String, default="queued")  # queued|running|complete|error|skipped_duplicate
    detail = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)


class UploadedFile(Base):
    """One row per uploaded bill/solar/SMT file. sha256 is the dedup key."""
    __tablename__ = "uploaded_files"
    id = Column(Integer, primary_key=True)
    file_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    kind = Column(String, nullable=False)        # bill | solar | smt
    original_name = Column(String)
    stored_path = Column(String)
    sha256 = Column(String, index=True)          # dedup key (not unique: re-upload ok per user)
    parse_status = Column(String, default="pending")  # pending | ok | error
    parsed_json = Column(Text)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Job(Base):
    """One row per /compare run — makes ranking results durable across restarts."""
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    job_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="queued")    # queued | running | complete | error
    current_node = Column(String)
    result_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)


class ElectricityPlan(Base):
    __tablename__ = "electricity_plans"
    id = Column(Integer, primary_key=True)
    document_id = Column(String, ForeignKey("documents.document_id"))
    provider = Column(String)
    plan_name = Column(String)
    plan_type = Column(String)
    energy_rate_cents = Column(Float)
    base_charge_monthly = Column(Float)
    buyback_rate_cents = Column(Float, default=0.0)
    buyback_applies_to_tdu = Column(Boolean, default=False)  # only True if EFL proves it
    free_nights_start = Column(Integer)
    free_nights_end = Column(Integer)
    min_usage_fee = Column(Float, default=0.0)
    term_months = Column(Integer)
    efl_effective_date = Column(String)
    source_url = Column(String)


class TduCharge(Base):
    __tablename__ = "tdu_charges"
    id = Column(Integer, primary_key=True)
    tdu_name = Column(String, default="Oncor")
    fixed_monthly = Column(Float)
    volumetric_cents_per_kwh = Column(Float)
    effective_date = Column(String)
    source_doc_id = Column(String)


class BillCalculation(Base):
    __tablename__ = "bill_calculations"
    id = Column(Integer, primary_key=True)
    job_id = Column(String, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan_id = Column(Integer, ForeignKey("electricity_plans.id"))
    imported_cost = Column(Float)
    self_consumption_value = Column(Float)
    export_credit = Column(Float)
    tdu_delivery_cost = Column(Float)
    base_fee = Column(Float)
    taxes_misc = Column(Float)
    est_monthly_bill = Column(Float)
    est_annual_bill = Column(Float)
    annual_savings_vs_current = Column(Float)
    rank = Column(Integer)
    assumptions_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    job_id = Column(String, index=True)
    node = Column(String)
    tool = Column(String)
    input_hash = Column(String)
    output_summary = Column(Text)
    citations_json = Column(Text)
    ts = Column(DateTime, default=datetime.utcnow)
