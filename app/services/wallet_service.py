
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.wallet import Wallet, WalletTransaction


class WalletService:
    @staticmethod
    def get_or_create_wallet(
        db: Session, user_id: int, commit: bool = True
    ) -> Wallet:
        wallet = (
            db.query(Wallet)
            .filter(Wallet.user_id == user_id)
            .with_for_update()
            .first()
        )

        if wallet is None:
            wallet = Wallet(
                user_id=user_id,
                available_balance=0.0,
                pending_amount=0.0,
                withdrawn_amount=0.0,
                total_earnings=0.0,
            )
            db.add(wallet)
            db.flush()

            if commit:
                db.commit()
                db.refresh(wallet)

        return wallet

    @staticmethod
    def credit_pending(
        db: Session,
        user_id: int,
        order_id: int,
        amount: float,
        description: str = "",
        commit: bool = True,
    ) -> Wallet:
        if amount < 0:
            raise ValueError("Amount cannot be negative.")

        wallet = WalletService.get_or_create_wallet(
            db, user_id, commit=False
        )

        existing = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.wallet_id == wallet.wallet_id,
                WalletTransaction.order_id == order_id,
                WalletTransaction.transaction_type == "credit",
            )
            .first()
        )

        if existing is not None:
            if existing.status == "Cancelled":
                raise ValueError(
                    "This order's wallet credit has already been cancelled."
                )
            return wallet

        wallet.pending_amount += amount

        db.add(
            WalletTransaction(
                wallet_id=wallet.wallet_id,
                order_id=order_id,
                amount=amount,
                transaction_type="credit",
                description=(
                    description or f"Pending earnings for Order #{order_id}"
                ),
                status="Pending",
            )
        )

        if commit:
            db.commit()
            db.refresh(wallet)
        else:
            db.flush()

        return wallet

    @staticmethod
    def settle_delivered_order(
        db: Session,
        user_id: int,
        order_id: int,
        amount: float,
        commit: bool = True,
    ) -> Wallet:
        if amount < 0:
            raise ValueError("Amount cannot be negative.")

        wallet = WalletService.get_or_create_wallet(
            db, user_id, commit=False
        )

        tx = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.wallet_id == wallet.wallet_id,
                WalletTransaction.order_id == order_id,
                WalletTransaction.transaction_type == "credit",
            )
            .with_for_update()
            .first()
        )

        # Do not pay an order twice.
        if tx and tx.status == "Completed":
            return wallet

        if tx and tx.status == "Cancelled":
            raise ValueError("A cancelled payout cannot be settled.")

        if tx:
            wallet.pending_amount = max(
                0.0, wallet.pending_amount - tx.amount
            )
            tx.status = "Completed"
            tx.description = f"Completed payout for Order #{order_id}"
        else:
            # Supports older orders without a pending transaction.
            tx = WalletTransaction(
                wallet_id=wallet.wallet_id,
                order_id=order_id,
                amount=amount,
                transaction_type="credit",
                description=f"Completed payout for Order #{order_id}",
                status="Completed",
            )
            db.add(tx)

        wallet.available_balance += amount
        wallet.total_earnings += amount

        if commit:
            db.commit()
            db.refresh(wallet)
        else:
            db.flush()

        return wallet

    @staticmethod
    def cancel_order_pending(
        db: Session,
        user_id: int,
        order_id: int,
        amount: float,
        commit: bool = True,
    ) -> Wallet:
        wallet = WalletService.get_or_create_wallet(
            db, user_id, commit=False
        )

        tx = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.wallet_id == wallet.wallet_id,
                WalletTransaction.order_id == order_id,
                WalletTransaction.transaction_type == "credit",
            )
            .with_for_update()
            .first()
        )

        # Repeated cancellation must not deduct pending earnings twice.
        if tx is None or tx.status == "Cancelled":
            return wallet

        if tx.status == "Completed":
            raise ValueError(
                "A completed payout cannot be cancelled as pending."
            )

        wallet.pending_amount = max(
            0.0, wallet.pending_amount - tx.amount
        )
        tx.status = "Cancelled"
        tx.description = f"Order #{order_id} cancelled; payout reverted"

        if commit:
            db.commit()
            db.refresh(wallet)
        else:
            db.flush()

        return wallet

    @staticmethod
    def withdraw_funds(
        db: Session, user_id: int, amount: float
    ) -> Dict[str, Any]:
        if amount <= 0:
            return {
                "success": False,
                "message": "Amount must be greater than zero.",
            }

        wallet = WalletService.get_or_create_wallet(db, user_id)

        if wallet.available_balance < amount:
            return {
                "success": False,
                "message": (
                    "Insufficient balance. Available: "
                    f"₹{wallet.available_balance:.2f}"
                ),
            }

        wallet.available_balance -= amount
        wallet.withdrawn_amount += amount

        db.add(
            WalletTransaction(
                wallet_id=wallet.wallet_id,
                amount=amount,
                transaction_type="withdrawal",
                description=(
                    f"Simulated bank transfer withdrawal of ₹{amount:.2f}"
                ),
                status="Completed",
            )
        )

        db.commit()
        db.refresh(wallet)

        return {
            "success": True,
            "message": (
                f"Withdrawal of ₹{amount:.2f} processed in Demo Mode."
            ),
            "new_balance": wallet.available_balance,
        }
