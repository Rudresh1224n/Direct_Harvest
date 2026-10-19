from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.ist_time import get_ist_now

class Wallet(Base):
    __tablename__ = "farmer_wallets"

    wallet_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    available_balance = Column(Float, default=0.0, nullable=False)
    pending_amount = Column(Float, default=0.0, nullable=False)
    withdrawn_amount = Column(Float, default=0.0, nullable=False)
    total_earnings = Column(Float, default=0.0, nullable=False)
    updated_at = Column(DateTime, default=get_ist_now, onupdate=get_ist_now, nullable=False)

    __table_args__ = (
        CheckConstraint("available_balance >= 0", name="chk_wallet_positive_balance"),
    )

    user = relationship("User", back_populates="wallet")
    transactions = relationship("WalletTransaction", back_populates="wallet", cascade="all, delete-orphan")


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_id = Column(Integer, ForeignKey("farmer_wallets.wallet_id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.order_id", ondelete="SET NULL"), nullable=True)
    amount = Column(Float, nullable=False)
    transaction_type = Column(String(20), nullable=False)  # credit, debit, withdrawal, refund
    description = Column(Text, nullable=True)
    status = Column(String(20), default="Completed", nullable=False)
    created_at = Column(DateTime, default=get_ist_now, nullable=False)

    wallet = relationship("Wallet", back_populates="transactions")
    order = relationship("Order")
