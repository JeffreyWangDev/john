import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from shared.models import Base, Issue, Event, Participant

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./test.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        db.close()
        raise e


def create_issue_from_thread(
    thread_ts: str,
    channel_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    source: str = "slack"
) -> Issue:
    db = get_db()
    try:
        issue = Issue(
            title=title or f"Issue from Slack thread {thread_ts}",
            description=description or "",
            status="unverified",
            priority="low",
            source=source,
            root_thread_id=thread_ts
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)
        return issue
    finally:
        db.close()


def get_attachment_urls(message: dict) -> list:
    attachment_urls = []
    
    if message.get("files"):
        for file in message["files"]:
            if file.get("permalink_public"):
                attachment_urls.append(file["permalink_public"])
            elif file.get("permalink"):
                attachment_urls.append(file["permalink"])
            elif file.get("url_private"):
                attachment_urls.append(file["url_private"])
    
    if message.get("attachments"):
        for attachment in message["attachments"]:
            if attachment.get("permalink"):
                attachment_urls.append(attachment["permalink"])
            elif attachment.get("image_url"):
                attachment_urls.append(attachment["image_url"])
            elif attachment.get("thumb_url"):
                attachment_urls.append(attachment["thumb_url"])
    
    return attachment_urls


def save_thread_messages_as_events(
    issue_id: str,
    messages: List[dict],
    source: str = "slack"
) -> List[Event]:
    db = get_db()
    try:
        events = []
        for msg in messages:
            attachment_urls = get_attachment_urls(msg)
            
            event = Event(
                issue_id=issue_id,
                source=source,
                external_id=msg.get("ts"),
                author=msg.get("user", msg.get("bot_id", "unknown")),
                body=msg.get("text", ""),
                event_type="message_added",
                ai_metadata={},
                attachments=attachment_urls
            )
            db.add(event)
            events.append(event)
        
        db.commit()
        for event in events:
            db.refresh(event)
        return events
    finally:
        db.close()


def add_participant(
    issue_id: str,
    slack_user_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    role: str = "requester"
) -> Participant:
    db = get_db()
    try:
        participant = Participant(
            issue_id=issue_id,
            slack_user_id=slack_user_id,
            name=name,
            email=email,
            role=role
        )
        db.add(participant)
        db.commit()
        db.refresh(participant)
        return participant
    finally:
        db.close()


def get_issue_by_thread_id(thread_ts: str) -> Optional[Issue]:
    db = get_db()
    try:
        issue = db.query(Issue).filter(
            Issue.root_thread_id == thread_ts,
            Issue.deleted_at.is_(None)
        ).first()
        return issue
    finally:
        db.close()


def get_issue_events(issue_id: str) -> List[Event]:
    db = get_db()
    try:
        events = db.query(Event).filter(
            Event.issue_id == issue_id,
            Event.deleted_at.is_(None)
        ).order_by(Event.created_at).all()
        return events
    finally:
        db.close()


def update_issue_from_ai(issue_id: str, ai_summary: dict) -> Optional[Issue]:
    db = get_db()
    try:
        issue = db.query(Issue).filter(
            Issue.id == issue_id,
            Issue.deleted_at.is_(None)
        ).first()
        
        if not issue:
            return None
        
        if ai_summary.get('main_issue'):
            issue.title = ai_summary['main_issue'][:200]
        
        if ai_summary.get('summary'):
            description_parts = [ai_summary['summary']]
            
            if ai_summary.get('key_points'):
                description_parts.append("\n\nKey Points:")
                for point in ai_summary['key_points']:
                    description_parts.append(f"• {point}")
            
            if ai_summary.get('action_items'):
                description_parts.append("\n\nAction Items:")
                for item in ai_summary['action_items']:
                    description_parts.append(f"• {item}")
            
            issue.description = "\n".join(description_parts)
        
        db.add(issue)
        db.commit()
        db.refresh(issue)
        return issue
    finally:
        db.close()
