from datetime import datetime
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import relationship

from .base import Base
from .alert import STATUS_VALUES


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), unique=True, nullable=False)
    subject_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    status = Column(Enum(*STATUS_VALUES, name="case_status", create_constraint=False), nullable=False, default="OPEN")
    network_summary = Column(Text, nullable=True)
    linked_accounts = Column(JSON, nullable=True)
    linked_devices = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    alert = relationship("Alert", back_populates="case")
    actions = relationship("CaseAction", back_populates="case", cascade="all, delete-orphan")
    subject_account = relationship("Account", back_populates="cases")
