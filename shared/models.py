from sqlalchemy import Column, String, Text, Integer, ForeignKey, TIMESTAMP, Boolean, func, JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, CHAR
import uuid

class UUID(TypeDecorator):
    impl = CHAR
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            return str(value) if isinstance(value, uuid.UUID) else value
    
    def process_result_value(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            return uuid.UUID(value) if isinstance(value, str) else value

Base = declarative_base()


class Issue(Base):
    __tablename__ = "issues"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(), ForeignKey("programs.id", ondelete="SET NULL"), nullable=True)
    title = Column(Text)
    description = Column(Text)
    status = Column(String(20), default="unverified")
    priority = Column(String(20), default="low")
    source = Column(String(20))
    root_thread_id = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)
    events = relationship("Event", back_populates="issue", cascade="all, delete-orphan")
    participants = relationship("Participant", back_populates="issue", cascade="all, delete-orphan")
    issue_tags = relationship("IssueTag", back_populates="issue", cascade="all, delete-orphan")
    status_changes = relationship("IssueStatusChange", back_populates="issue", cascade="all, delete-orphan")
    outbound_webhooks = relationship("OutboundWebhook", back_populates="issue", cascade="all, delete-orphan")
    program = relationship("Program", back_populates="issues")


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    issue_id = Column(UUID(), ForeignKey("issues.id", ondelete="CASCADE"))
    source = Column(String(20), nullable=False)
    external_id = Column(Text)
    author = Column(Text)
    body = Column(Text)
    event_type = Column(String(50))
    ai_metadata = Column(JSON, default={})
    attachments = Column(JSON, default=[])
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)

    issue = relationship("Issue", back_populates="events")
    ai_jobs = relationship("AIJob", back_populates="event", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    name = Column(Text, unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)

    issue_tags = relationship("IssueTag", back_populates="tag", cascade="all, delete-orphan")


class IssueTag(Base):
    __tablename__ = "issue_tags"

    issue_id = Column(UUID(), ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(UUID(), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    source = Column(String(20))
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)

    issue = relationship("Issue", back_populates="issue_tags")
    tag = relationship("Tag", back_populates="issue_tags")


class Participant(Base):
    __tablename__ = "participants"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    issue_id = Column(UUID(), ForeignKey("issues.id", ondelete="CASCADE"))
    name = Column(Text)
    email = Column(Text)
    slack_user_id = Column(Text)
    role = Column(String(20))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)

    issue = relationship("Issue", back_populates="participants")


class IssueStatusChange(Base):
    __tablename__ = "issue_status_changes"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    issue_id = Column(UUID(), ForeignKey("issues.id", ondelete="CASCADE"))
    old_status = Column(String(20))
    new_status = Column(String(20))
    changed_by = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)

    issue = relationship("Issue", back_populates="status_changes")


class OutboundWebhook(Base):
    __tablename__ = "outbound_webhooks"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    issue_id = Column(UUID(), ForeignKey("issues.id", ondelete="CASCADE"))
    webhook_url = Column(Text, nullable=False)
    payload = Column(JSON)
    status = Column(String(20), default="pending")
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(TIMESTAMP(timezone=True))
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)

    issue = relationship("Issue", back_populates="outbound_webhooks")


class Program(Base):
    __tablename__ = "programs"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    program_id = Column(String(255), unique=True, nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    owners = Column(JSON, default=[])  # List of owner user_ids
    channels = Column(JSON, default=[])  # List of associated channel_ids
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)

    issues = relationship("Issue", back_populates="program")


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(), ForeignKey("events.id", ondelete="CASCADE"))
    job_type = Column(String(50))
    status = Column(String(20), default="pending")
    output = Column(JSON)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    completed_at = Column(TIMESTAMP(timezone=True))
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)

    event = relationship("Event", back_populates="ai_jobs")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), unique=True, nullable=False)  # External user ID (e.g., Slack user ID)
    display_name = Column(Text, nullable=False)
    profile_picture_url = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)
