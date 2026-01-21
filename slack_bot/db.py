import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from shared.models import Base, Issue, Event, Participant, Program

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
            root_thread_id=f"{channel_id}:{thread_ts}"
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


def get_issue_by_thread_id(thread_ts: str, channel_id: str = None) -> Optional[Issue]:
    db = get_db()
    try:
        from sqlalchemy.orm import joinedload
        
        if channel_id:
            # New format: channel:thread_ts
            query_thread_id = f"{channel_id}:{thread_ts}"
            issue = db.query(Issue).options(joinedload(Issue.program)).filter(
                Issue.root_thread_id == query_thread_id,
                Issue.deleted_at.is_(None)
            ).first()
        else:
            # Try both formats for backward compatibility
            issue = db.query(Issue).options(joinedload(Issue.program)).filter(
                (Issue.root_thread_id == thread_ts) | (Issue.root_thread_id.like(f"%:{thread_ts}")),
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
            
            issue.description = "\n".join(description_parts) # type: ignore
        
        db.add(issue)
        db.commit()
        db.refresh(issue)
        return issue
    finally:
        db.close()


def create_program(program_id: str, program_name: str, description: Optional[str] = None) -> Program:
    """Create a new program in the database"""
    db = get_db()
    try:
        program = Program(
            program_id=program_id,
            name=program_name,
            description=description,
            owners=[],
            channels=[]
        )
        db.add(program)
        db.commit()
        db.refresh(program)
        return program
    finally:
        db.close()


def get_program(program_id: str) -> Optional[Program]:
    """Get a program by program_id"""
    db = get_db()
    try:
        program = db.query(Program).filter(
            Program.program_id == program_id,
            Program.deleted_at.is_(None)
        ).first()
        return program
    finally:
        db.close()


def get_program_by_channel(channel_id: str) -> Optional[Program]:
    """Get a program by channel_id"""
    db = get_db()
    try:
        from sqlalchemy import and_
        program = db.query(Program).filter(
            and_(
                Program.channels.contains([channel_id]),
                Program.deleted_at.is_(None)
            )
        ).first()
        return program
    finally:
        db.close()


def add_channel_to_program(program_id: str, channel_id: str) -> Optional[Program]:
    """Add a channel to a program"""
    db = get_db()
    try:
        program = db.query(Program).filter(
            Program.program_id == program_id,
            Program.deleted_at.is_(None)
        ).first()
        
        if program:
            if channel_id not in program.channels:
                program.channels.append(channel_id)
                db.add(program)
                db.commit()
                db.refresh(program)
        return program
    finally:
        db.close()


def add_program_owner(program_id: str, user_id: str) -> Optional[Program]:
    """Add an owner to a program"""
    db = get_db()
    try:
        program = db.query(Program).filter(
            Program.program_id == program_id,
            Program.deleted_at.is_(None)
        ).first()
        
        if program:
            if user_id not in program.owners:
                program.owners.append(user_id)
                db.add(program)
                db.commit()
                db.refresh(program)
        return program
    finally:
        db.close()


def remove_program_owner(program_id: str, user_id: str) -> Optional[Program]:
    """Remove an owner from a program"""
    db = get_db()
    try:
        program = db.query(Program).filter(
            Program.program_id == program_id,
            Program.deleted_at.is_(None)
        ).first()
        
        if program and user_id in program.owners:
            program.owners.remove(user_id)
            db.add(program)
            db.commit()
            db.refresh(program)
        return program
    finally:
        db.close()


def get_all_programs() -> List[Program]:
    """Get all programs"""
    db = get_db()
    try:
        programs = db.query(Program).filter(
            Program.deleted_at.is_(None)
        ).all()
        return programs
    finally:
        db.close()


def link_issue_to_program(issue_id: str, program_id: str) -> Optional[Issue]:
    """Link an issue to a program"""
    db = get_db()
    try:
        program = db.query(Program).filter(
            Program.program_id == program_id,
            Program.deleted_at.is_(None)
        ).first()
        
        if not program:
            return None
        
        issue = db.query(Issue).filter(Issue.id == issue_id).first()
        if issue:
            issue.program_id = program.id
            db.add(issue)
            db.commit()
            db.refresh(issue)
        return issue
    finally:
        db.close()


# Issue Owner Management
issue_owners = {}  # Maps issue_id -> set of owner user_ids

def set_issue_owner(issue_id: str, user_id: str):
    """Set a user as owner of an issue"""
    if issue_id not in issue_owners:
        issue_owners[issue_id] = set()
    issue_owners[issue_id].add(user_id)


def remove_issue_owner(issue_id: str, user_id: str):
    """Remove a user as owner of an issue"""
    if issue_id in issue_owners:
        issue_owners[issue_id].discard(user_id)


def is_issue_owner(issue_id: str, user_id: str) -> bool:
    """Check if a user is an owner of an issue"""
    return user_id in issue_owners.get(issue_id, set())


# Channel Owner Management
channel_owners = {}  # Maps channel_id -> set of owner user_ids

def set_channel_owner(channel_id: str, user_id: str):
    """Set a user as owner of a channel"""
    if channel_id not in channel_owners:
        channel_owners[channel_id] = set()
    channel_owners[channel_id].add(user_id)


def remove_channel_owner(channel_id: str, user_id: str):
    """Remove a user as owner of a channel"""
    if channel_id in channel_owners:
        channel_owners[channel_id].discard(user_id)


def is_channel_owner(channel_id: str, user_id: str) -> bool:
    """Check if a user is an owner of a channel"""
    return user_id in channel_owners.get(channel_id, set())


def get_issue_by_id(issue_id: str) -> Optional[Issue]:
    """Get an issue by its ID"""
    db = get_db()
    try:
        from sqlalchemy.orm import joinedload
        issue = db.query(Issue).options(joinedload(Issue.program)).filter(Issue.id == issue_id).first()
        return issue
    finally:
        db.close()


def get_issue_with_program(issue_id: str) -> Optional[dict]:
    """Get issue data with program info - safe to use after session closes"""
    db = get_db()
    try:
        from sqlalchemy.orm import joinedload
        issue = db.query(Issue).options(joinedload(Issue.program)).filter(Issue.id == issue_id).first()
        if not issue:
            return None
        
        program_info = None
        if issue.program:
            program_info = {
                "id": str(issue.program.id),
                "program_id": issue.program.program_id,
                "name": issue.program.name,
                "owners": issue.program.owners if issue.program.owners else []
            }
        
        return {
            "id": str(issue.id),
            "title": issue.title,
            "description": issue.description,
            "status": issue.status,
            "program": program_info
        }
    finally:
        db.close()

