from datetime import datetime
from sqlalchemy import Column, DateTime, Enum, Integer, String, Text

from .base import Base


class InvestigatorAction(Base):
    __tablename__ = "investigator_actions"

    id = Column(Integer, primary_key=True)
    anchor_id = Column(String(255), nullable=False)
    anchor_type = Column(Enum("ACCOUNT", "DEVICE", name="anchor_type", create_constraint=False), nullable=False)
    action = Column(String(50), nullable=False)
    status = Column(String(50), nullable=True)
    note = Column(Text, nullable=True)
    rule_key = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
