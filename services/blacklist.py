import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from database import models as db
from services.gemini_service import gemini_service
from config import config


pending_unblocks = {}

async def block_user(user_id: int, reason: str, admin_id: int, permanent: bool = False):
    await db.add_to_blacklist(user_id, reason, admin_id, permanent)
    if permanent:
        await db.set_user_blacklist_strikes(user_id, 99)
        return f"用户 {user_id} 已被管理员永久拉黑。\n原因: {reason}"
    return f"用户 {user_id} 已被管理员拉黑。\n原因: {reason}"

async def unblock_user(user_id: int):
    await db.remove_from_blacklist(user_id)
    
    await db.set_user_blacklist_strikes(user_id, 0)
    return f"用户 {user_id} 已被管理员解封。"

def is_unblock_pending(user_id: int) -> tuple[bool, bool]:
    """
    检查用户是否有待解封问题
    返回: (has_pending: bool, is_expired: bool)
    """
    if user_id not in pending_unblocks:
        return False, True
    
    session = pending_unblocks[user_id]
    is_expired = time.time() - session['created_at'] > config.VERIFICATION_TIMEOUT
    
    if is_expired:
        del pending_unblocks[user_id]
        return False, True
    
    return True, False

def get_pending_unblock_message(user_id: int):
    """
    获取待解封的问题和键盘
    如果解封会话不存在或已过期，返回 None
    返回: (question: str, keyboard: InlineKeyboardMarkup) 或 None
    """
    if user_id not in pending_unblocks:
        return None
    
    session = pending_unblocks[user_id]
    
    if time.time() - session['created_at'] > config.VERIFICATION_TIMEOUT:
        del pending_unblocks[user_id]
        return None
    
    question = session['question']
    options = session['options']
    
    keyboard = [
        [InlineKeyboardButton(option, callback_data=f"unblock_{option}") for option in options]
    ]
    
    return question, InlineKeyboardMarkup(keyboard)

async def start_unblock_process(user_id: int):
    is_blocked, is_permanent = await db.is_blacklisted(user_id)
    
    if is_permanent:
        return "您已被管理员永久封禁，无法通过申诉解封。", None

    # 检查是否有待解封问题
    has_pending, is_expired = is_unblock_pending(user_id)
    
    if has_pending and not is_expired:
        # 有未超时的待解封问题，返回之前的问题
        unblock_data = get_pending_unblock_message(user_id)
        if unblock_data:
            question, keyboard = unblock_data
            return (
                "您还有未完成的解封验证，请先完成验证后再发送消息。\n\n"
                f"您已被暂时封禁。\n\n"
                f"如果您认为这是误操作，请回答以下问题以自动解封：\n\n{question}"
            ), keyboard
    
    # 没有待解封问题或已超时，创建新的问题
    challenge = await gemini_service.generate_unblock_question()
    question = challenge['question']
    correct_answer = challenge['correct_answer']
    options = challenge['options']
    
    existing_attempts = pending_unblocks.get(user_id, {}).get('attempts', 0)
    
    pending_unblocks[user_id] = {
        'answer': correct_answer,
        'question': question,
        'options': options,
        'attempts': existing_attempts,
        'created_at': time.time()
    }
    
    keyboard = [
        [InlineKeyboardButton(option, callback_data=f"unblock_{option}") for option in options]
    ]
    
    return (
        "您已被暂时封禁。\n\n"
        f"如果您认为这是误操作，请回答以下问题以自动解封：\n\n{question}"
    ), InlineKeyboardMarkup(keyboard)

async def verify_unblock_answer(user_id: int, user_answer: str):
    if user_id not in pending_unblocks:
        return "解封会话已过期或不存在。", False

    session = pending_unblocks[user_id]
    
    if time.time() - session['created_at'] > config.VERIFICATION_TIMEOUT:
        del pending_unblocks[user_id]
        return "解封超时，请重新发送消息以获取新问题。", False

    if user_answer == session['answer']:
        del pending_unblocks[user_id]
        await db.remove_from_blacklist(user_id)
        
        await db.set_user_blacklist_strikes(user_id, 0)
        return "解封成功！您现在可以正常发送消息了。", True
    else:
        # 答案错误，不删除会话，允许用户再次尝试（只要未超时）
        session['attempts'] = session.get('attempts', 0) + 1
        
        if session['attempts'] >= config.MAX_VERIFICATION_ATTEMPTS:
            # 超过最大尝试次数，永久封禁
            del pending_unblocks[user_id]
            await db.add_to_blacklist(user_id, reason="解封验证失败次数过多", blocked_by=config.BOT_ID, permanent=True)
            await db.set_user_blacklist_strikes(user_id, 99)
            return "答案错误次数过多，解封失败。您已被永久封禁。", False
        
        return f"答案错误，还有 {config.MAX_VERIFICATION_ATTEMPTS - session['attempts']} 次机会。", False

def _safe_text_for_markdown(text: str) -> str:
    if not text:
        return text
    
    dangerous_chars = r'_*[]()`'
    return "".join(f"\\{char}" if char in dangerous_chars else char for char in text)

async def get_blacklist_keyboard(page: int = 1, per_page: int = 5):
    total_count = await db.get_blacklist_count()
    
    if total_count == 0:
        return "黑名单中没有用户。", None

    total_pages = (total_count + per_page - 1) // per_page

    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page

    blacklist_users = await db.get_blacklist_paginated(limit=per_page, offset=offset)
    
    if not blacklist_users:
        return "黑名单中没有用户。", None

    keyboard = []
    message = f"黑名单用户列表 (第 {page}/{total_pages} 页)\n\n"
    
    for idx, user in enumerate(blacklist_users, 1):
        user_id = user.get('user_id')
        first_name = user.get('first_name') or 'N/A'
        username = user.get('username')
        reason = user.get('reason') or '无'
        
        safe_first_name = _safe_text_for_markdown(first_name)
        safe_username = _safe_text_for_markdown(username) if username else None
        safe_reason = _safe_text_for_markdown(reason)
        
        user_info = f"{safe_first_name}"
        if safe_username:
            user_info += f" (@{safe_username})"
        
        message += f"{idx}. {user_info} (`{user_id}`)\n原因: {safe_reason}\n\n"
        
        keyboard.append([
            InlineKeyboardButton(f"解封 {first_name}", callback_data=f"admin_unblock_{user_id}")
        ])
    
    navigation_buttons = []
    if page > 1:
        navigation_buttons.append(InlineKeyboardButton("上一页", callback_data=f"blacklist_page_{page - 1}"))
    if page < total_pages:
        navigation_buttons.append(InlineKeyboardButton("下一页", callback_data=f"blacklist_page_{page + 1}"))
    
    if navigation_buttons:
        keyboard.append(navigation_buttons)

    return message, InlineKeyboardMarkup(keyboard)
