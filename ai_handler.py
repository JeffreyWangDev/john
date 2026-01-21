import os
import sys
import httpx
from typing import List, Optional, Dict, Any
from datetime import datetime

sys.path.append(os.path.dirname(__file__))
from slack_bot.db import get_db, get_issue_events
from shared.models import AIJob, Event, Issue

AI_API_URL = os.environ.get("AI_API_URL", "https://ai.hackclub.com/proxy/v1/chat/completions")
AI_API_KEY = os.environ.get("AI_API_KEY")
AI_MODEL = os.environ.get("AI_MODEL", "openai/gpt-4")


def create_ai_job(event_id: str, job_type: str = "full_extraction") -> AIJob:
    db = get_db()
    try:
        ai_job = AIJob(
            event_id=event_id,
            job_type=job_type,
            status="pending",
            output={}
        )
        db.add(ai_job)
        db.commit()
        db.refresh(ai_job)
        return ai_job
    finally:
        db.close()


def get_pending_ai_jobs() -> List[AIJob]:
    db = get_db()
    try:
        jobs = db.query(AIJob).filter(
            AIJob.status == "pending",
            AIJob.deleted_at.is_(None)
        ).all()
        return jobs
    finally:
        db.close()


async def call_ai_api(messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> Dict[str, Any]:
    if not AI_API_KEY:
        raise ValueError("AI_API_KEY environment variable is not set")
    
    formatted_messages = []
    
    if system_prompt:
        formatted_messages.append({
            "role": "system",
            "content": system_prompt
        })
    
    formatted_messages.extend(messages)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            AI_API_URL,
            headers={
                "Authorization": f"Bearer {AI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": AI_MODEL,
                "messages": formatted_messages,
                "temperature": 0.7
            }
        )
        response.raise_for_status()
        return response.json()


async def summarize_thread(issue_id: str) -> Dict[str, Any]:
    events = get_issue_events(issue_id)
    
    if not events:
        return {"error": "No messages found for this issue"}
    
    thread_text = "\n\n".join([
        f"[{event.author}]: {event.body}"
        for event in events
        if event.body
    ])
    
    system_prompt = """You are an AI assistant that analyzes support conversations. 
Your job is to:
1. Summarize the main issue or request
2. Identify key discussion points
3. Extract any action items or promises made
4. Determine the current status and next steps
5. Assess the urgency and sentiment

Respond in JSON format with the following structure:
{
    "summary": "Brief overview of the issue",
    "main_issue": "The core problem or request",
    "key_points": ["point 1", "point 2", ...],
    "action_items": ["action 1", "action 2", ...],
    "promises": ["promise 1", "promise 2", ...],
    "next_steps": "What should happen next",
    "urgency": "low|medium|high",
    "sentiment": "positive|neutral|negative",
    "suggested_tags": ["tag1", "tag2", ...]
}"""
    
    messages = [
        {
            "role": "user",
            "content": f"Analyze this support thread:\n\n{thread_text}"
        }
    ]
    
    try:
        response = await call_ai_api(messages, system_prompt)
        ai_content = response["choices"][0]["message"]["content"]
        
        import json
        try:
            summary_data = json.loads(ai_content)
        except json.JSONDecodeError:
            summary_data = {
                "summary": ai_content,
                "raw_response": ai_content
            }
        
        return summary_data
    
    except Exception as e:
        return {"error": str(e)}


async def process_ai_job(job: AIJob) -> Dict[str, Any]:
    db = get_db()
    try:
        job.status = "processing"
        db.add(job)
        db.commit()
        
        event = db.query(Event).filter(Event.id == job.event_id).first()
        if not event:
            job.status = "failed"
            job.output = {"error": "Event not found"}
            db.add(job)
            db.commit()
            return job.output
        
        issue = db.query(Issue).filter(Issue.id == event.issue_id).first()
        if not issue:
            job.status = "failed"
            job.output = {"error": "Issue not found"}
            db.add(job)
            db.commit()
            return job.output
        
        if job.job_type == "full_extraction":
            summary = await summarize_thread(str(issue.id))
            
            job.status = "completed"
            job.output = summary
            job.completed_at = datetime.utcnow()
            
            event.ai_metadata = summary
            db.add(event)
        
        else:
            job.status = "failed"
            job.output = {"error": f"Unknown job type: {job.job_type}"}
        
        db.add(job)
        db.commit()
        db.refresh(job)
        
        return job.output
    
    except Exception as e:
        job.status = "failed"
        job.output = {"error": str(e)}
        db.add(job)
        db.commit()
        return job.output
    
    finally:
        db.close()


async def process_pending_jobs():
    jobs = get_pending_ai_jobs()
    
    for job in jobs:
        print(f"Processing AI job {job.id} (type: {job.job_type})")
        result = await process_ai_job(job)
        print(f"Job {job.id} completed with result: {result}")


if __name__ == "__main__":
    import asyncio
    
    print("Starting AI job processor...")
    asyncio.run(process_pending_jobs())
