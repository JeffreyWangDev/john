from fastapi import FastAPI, Request, HTTPException, Depends, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import Optional, List
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

from shared.models import Issue, Program, Event
from slack_bot.db import get_db
from slack_bot.permissions import Permission, has_permission, ADMIN_USERS

app = FastAPI(title="Issue Management System")

# Mount static files
app.mount("/static", StaticFiles(directory="templates/static"), name="static")

# Session middleware
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET_KEY", "your-secret-key-change-this"))

# Simple auth credentials from environment
AUTH_USERNAME = os.environ.get("WEB_USERNAME", "admin")
AUTH_PASSWORD = os.environ.get("WEB_PASSWORD", "password")

# Templates
templates = Jinja2Templates(directory="templates")


# Dependency to get current user from session
def get_current_user(request: Request):
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# Dependency to check if user is admin
def require_admin(request: Request):
    user = get_current_user(request)
    user_id = user.get('id')
    # For simple auth, admin is the authenticated user
    if user_id != AUTH_USERNAME:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - redirects to issues if logged in, otherwise shows login"""
    user = request.session.get('user')
    if user:
        return RedirectResponse(url="/issues")
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    """Show login form"""
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error
    })


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Handle login form submission"""
    if username == AUTH_USERNAME and password == AUTH_PASSWORD:
        # Store user in session
        request.session['user'] = {
            'id': username,
            'name': username,
            'email': f"{username}@example.com",
            'image': None
        }
        return RedirectResponse(url="/issues", status_code=303)
    else:
        return RedirectResponse(url="/login?error=Invalid+credentials", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    """Logout user"""
    request.session.clear()
    return RedirectResponse(url="/")


@app.get("/issues", response_class=HTMLResponse)
async def list_issues(request: Request, user: dict = Depends(get_current_user)):
    """List all issues"""
    db = get_db()
    try:
        issues = db.query(Issue).filter(Issue.deleted_at == None).order_by(Issue.created_at.desc()).all()
        return templates.TemplateResponse("issues.html", {
            "request": request,
            "issues": issues,
            "user": user
        })
    finally:
        db.close()


@app.get("/api/issues", response_class=JSONResponse)
async def get_issues_api(user: dict = Depends(get_current_user)):
    """Get all issues as JSON"""
    db = get_db()
    try:
        issues = db.query(Issue).filter(Issue.deleted_at == None).order_by(Issue.created_at.desc()).all()
        return [{
            "id": str(issue.id),
            "title": issue.title,
            "description": issue.description,
            "status": issue.status,
            "priority": issue.priority,
            "source": issue.source,
            "program_id": str(issue.program_id) if issue.program_id else None,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "updated_at": issue.updated_at.isoformat() if issue.updated_at else None
        } for issue in issues]
    finally:
        db.close()


@app.get("/api/issues/{issue_id}", response_class=JSONResponse)
async def get_issue_detail(issue_id: str, user: dict = Depends(get_current_user)):
    """Get issue detail with first 20 events"""
    db = get_db()
    try:
        issue = db.query(Issue).filter(Issue.id == issue_id, Issue.deleted_at == None).first()
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        # Get total count of events
        total_events = db.query(Event).filter(Event.issue_id == issue_id, Event.deleted_at == None).count()
        
        # Get only first 20 events
        events = db.query(Event).filter(Event.issue_id == issue_id, Event.deleted_at == None).order_by(Event.created_at).limit(20).all()
        
        # Build events
        events_data = []
        for event in events:
            events_data.append({
                "id": str(event.id),
                "author": event.author,
                "body": event.body,
                "event_type": event.event_type,
                "created_at": event.created_at.isoformat() if event.created_at else None
            })
        
        return {
            "id": str(issue.id),
            "title": issue.title,
            "description": issue.description,
            "status": issue.status,
            "priority": issue.priority,
            "source": issue.source,
            "program_id": str(issue.program_id) if issue.program_id else None,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
            "events": events_data,
            "total_events": total_events
        }
    finally:
        db.close()


@app.get("/api/issues/{issue_id}/messages", response_class=JSONResponse)
async def get_issue_messages(issue_id: str, offset: int = 0, limit: int = 20, user: dict = Depends(get_current_user)):
    """Get paginated messages for an issue"""
    db = get_db()
    try:
        # Verify issue exists
        issue = db.query(Issue).filter(Issue.id == issue_id, Issue.deleted_at == None).first()
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        # Get total count
        total_events = db.query(Event).filter(Event.issue_id == issue_id, Event.deleted_at == None).count()
        
        # Get paginated events
        events = db.query(Event).filter(Event.issue_id == issue_id, Event.deleted_at == None).order_by(Event.created_at).offset(offset).limit(limit).all()
        
        # Build events
        events_data = []
        for event in events:
            events_data.append({
                "id": str(event.id),
                "author": event.author,
                "body": event.body,
                "event_type": event.event_type,
                "created_at": event.created_at.isoformat() if event.created_at else None
            })
        
        return {
            "events": events_data,
            "total_events": total_events,
            "offset": offset,
            "limit": limit,
            "returned": len(events_data)
        }
    finally:
        db.close()



@app.patch("/api/issues/{issue_id}/status", response_class=JSONResponse)
async def update_issue_status(issue_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Update issue status and send message to Slack thread"""
    db = get_db()
    try:
        issue = db.query(Issue).filter(Issue.id == issue_id, Issue.deleted_at == None).first()
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        body = await request.json()
        new_status = body.get('status')
        
        if not new_status:
            raise HTTPException(status_code=400, detail="Status is required")
        
        old_status = issue.status
        issue.status = new_status
        db.commit()
        
        # Send message to Slack thread
        if issue.root_thread_id:
            try:
                from slack_bolt import App
                
                slack_app = App(
                    token=os.environ.get("SLACK_BOT_TOKEN"),
                    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
                )
                
                # Extract channel and thread timestamp
                if ':' in issue.root_thread_id:
                    parts = issue.root_thread_id.split(':')
                    if len(parts) == 2:
                        channel = parts[0]
                        thread_ts = parts[1]
                        
                        message = f"Status changed from *{old_status}* to *{new_status}* by {user.get('id', 'unknown')}"
                        result = slack_app.client.chat_postMessage(
                            channel=channel,
                            thread_ts=thread_ts,
                            text=message
                        )
                        print(f"Message posted to Slack: {result}")
                    else:
                        print(f"Invalid root_thread_id format (multiple colons): {issue.root_thread_id}")
                else:
                    print(f"Old format root_thread_id detected (no channel info): {issue.root_thread_id}. Cannot post to Slack.")
            except Exception as e:
                print(f"Error posting to Slack: {e}")
                import traceback
                traceback.print_exc()
        
        return {
            "id": str(issue.id),
            "status": issue.status,
            "message": f"Status updated from {old_status} to {new_status}"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.patch("/api/issues/{issue_id}/priority", response_class=JSONResponse)
async def update_issue_priority(issue_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Update issue priority"""
    db = get_db()
    try:
        issue = db.query(Issue).filter(Issue.id == issue_id, Issue.deleted_at == None).first()
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        body = await request.json()
        new_priority = body.get('priority')
        
        if not new_priority:
            raise HTTPException(status_code=400, detail="Priority is required")
        
        issue.priority = new_priority
        db.commit()
        
        return {
            "id": str(issue.id),
            "priority": issue.priority,
            "message": "Priority updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/programs", response_class=HTMLResponse)
async def list_programs(request: Request, user: dict = Depends(get_current_user)):
    """List all programs"""
    db = get_db()
    try:
        programs = db.query(Program).filter(Program.deleted_at == None).order_by(Program.created_at.desc()).all()
        return templates.TemplateResponse("programs.html", {
            "request": request,
            "programs": programs,
            "user": user
        })
    finally:
        db.close()


@app.get("/api/programs", response_class=JSONResponse)
async def get_programs_api(user: dict = Depends(get_current_user)):
    """Get all programs as JSON"""
    db = get_db()
    try:
        programs = db.query(Program).filter(Program.deleted_at == None).order_by(Program.created_at.desc()).all()
        return [{
            "id": str(program.id),
            "program_id": program.program_id,
            "name": program.name,
            "description": program.description,
            "owners": program.owners,
            "channels": program.channels,
            "created_at": program.created_at.isoformat() if program.created_at else None,
            "updated_at": program.updated_at.isoformat() if program.updated_at else None
        } for program in programs]
    finally:
        db.close()


@app.post("/api/programs", response_class=JSONResponse)
async def create_program(
    request: Request,
    user: dict = Depends(require_admin)
):
    """Create a new program (admin only)"""
    data = await request.json()
    
    # Validate required fields
    if not data.get('program_id') or not data.get('name'):
        raise HTTPException(status_code=400, detail="program_id and name are required")
    
    db = get_db()
    try:
        # Check if program_id already exists
        existing = db.query(Program).filter(Program.program_id == data['program_id'], Program.deleted_at == None).first()
        if existing:
            raise HTTPException(status_code=400, detail="Program ID already exists")
        
        program = Program(
            program_id=data['program_id'],
            name=data['name'],
            description=data.get('description', ''),
            owners=data.get('owners', []),
            channels=data.get('channels', [])
        )
        db.add(program)
        db.commit()
        db.refresh(program)
        
        return {
            "id": str(program.id),
            "program_id": program.program_id,
            "name": program.name,
            "description": program.description,
            "owners": program.owners,
            "channels": program.channels,
            "created_at": program.created_at.isoformat() if program.created_at else None
        }
    finally:
        db.close()


@app.put("/api/programs/{program_id}", response_class=JSONResponse)
async def update_program(
    program_id: str,
    request: Request,
    user: dict = Depends(require_admin)
):
    """Update a program (admin only)"""
    data = await request.json()
    
    db = get_db()
    try:
        program = db.query(Program).filter(Program.id == program_id, Program.deleted_at == None).first()
        if not program:
            raise HTTPException(status_code=404, detail="Program not found")
        
        # Update fields
        if 'name' in data:
            program.name = data['name']
        if 'description' in data:
            program.description = data['description']
        if 'owners' in data:
            program.owners = data['owners']
        if 'channels' in data:
            program.channels = data['channels']
        
        program.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(program)
        
        return {
            "id": str(program.id),
            "program_id": program.program_id,
            "name": program.name,
            "description": program.description,
            "owners": program.owners,
            "channels": program.channels,
            "updated_at": program.updated_at.isoformat()
        }
    finally:
        db.close()


@app.delete("/api/programs/{program_id}", response_class=JSONResponse)
async def delete_program(
    program_id: str,
    user: dict = Depends(require_admin)
):
    """Delete a program (admin only)"""
    db = get_db()
    try:
        program = db.query(Program).filter(Program.id == program_id, Program.deleted_at == None).first()
        if not program:
            raise HTTPException(status_code=404, detail="Program not found")
        
        program.deleted_at = datetime.utcnow()
        db.commit()
        
        return {"message": "Program deleted successfully"}
    finally:
        db.close()


@app.get("/api/me", response_class=JSONResponse)
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """Get current user info"""
    is_admin = user.get('id') == AUTH_USERNAME
    return {
        **user,
        "is_admin": is_admin
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
