from enum import Enum
from typing import Optional
import os

class Permission(Enum):
    USER = "user"                  # Default permission - can view and comment
    OWNER = "owner"                # Owner of a specific issue - can manage their own content
    PROGRAM_OWNER = "program_owner" # Owner of a program - can manage all issues in their program
    ADMIN = "admin"                # Admin over everything - full control


ADMIN_USERS = set(os.environ.get("SLACK_ADMIN_USERS", "").split(","))


def get_user_permission(user_id: str, channel_id: Optional[str] = None, issue_id: Optional[str] = None) -> Permission:
    """
    Get the effective permission level for a user.
    Checks in order: admin -> program_owner -> issue_owner -> user (default)
    """
    from slack_bot.db import get_issue_with_program, get_program_by_channel, is_channel_owner, is_issue_owner
    
    if user_id in ADMIN_USERS:
        return Permission.ADMIN
    
    if channel_id:
        program = get_program_by_channel(channel_id)
        if program and user_id in program.owners:
            return Permission.PROGRAM_OWNER
    
    if issue_id:
        try:
            issue_data = get_issue_with_program(issue_id)
            if issue_data and issue_data.get("program") and user_id in issue_data["program"].get("owners", []):
                return Permission.PROGRAM_OWNER
        except:
            pass
    
    if channel_id and is_channel_owner(channel_id, user_id):
        return Permission.OWNER
    
    if issue_id and is_issue_owner(issue_id, user_id):
        return Permission.OWNER
    
    return Permission.USER


def has_permission(user_id: str, required_permission: Permission, 
                   channel_id: Optional[str] = None, issue_id: Optional[str] = None) -> bool:
    """
    Check if a user has the required permission level.
    Permission hierarchy: ADMIN > PROGRAM_OWNER > OWNER > USER
    """
    user_perm = get_user_permission(user_id, channel_id, issue_id)
    
    permission_hierarchy = {
        Permission.USER: 0,
        Permission.OWNER: 1,
        Permission.PROGRAM_OWNER: 2,
        Permission.ADMIN: 3
    }
    
    return permission_hierarchy[user_perm] >= permission_hierarchy[required_permission]


def require_permission(required_permission: Permission):
    """
    Decorator to require a specific permission level for an action
    """
    def decorator(func):
        def wrapper(event, *args, **kwargs):
            user_id = event.get("user")
            channel_id = event.get("channel")
            
            if not has_permission(user_id, required_permission, channel_id=channel_id):
                perm_name = required_permission.value
                kwargs.get('say', lambda **k: None)(
                    text=f"❌ You need {perm_name} permission to perform this action.",
                    thread_ts=event.get("thread_ts") or event.get("ts")
                )
                return
            
            return func(event, *args, **kwargs)
        return wrapper
    return decorator
