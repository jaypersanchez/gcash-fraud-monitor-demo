from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, Enum

from .base import Base


SEVERITY_LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


class RuleDefinition(Base):
    __tablename__ = "rule_definitions"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    cypher_query = Column(Text, nullable=True)
    severity = Column(Enum(*SEVERITY_LEVELS, name="rule_severity", create_constraint=False), nullable=False, default="HIGH")
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
