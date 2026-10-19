from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.ist_time import get_ist_now

class WhatsAppLog(Base):
    __tablename__ = "whatsapp_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, nullable=True, index=True)
    recipient_role = Column(String(20), nullable=False)  # consumer, farmer, delivery
    recipient_phone = Column(String(25), nullable=False)
    message_type = Column(String(50), nullable=False)   # order_confirmation, new_order_alert, delivery_assignment
    message_body = Column(Text, nullable=False)
    send_mode = Column(String(30), nullable=False)       # simulated, live_cloud_api, twilio
    status = Column(String(20), nullable=False)          # Simulated, Sent, Failed
    provider_response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_ist_now, nullable=False)


class AdminActivityLog(Base):
    __tablename__ = "admin_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    target_type = Column(String(50), nullable=True)
    target_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_ist_now, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=get_ist_now, nullable=False)

    user = relationship("User", back_populates="notifications")


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
