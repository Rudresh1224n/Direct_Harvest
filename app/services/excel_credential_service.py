import io
import os
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User, FarmerProfile, ConsumerProfile, DeliveryPartnerProfile
from app.models.wallet import Wallet
from app.utils.constants import ROLE_ADMIN, ROLE_FARMER, ROLE_CONSUMER, ROLE_DELIVERY
from app.utils.security import hash_password, verify_password
from app.utils.ist_time import get_ist_now, format_ist_datetime

logger = logging.getLogger("excel_credential_service")

# Primary and backup file paths
PRIMARY_EXCEL_PATH = settings.BASE_DIR / "users_credentials.xlsx"
DATA_EXCEL_PATH = settings.BASE_DIR / "data" / "users_credentials.xlsx"

HEADERS = [
    "User ID",
    "Full Name",
    "Email",
    "Phone",
    "Password ([Encrypted] / Edit to Update)",
    "Role",
    "Account Status",
    "District / Address",
    "Vehicle Type",
    "License Number",
    "Registration Date (IST)",
    "Last Synced (IST)",
]

# Track last modification time to avoid duplicate sync loops
_last_synced_mtime: float = 0.0


def _style_credentials_sheet(ws):
    """Apply clear professional formatting to credentials spreadsheet."""
    header_fill = PatternFill(fill_type="solid", fgColor="1B4332")  # Deep Forest Green
    header_font = Font(bold=True, color="FFFFFF", size=11)
    
    pwd_header_fill = PatternFill(fill_type="solid", fgColor="B7791F")  # Amber / Warning tone for password
    
    thin_border = Border(
        left=Side(style="thin", color="CCCCCC"),
        right=Side(style="thin", color="CCCCCC"),
        top=Side(style="thin", color="CCCCCC"),
        bottom=Side(style="thin", color="CCCCCC"),
    )

    ws.row_dimensions[1].height = 28

    for col_idx, cell in enumerate(ws[1], start=1):
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if col_idx == 5:  # Password column
            cell.fill = pwd_header_fill
            cell.font = Font(bold=True, color="FFFFFF", size=11)
        else:
            cell.fill = header_fill
            cell.font = header_font

    pwd_data_fill = PatternFill(fill_type="solid", fgColor="FEFCBF")  # Light soft yellow for password cells
    pwd_font = Font(bold=True, color="744210", size=10)

    for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        ws.row_dimensions[row_idx].height = 22
        for col_idx, cell in enumerate(row, start=1):
            cell.border = thin_border
            if col_idx == 5:  # Password column
                cell.fill = pwd_data_fill
                cell.font = pwd_font
                cell.alignment = Alignment(horizontal="left", vertical="center")
            elif col_idx in (1, 6, 7):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions

    for column in ws.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        col_letter = get_column_letter(column[0].column)
        ws.column_dimensions[col_letter].width = min(max(max_length + 4, 14), 40)


