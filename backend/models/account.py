from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.orm import relationship

from .base import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    account_number = Column(String(50), unique=True, nullable=False)
    customer_name = Column(String(255), nullable=False)
    risk_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    alerts = relationship("Alert", back_populates="subject_account")
    cases = relationship("Case", back_populates="subject_account")
