from datetime import datetime
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from .base import Base
from .rule_definition import RuleDefinition, SEVERITY_LEVELS

STATUS_VALUES = ("OPEN", "IN_PROGRESS", "RESOLVED")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey("rule_definitions.id"), nullable=False)
    subject_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    severity = Column(Enum(*SEVERITY_LEVELS, name="alert_severity", create_constraint=False), nullable=False, default="MEDIUM")
    status = Column(Enum(*STATUS_VALUES, name="alert_status", create_constraint=False), nullable=False, default="OPEN")
    summary = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    rule = relationship(RuleDefinition)
    subject_account = relationship("Account", back_populates="alerts")
    case = relationship("Case", uselist=False, back_populates="alert")
