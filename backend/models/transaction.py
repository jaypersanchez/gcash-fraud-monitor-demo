from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Numeric

from .base import Base


class TransactionLog(Base):
    __tablename__ = "transaction_logs"

    id = Column(Integer, primary_key=True)
    tx_reference = Column(String(100), unique=True, nullable=False)
    sender_account_id = Column(String(255), nullable=False)
    receiver_account_id = Column(String(255), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(10), nullable=True)
    tx_datetime = Column(DateTime(timezone=True), nullable=False)
    ofi = Column(String(255), nullable=True)
    rfi = Column(String(255), nullable=True)
    channel = Column(String(50), nullable=True)
    auth_method = Column(String(50), nullable=True)
    device_fingerprint = Column(String(255), nullable=True)
    device_details = Column(String, nullable=True)
    ip_address = Column(String(100), nullable=True)
    browser_user_agent = Column(String, nullable=True)
    non_financial_action = Column(String(100), nullable=True)
    network_reference = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
