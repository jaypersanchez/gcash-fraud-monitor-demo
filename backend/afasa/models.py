from datetime import datetime, timedelta
from sqlalchemy import (
    Column,
    Integer,
    String,
    Enum,
    DateTime,
    ForeignKey,
    Boolean,
    Numeric,
)
from sqlalchemy.orm import relationship

from backend.models.base import Base
from backend.afasa.constants import (
    REASON_CATEGORIES,
    SUSPICION_TYPES,
    DISPUTE_STATUS,
    VERIFICATION_EVENT_TYPES,
    FLAG_SOURCES,
)


def _default_now():
    return datetime.utcnow()


class AfasaDisputedTransaction(Base):
    __tablename__ = "afasa_disputed_transactions"

    id = Column(Integer, primary_key=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    original_tx_id = Column(Integer, ForeignKey("transaction_logs.id"), nullable=True)
    source_account_id = Column(String(255), nullable=False)
    beneficiary_account_id = Column(String(255), nullable=False)
    amount = Column(Numeric(18, 2), nullable=True)
    currency = Column(String(10), nullable=True)
    reason_category = Column(Enum(*REASON_CATEGORIES, name="afasa_reason_category", create_constraint=False), nullable=False)
    suspicion_type = Column(Enum(*SUSPICION_TYPES, name="afasa_suspicion_type", create_constraint=False), nullable=False)
    status = Column(Enum(*DISPUTE_STATUS, name="afasa_dispute_status", create_constraint=False), nullable=False, default="PENDING_HOLD")
    hold_start_at = Column(DateTime(timezone=True), nullable=True)
    hold_end_at = Column(DateTime(timezone=True), nullable=True)
    max_hold_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_default_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_default_now, onupdate=_default_now, nullable=False)

    verification_events = relationship(
        "AfasaVerificationEvent",
        back_populates="disputed_transaction",
        cascade="all, delete-orphan",
    )

    def start_hold(self, hold_window_days: int = 30):
        now = datetime.utcnow()
        self.hold_start_at = now
        self.max_hold_until = now + timedelta(days=hold_window_days)
        self.status = "HELD"


class AfasaVerificationEvent(Base):
    __tablename__ = "afasa_verification_events"

    id = Column(Integer, primary_key=True)
    disputed_tx_id = Column(Integer, ForeignKey("afasa_disputed_transactions.id"), nullable=False)
    event_type = Column(Enum(*VERIFICATION_EVENT_TYPES, name="afasa_verification_event", create_constraint=False), nullable=False)
    notes = Column(String, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_default_now, nullable=False)

    disputed_transaction = relationship("AfasaDisputedTransaction", back_populates="verification_events")


class AfasaMoneyMuleFlag(Base):
    __tablename__ = "afasa_money_mule_flags"

    id = Column(Integer, primary_key=True)
    account_id = Column(String(255), nullable=False)
    flag_source = Column(Enum(*FLAG_SOURCES, name="afasa_flag_source", create_constraint=False), nullable=False, default="RULE_ENGINE")
    risk_score = Column(Integer, nullable=True)
    is_confirmed = Column(Boolean, default=False, nullable=False)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_default_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_default_now, onupdate=_default_now, nullable=False)
