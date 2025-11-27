from datetime import datetime
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base

ACTION_VALUES = ("BLOCK_ACCOUNT", "MARK_SAFE", "ESCALATE")


class CaseAction(Base):
    __tablename__ = "case_actions"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    action = Column(Enum(*ACTION_VALUES, name="case_action", create_constraint=False), nullable=False)
    performed_by = Column(String(255), default="fraud_analyst_1", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    case = relationship("Case", back_populates="actions")