def _safe_save_workbook(wb: openpyxl.Workbook, target_path: Path):
    """Safely write workbook to disk, handling Windows file locks with fallback."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(target_path)
    except PermissionError:
        # File is currently open in Microsoft Excel on Windows.
        # Save to data backup so newly registered data is preserved.
        try:
            wb.save(DATA_EXCEL_PATH)
            logger.info(
                "Primary Excel file %s is open in Excel; saved update to backup %s.",
                target_path,
                DATA_EXCEL_PATH,
            )
        except Exception:
            pass


def _load_workbook_from_path(path: Path) -> Optional[openpyxl.Workbook]:
    """
    Safely load an Excel workbook on Windows even when Microsoft Excel has it open.
    Reads file bytes into RAM using shared read access, then parses with openpyxl in-memory.
    Retries briefly if the file is momentarily in the middle of an atomic save by Excel.
    """
    if not path.exists():
        return None
    import time
    for attempt in range(5):
        try:
            with open(path, "rb") as f:
                content = f.read()
            if len(content) > 100:
                bio = io.BytesIO(content)
                return openpyxl.load_workbook(bio, data_only=True)
        except (PermissionError, OSError, Exception) as exc:
            logger.debug("Attempt %d reading %s encountered %s; retrying in 100ms...", attempt + 1, path, exc)
            time.sleep(0.1)
    return None


class ExcelCredentialService:
    """
    Manages two-way synchronization between user credentials in the database
    and an editable Microsoft Excel spreadsheet (`users_credentials.xlsx`).
    """

    @classmethod
    def get_excel_path(cls) -> Path:
        return PRIMARY_EXCEL_PATH

    @classmethod
    def get_last_mtime(cls) -> float:
        try:
            if PRIMARY_EXCEL_PATH.exists():
                return os.path.getmtime(PRIMARY_EXCEL_PATH)
        except Exception:
            pass
        return 0.0

    @classmethod
    def initialize_or_export_all(cls, db: Session, default_admin_pwd: str = "admin123") -> Path:
        """
        Generate `users_credentials.xlsx` if missing, or sync from it if already present.
        Never blindly overwrites an existing sheet edited by the user.
        """
        global _last_synced_mtime

        # If Excel file already exists, sync its contents into DB and keep it untouched
        if PRIMARY_EXCEL_PATH.exists():
            cls.sync_excel_to_db(db, force=True)
            _last_synced_mtime = cls.get_last_mtime()
            return PRIMARY_EXCEL_PATH

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "DirectHarvest Credentials"
        ws.append(HEADERS)

        users = db.query(User).order_by(User.id).all()
        now_str = format_ist_datetime(get_ist_now())

        for u in users:
            pwd = "[Encrypted]"

            v_type = ""
            l_num = ""
            if u.role == ROLE_DELIVERY and u.delivery_profile:
                v_type = u.delivery_profile.vehicle_type or ""
                l_num = u.delivery_profile.license_number or ""

            ws.append([
                u.id,
                u.full_name or "",
                u.email or "",
                u.phone or "",
                pwd,
                u.role or "consumer",
                u.status or "Active",
                u.address or "",
                v_type,
                l_num,
                format_ist_datetime(u.created_at) if u.created_at else now_str,
                now_str,
            ])

        _style_credentials_sheet(ws)
        _safe_save_workbook(wb, PRIMARY_EXCEL_PATH)

        try:
            DATA_EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PRIMARY_EXCEL_PATH, DATA_EXCEL_PATH)
        except Exception:
            pass

        _last_synced_mtime = cls.get_last_mtime()
        logger.info("Initialized credentials Excel with %d users at %s", len(users), PRIMARY_EXCEL_PATH)
        return PRIMARY_EXCEL_PATH

    @classmethod
    def record_user_registration(
        cls,
        user: User,
        raw_password: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        license_number: Optional[str] = None,
    ):
        """
        Automatically append or update user credentials in `users_credentials.xlsx`
        immediately upon registration. Passwords are never saved in plaintext.
        """
        global _last_synced_mtime
        try:
            if not PRIMARY_EXCEL_PATH.exists():
                from app.database import SessionLocal
                with SessionLocal() as db:
                    cls.initialize_or_export_all(db)

            wb = _load_workbook_from_path(PRIMARY_EXCEL_PATH)
            if wb is None:
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "DirectHarvest Credentials"
                ws.append(HEADERS)
            else:
                ws = wb.active

            now_str = format_ist_datetime(get_ist_now())
            user_id = user.id
            found = False

            # Check if row already exists for this user ID
            for row in ws.iter_rows(min_row=2):
                cell_id = row[0].value
                try:
                    if cell_id and int(cell_id) == user_id:
                        row[1].value = user.full_name
                        row[2].value = user.email
                        row[3].value = user.phone or ""
                        row[4].value = "[Encrypted]"  # Never store plaintext password
                        row[5].value = user.role
                        row[6].value = user.status
                        row[7].value = user.address or ""
                        row[8].value = vehicle_type or ""
                        row[9].value = license_number or ""
                        row[11].value = now_str
                        found = True
                        break
                except Exception:
                    pass

            if not found:
                ws.append([
                    user.id,
                    user.full_name,
                    user.email,
                    user.phone or "",
                    "[Encrypted]",  # Never store plaintext password
                    user.role,
                    user.status,
                    user.address or "",
                    vehicle_type or "",
                    license_number or "",
                    format_ist_datetime(user.created_at) if user.created_at else now_str,
                    now_str,
                ])

            _style_credentials_sheet(ws)
            _safe_save_workbook(wb, PRIMARY_EXCEL_PATH)

            try:
                DATA_EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(PRIMARY_EXCEL_PATH, DATA_EXCEL_PATH)
            except Exception:
                pass

            _last_synced_mtime = cls.get_last_mtime()
            logger.info("Recorded registration in Excel for user %s (%s)", user.email, user.role)

        except Exception:
            logger.exception("Error recording user registration in Excel credentials file.")

    @classmethod
    def _sync_worksheet_to_db(cls, ws, db: Session) -> Dict[str, Any]:
        """Core row-by-row synchronization engine between worksheet and database."""
        updated_count = 0
        created_count = 0
        errors: List[str] = []
        now_str = format_ist_datetime(get_ist_now())

        seen_user_ids = set()
        seen_emails = set()

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not any(row):
                continue

            raw_id = row[0]
            name = str(row[1] or "").strip()
            email = str(row[2] or "").strip().lower()
            phone = str(row[3] or "").strip()
            password_val = str(row[4] or "").strip() if row[4] is not None else ""
            role_val = str(row[5] or "").strip().lower()
            status_val = str(row[6] or "").strip()
            address_val = str(row[7] or "").strip()
            vehicle_val = str(row[8] or "").strip() if len(row) > 8 and row[8] else ""
            license_val = str(row[9] or "").strip() if len(row) > 9 and row[9] else ""

            if not email and not phone:
                continue

            if raw_id:
                try:
                    seen_user_ids.add(int(raw_id))
                except Exception:
                    pass
            if email:
                seen_emails.add(email)

            # Clean phone
            clean_phone_val = "".join(ch for ch in phone if ch.isdigit())
            if len(clean_phone_val) >= 10:
                clean_phone_val = clean_phone_val[-10:]

            # Normalize role
            if role_val not in (ROLE_ADMIN, ROLE_FARMER, ROLE_CONSUMER, ROLE_DELIVERY):
                role_val = ROLE_CONSUMER

            # Match user by ID or by email
            user = None
            if raw_id:
                try:
                    u_id = int(raw_id)
                    user = db.query(User).filter(User.id == u_id).first()
                except Exception:
                    pass

            if not user and email:
                user = db.query(User).filter(User.email == email).first()

            if user:
                seen_user_ids.add(user.id)
                if user.email:
                    seen_emails.add(user.email.lower())
                changed = False

                # 1. Password change
                if password_val and password_val != "[Encrypted]" and len(password_val) >= 4:
                    if not verify_password(password_val, user.password_hash):
                        user.password_hash = hash_password(password_val)
                        changed = True
                        logger.info("Updated password for user %s via Excel sync.", user.email)

                # 2. Email change
                if email and user.email != email:
                    conflict = db.query(User).filter(User.email == email, User.id != user.id).first()
                    if not conflict:
                        user.email = email
                        changed = True
                    else:
                        errors.append(f"Row {row_idx}: Email '{email}' conflicts with another user.")

                # 3. Name change
                if name and user.full_name != name:
                    user.full_name = name
                    changed = True

                # 4. Phone change
                if clean_phone_val and user.phone != clean_phone_val:
                    user.phone = clean_phone_val
                    changed = True

                # 5. Status change
                if status_val and status_val.capitalize() in ("Active", "Inactive", "Suspended"):
                    normalized_status = status_val.capitalize()
                    if user.status != normalized_status:
                        user.status = normalized_status
                        changed = True

                # 6. Address change
                if address_val and user.address != address_val:
                    user.address = address_val
                    changed = True

                # 7. Role change
                if role_val and user.role != role_val:
                    user.role = role_val
                    changed = True
                    if role_val == ROLE_FARMER:
                        if not user.farmer_profile:
                            db.add(FarmerProfile(farmer_id=user.id, trust_score=5.0))
                        if not user.wallet:
                            db.add(Wallet(user_id=user.id, available_balance=0.0))
                    elif role_val == ROLE_CONSUMER:
                        if not user.consumer_profile:
                            db.add(ConsumerProfile(consumer_id=user.id))
                    elif role_val == ROLE_DELIVERY:
                        if not user.delivery_profile:
                            db.add(DeliveryPartnerProfile(delivery_id=user.id, vehicle_type=vehicle_val or "Bike", license_number=license_val or None))

                # Delivery partner vehicle/license
                if user.role == ROLE_DELIVERY and user.delivery_profile:
                    if vehicle_val and user.delivery_profile.vehicle_type != vehicle_val:
                        user.delivery_profile.vehicle_type = vehicle_val
                        changed = True
                    if license_val and user.delivery_profile.license_number != license_val:
                        user.delivery_profile.license_number = license_val
                        changed = True

                if changed:
                    updated_count += 1

            else:
                # Brand new user created in Excel directly!
                if email:
                    conflict = db.query(User).filter(User.email == email).first()
                    if not conflict:
                        try:
                            final_pwd = password_val if (password_val and password_val != "[Encrypted]" and len(password_val) >= 4) else "password123"
                            new_u = User(
                                full_name=name or "Excel Registered User",
                                email=email,
                                phone=clean_phone_val or None,
                                password_hash=hash_password(final_pwd),
                                role=role_val,
                                address=address_val or "Bhopal, Madhya Pradesh",
                                status=status_val.capitalize() if status_val else "Active",
                            )
                            db.add(new_u)
                            db.flush()

                            if role_val == ROLE_FARMER:
                                db.add(FarmerProfile(farmer_id=new_u.id, trust_score=5.0))
                                db.add(Wallet(user_id=new_u.id, available_balance=0.0))
                            elif role_val == ROLE_CONSUMER:
                                db.add(ConsumerProfile(consumer_id=new_u.id))
                            elif role_val == ROLE_DELIVERY:
                                db.add(DeliveryPartnerProfile(delivery_id=new_u.id, vehicle_type=vehicle_val or "Bike", license_number=license_val or None))

                            seen_user_ids.add(new_u.id)
                            seen_emails.add(new_u.email.lower())
                            created_count += 1
                            logger.info("Created new user %s (%s) from Excel row %d.", email, role_val, row_idx)
                        except Exception as exc:
                            errors.append(f"Row {row_idx}: Failed to insert user ({str(exc)})")
                    else:
                        errors.append(f"Row {row_idx}: Email '{email}' already registered.")
                else:
                    errors.append(f"Row {row_idx}: Missing required email or valid password for new user.")

        # Deletion synchronization: purge DB users removed from the spreadsheet
        deleted_count = 0
        if seen_user_ids or seen_emails:
            from app.routes.admin_routes import safely_delete_user
            db_users = db.query(User).all()
            absent_user_ids = [
                u.id for u in db_users
                if u.id != 1
                and (u.role or "").lower() != ROLE_ADMIN
                and (u.email or "").lower() != "admin@directharvest.com"
                and not (u.email or "").lower().endswith("@directharvest.com")
                and u.id not in seen_user_ids
                and (u.email or "").lower() not in seen_emails
            ]
            for uid in absent_user_ids:
                user_obj = db.query(User).filter(User.id == uid).first()
                user_ident = user_obj.email if user_obj else f"ID {uid}"
                logger.info("User %s deleted from Excel. Purging from database...", user_ident)
                success, msg = safely_delete_user(db, uid, current_admin_id=-1)
                if success:
                    deleted_count += 1
                else:
                    errors.append(f"Failed to delete absent user {user_ident}: {msg}")

        if updated_count > 0 or created_count > 0:
            db.commit()
            logger.info("Excel sync committed: %d updated, %d created.", updated_count, created_count)

        if deleted_count > 0:
            logger.info("Excel sync committed: %d absent user(s) purged.", deleted_count)

        return {
            "success": True,
            "updated": updated_count,
            "created": created_count,
            "deleted": deleted_count,
            "errors": errors,
            "timestamp": now_str,
        }

    @classmethod
    def sync_bytes_to_db(cls, content: bytes, db: Session) -> Dict[str, Any]:
        """Synchronize an Excel file from in-memory bytes directly into the database."""
        try:
            bio = io.BytesIO(content)
            wb = openpyxl.load_workbook(bio, data_only=True)
            res = cls._sync_worksheet_to_db(wb.active, db)
            return res
        except Exception as exc:
            logger.exception("Failed to parse Excel from bytes: %s", exc)
            return {"updated": 0, "created": 0, "errors": [str(exc)], "success": False}

    @classmethod
    def sync_excel_to_db(cls, db: Session, force: bool = False) -> Dict[str, Any]:
        """
        Synchronize changes from `users_credentials.xlsx` into the database:
        - If password is typed/edited, hashes it with bcrypt and updates user.
        - If email, phone, name, role, status, or address are edited, updates user.
        - If a new row is added directly into Excel, creates that user in the database.
        """
        global _last_synced_mtime

        if not PRIMARY_EXCEL_PATH.exists():
            cls.initialize_or_export_all(db)
            return {"updated": 0, "created": 0, "errors": [], "message": "Excel initialized"}

        current_mtime = cls.get_last_mtime()
        if not force and current_mtime <= _last_synced_mtime and _last_synced_mtime > 0:
            return {"updated": 0, "created": 0, "errors": [], "skipped": True}

        logger.info("Detected change in %s (mtime: %s). Syncing to DB...", PRIMARY_EXCEL_PATH, current_mtime)

        # Load workbook in-memory safely (works on Windows even when Excel has file open)
        wb = _load_workbook_from_path(PRIMARY_EXCEL_PATH)
        if wb is None:
            logger.warning("Could not read %s (temporarily locked or being saved). Will retry.", PRIMARY_EXCEL_PATH)
            return {"updated": 0, "created": 0, "errors": ["File temporarily locked"], "skipped": True}

        res = cls._sync_worksheet_to_db(wb.active, db)
        _last_synced_mtime = cls.get_last_mtime()
        return res
    @classmethod
    def check_and_sync_if_modified(cls, db: Session) -> bool:
        """Lightweight check called by background monitor or web requests."""
        if not PRIMARY_EXCEL_PATH.exists():
            return False
        current_mtime = cls.get_last_mtime()
        if current_mtime > _last_synced_mtime:
            res = cls.sync_excel_to_db(db)
            return bool(res.get("updated") or res.get("created") or res.get("deleted"))
        return False

