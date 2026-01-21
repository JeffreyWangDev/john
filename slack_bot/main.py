import os
import sys
import asyncio
import threading
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from db import (
    create_issue_from_thread,
    save_thread_messages_as_events,
    add_participant,
    get_issue_by_thread_id,
    update_issue_from_ai,
    create_program as db_create_program,
    get_program,
    get_program_by_channel,
    add_channel_to_program,
    add_program_owner,
    remove_program_owner,
    get_all_programs,
    link_issue_to_program,
    set_issue_owner,
    set_channel_owner,
    remove_channel_owner,
    remove_issue_owner,
    is_issue_owner,
    is_channel_owner,
    get_issue_with_program
)
from slack_bolt.request import BoltRequest
from permissions import Permission, has_permission, get_user_permission, require_permission

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from ai_handler import create_ai_job, process_ai_job, summarize_thread

load_dotenv()

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)


def process_ai_in_background(issue_id: str, logger):
    """
    Process AI analysis in a background thread
    """

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        summary = loop.run_until_complete(summarize_thread(issue_id))
        loop.close()
        
        if "error" not in summary:
            updated_issue = update_issue_from_ai(issue_id, summary)
            if updated_issue:
                logger.info(f"Issue {issue_id} updated with AI summary")
        else:
            logger.warning(f"AI processing error for issue {issue_id}: {summary.get('error')}")
    
    except Exception as ai_error:
        logger.exception(f"Error processing AI job in background: {ai_error}")

def get_all_messages(channel_id: str, thread_ts: str, client) -> list[dict]:
    """
    Retrieve all messages from a Slack channel
    """
    all_messages = []
    cursor = None

    while True:
        response = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            cursor=cursor,
            limit=999
        )
        messages = response.get("messages", [])
        all_messages.extend(messages)

        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return all_messages

@app.event("app_mention")
def handle_app_mention(event, say, logger):
    """
    Respond when the bot is mentioned in a channel
    """
    user = event["user"]
    text = event.get("text", "")
    thread_ts = event.get("thread_ts")
    
    print(f"App mentioned by user {user}: {text}")
    
    if thread_ts:
        try:
            program = get_program_by_channel(event["channel"])
            if not program:
                app.client.chat_postMessage(
                    channel=event["channel"],
                    text=(
                        "❌ This channel is not managed by a program yet.\n\n"
                        "Ask the HQ staff to request this be added to john!"
                    ),
                    thread_ts=thread_ts
                )
                return
            
            existing_issue = get_issue_by_thread_id(thread_ts, event["channel"])
            if existing_issue:
                app.client.chat_postMessage(
                    channel=event["channel"],
                    text=f"⚠️ An issue already exists for this thread (ID: `{existing_issue.id}`)",
                    thread_ts=thread_ts
                )
                return
            
            all_messages = get_all_messages(event["channel"], thread_ts, app.client)
            
            first_message = all_messages[0] if all_messages else {}
            title = first_message.get("text", "")[:100] + ("..." if len(first_message.get("text", "")) > 100 else "")
            
            issue = create_issue_from_thread(
                thread_ts=thread_ts,
                channel_id=event["channel"],
                title=title or "Untitled Issue",
                description=f"Issue created from Slack thread in channel {event['channel']}"
            )
            
            set_issue_owner(str(issue.id), user)
            
            if program:
                link_issue_to_program(str(issue.id), program.program_id)
            
            events = save_thread_messages_as_events(
                issue_id=str(issue.id),
                messages=all_messages
            )
            
            add_participant(
                issue_id=str(issue.id),
                slack_user_id=user,
                role="requester"
            )
            
            unique_users = set()
            for msg in all_messages:
                if msg.get("user"):
                    unique_users.add(msg["user"])
            
            for slack_user in unique_users:
                if slack_user != user:
                    add_participant(
                        issue_id=str(issue.id),
                        slack_user_id=slack_user,
                        role="watcher"
                    )
            
            if events:
                ai_job = create_ai_job(
                    event_id=str(events[0].id),
                    job_type="full_extraction"
                )
                
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    summary = loop.run_until_complete(summarize_thread(str(issue.id)))
                    loop.close()
                    
                    if "error" not in summary:
                        updated_issue = update_issue_from_ai(str(issue.id), summary)
                        if updated_issue:
                            logger.info(f"Issue {issue.id} updated with AI summary")
                    
                except Exception as ai_error:
                    logger.exception(f"Error processing AI job: {ai_error}")
            
            user_perm = get_user_permission(user, channel_id=event["channel"], issue_id=str(issue.id))
            
            issue_data = get_issue_with_program(str(issue.id))
            program_info = ""
            if issue_data and issue_data.get("program"):
                program_info = f"*Program:* {issue_data['program']['name']}\n"
            
            app.client.chat_postMessage(
                channel=event["channel"],
                text=(
                    f"✅ Issue created successfully!\n\n"
                    f"*Issue ID:* `{issue.id}`\n"
                    f"{program_info}"
                    f"*Status:* {issue.status}\n"
                    f"*Messages saved:* {len(events)}\n"
                    f"*Participants:* {len(unique_users)}\n"
                    f"*Your role:* {user_perm.value}"
                ),
                thread_ts=thread_ts
            )
            
        except Exception as e:
            logger.exception(f"Error creating issue: {e}")
            app.client.chat_postMessage(
                channel=event["channel"],
                text=f"❌ Error creating issue: {str(e)}",
                thread_ts=thread_ts
            )
    else:
        app.client.chat_postMessage(
            channel=event["channel"],
            text=f"Hello <@{user}>! 👋 Mention me in a thread to create an issue from the conversation!",
            thread_ts=event.get("ts")
        )
        

@app.event("message")
def handle_message_events(event, logger):
    """
    Handle new messages - add to existing issues if in a thread
    """
    if event.get("bot_id") or event.get("subtype") in ["message_deleted", "message_changed", "message_replied"]:
        return
    
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return
    
    try:
        existing_issue = get_issue_by_thread_id(thread_ts, event.get("channel"))
        if not existing_issue:
            return
        
        from slack_bot.db import get_db
        from shared.models import Event
        
        db = get_db()
        try:
            event_record = Event(
                issue_id=existing_issue.id,
                source="slack",
                external_id=event.get("ts"),
                author=event.get("user", "unknown"),
                body=event.get("text", ""),
                event_type="message_added",
                ai_metadata={}
            )
            db.add(event_record)
            db.commit()
            logger.info(f"Added message to issue {existing_issue.id}")
        finally:
            db.close()
    
    except Exception as e:
        logger.exception(f"Error handling message event: {e}")
    
@app.error
def custom_error_handler(error, body, logger):
    """
    Handle errors
    """
    logger.exception(f"Error: {error}")
    logger.info(f"Request body: {body}")


if __name__ == "__main__":
    socket_token = os.environ.get("SLACK_APP_TOKEN")
    
    if socket_token:
        handler = SocketModeHandler(app, socket_token)
        print("Slack bot is running in Socket Mode!")
        handler.start()
    else:
        port = int(os.environ.get("PORT", 3000))
        print(f"Slack bot is running on port {port}!")
        app.start(port=port)
