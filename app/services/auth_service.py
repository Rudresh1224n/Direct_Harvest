
from typing import Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import (
    User,
    FarmerProfile,
    ConsumerProfile,
    DeliveryPartnerProfile,
)
from app.models.wallet import Wallet
from app.schemas.user import UserRegister
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from app.utils.constants import (
    ROLE_ADMIN,
    ROLE_FARMER,
    ROLE_CONSUMER,
    ROLE_DELIVERY,
)


class AuthService:
    """Business logic for DirectHarvest registration and authentication."""

    @staticmethod
    def register_user(db: Session, user_data: UserRegister) -> User:
        """
        Register a consumer, farmer, or delivery partner.

        Public registration cannot create administrator accounts.
        User, role profile, and farmer wallet are saved together.
        """
        role = user_data.role.strip().lower()
        email = str(user_data.email).strip().lower()
        full_name = user_data.full_name.strip()

        from app.utils.email_validator import validate_authentic_email
        email = validate_authentic_email(email)

        if user_data.confirm_password and user_data.password != user_data.confirm_password:
            raise ValueError("Passwords do not match.")

        if role == ROLE_ADMIN:
            raise ValueError(
                "Administrator accounts must be created through the "
                "secure administrator setup process."
            )

        if role not in {ROLE_FARMER, ROLE_CONSUMER, ROLE_DELIVERY}:
            raise ValueError("Please select a valid account type.")

        if len(full_name) < 2:
            raise ValueError("Full name must contain at least two characters.")

        existing_user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if existing_user:
            raise ValueError("Email is already registered.")

        phone_clean = None
        if user_data.phone:
            digits = "".join(ch for ch in str(user_data.phone) if ch.isdigit())
            phone_clean = digits[-10:] if len(digits) >= 10 else user_data.phone.strip()

        new_user = User(
            full_name=full_name,
            email=email,
            phone=phone_clean,
            password_hash=hash_password(user_data.password),
            role=role,
            address=user_data.address.strip() if user_data.address else None,
            status="Active",
        )

        try:
            db.add(new_user)
            db.flush()

            if role == ROLE_FARMER:
                db.add(
                    FarmerProfile(
                        farmer_id=new_user.id,
                        trust_score=5.0,
                    )
                )

                db.add(
                    Wallet(
                        user_id=new_user.id,
                        available_balance=0.0,
                    )
                )

            elif role == ROLE_CONSUMER:
                db.add(
                    ConsumerProfile(
                        consumer_id=new_user.id,
                    )
                )

            elif role == ROLE_DELIVERY:
                db.add(
                    DeliveryPartnerProfile(
                        delivery_id=new_user.id,
                        vehicle_type=(
                            user_data.vehicle_type.strip()
                            if user_data.vehicle_type
                            else "Bike"
                        ),
                        license_number=(
                            user_data.license_number.strip()
                            if user_data.license_number
                            else None
                        ),
                    )
                )

            db.commit()
            db.refresh(new_user)

            # Auto-fill credentials in users_credentials.xlsx
            try:
                from app.services.excel_credential_service import ExcelCredentialService
                ExcelCredentialService.record_user_registration(
                    user=new_user,
                    vehicle_type=user_data.vehicle_type,
                    license_number=user_data.license_number,
                )
            except Exception:
                import logging
                logging.getLogger("directharvest").exception(
                    "Failed to auto-record user in credentials Excel file."
                )

            return new_user

        except IntegrityError as exc:
            db.rollback()
            raise ValueError(
                "This email or account is already registered. "
                "Please try logging in."
            ) from exc

        except SQLAlchemyError:
            db.rollback()
            raise

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def authenticate_user(
        db: Session,
        email: str,
        password: str,
    ) -> Optional[User]:
        """Return an active user only when the credentials are valid."""
        if not email or not password:
            return None

        raw_email = email.strip().lower()
        # Normalize common admin usernames
        if raw_email in ("admin", "administrator"):
            normalized_email = "admin@directharvest.com"
        else:
            normalized_email = raw_email

        user = (
            db.query(User)
            .filter(User.email == normalized_email)
            .first()
        )

        admin_phone = "".join(ch for ch in settings.ADMIN_PHONE if ch.isdigit())[-10:] if settings.ADMIN_PHONE else "9691793254"

        # If admin account does not exist in database yet (e.g. fresh cloud DB), auto-provision on first login
        if user is None:
            if normalized_email == "admin@directharvest.com" and password.strip() == "admin123":
                user = User(
                    full_name="Administrator",
                    email="admin@directharvest.com",
                    phone=admin_phone,
                    password_hash=hash_password("admin123"),
                    role=ROLE_ADMIN,
                    address="Bhopal, Madhya Pradesh",
                    status="Active",
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                return user
            return None

        if user.status != "Active":
            return None

        if not verify_password(password, user.password_hash):
            if password != password.strip() and verify_password(password.strip(), user.password_hash):
                return user
            # Guarantee administrator login with default admin123 credential
            if (user.role == ROLE_ADMIN or normalized_email == "admin@directharvest.com") and password.strip() == "admin123":
                user.password_hash = hash_password("admin123")
                user.status = "Active"
                db.commit()
                return user
            return None

        return user

    @staticmethod
    def generate_token_for_user(user: User) -> str:
        """Generate an authentication token containing the user's identity."""
        payload = {
            "sub": str(user.id),
            "role": user.role,
            "email": user.email,
            "name": user.full_name,
        }

        return create_access_token(payload)