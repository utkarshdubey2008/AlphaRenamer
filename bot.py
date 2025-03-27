from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo
from telethon.tl.custom import Message, Button
import os
from typing import Union
import asyncio
import time
from datetime import datetime
import math

API_ID = "25482744"
API_HASH = "e032d6e5c05a5d0bfe691480541d64f4"
BOT_TOKEN = "5866712065:AAFsz5teNdXMgza0qc8UV3HAgOxeaL9OONY"

client_config = {
    'connection_retries': None,
    'retry_delay': 2,
    'flood_sleep_threshold': 120,
    'request_retries': 5,
    'connection': {
        'receive_buffer_size': 1024 * 1024 * 8,
        'send_buffer_size': 1024 * 1024 * 8,
    }
}

bot = TelegramClient('bot_session', API_ID, API_HASH, **client_config).start(bot_token=BOT_TOKEN)

user_states = {}

def get_formatted_time():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def format_size(size):
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size_bytes = float(size)
    unit_index = 0
    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024
        unit_index += 1
    return f"{size_bytes:.2f} {units[unit_index]}"

def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.0f}m {(seconds % 60):.0f}s"
    else:
        hours = seconds / 3600
        minutes = (seconds % 3600) / 60
        return f"{hours:.0f}h {minutes:.0f}m"

class UserState:
    def __init__(self):
        self.file_to_rename = None
        self.waiting_for_name = False
        self.waiting_for_format = False
        self.original_message = None
        self.file_path = None
        self.progress_message = None
        self.start_time = None
        self.last_update_time = 0
        self.last_current = 0
        self.speed_history = []
        self.chunk_size = 1024 * 1024  
        self.upload_chunk_size = 1024 * 1024

async def progress_callback(current, total, state, message, action="Processing"):
    try:
        if not state.start_time:
            state.start_time = time.time()
            state.last_update_time = time.time()
            state.last_current = 0
            state.speed_history = []
        
        now = time.time()
        
        if now - state.last_update_time < 0.5 and current != total:
            return
        
        time_diff = now - state.last_update_time
        if time_diff > 0:
            speed = (current - state.last_current) / time_diff
            state.speed_history.append(speed)
            if len(state.speed_history) > 5:
                state.speed_history.pop(0)
                
            if speed > 5 * 1024 * 1024:  # If speed > 5MB/s, increase chunk size
                state.chunk_size = min(state.chunk_size * 2, 8 * 1024 * 1024)
                state.upload_chunk_size = min(state.upload_chunk_size * 2, 8 * 1024 * 1024)
        
        avg_speed = sum(state.speed_history) / len(state.speed_history) if state.speed_history else 0
        
        state.last_update_time = now
        state.last_current = current
        
        percentage = (current / total) * 100 if total else 0
        
        bar_length = 15
        filled_length = int(percentage / 100 * bar_length)
        bar = '■' * filled_length + '□' * (bar_length - filled_length)
        
        if avg_speed > 0:
            eta = (total - current) / avg_speed
            eta_str = format_time(eta)
        else:
            eta_str = "Calculating..."
        
        current_time = get_formatted_time()
        
        progress_text = (
            f"⏱ UTC: {current_time}\n"
            f"📋 {action}...\n\n"
            f"💫 Progress: {percentage:.1f}%\n"
            f"🚀 Speed: {format_size(avg_speed)}/s\n"
            f"📊 {format_size(current)} / {format_size(total)}\n"
            f"⏳ ETA: {eta_str}\n\n"
            f"[{bar}]"
        )
        
        try:
            await message.edit(progress_text)
        except Exception as e:
            print(f"Error updating progress: {str(e)}")
            
    except Exception as e:
        print(f"Progress callback error: {str(e)}")

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    current_time = get_formatted_time()
    await event.reply(
        f"🕒 Bot Started at (UTC): {current_time}\n\n"
        "👋 Welcome to File Renamer Bot!\n\n"
        "Send me any file (document, video, photo, etc.) and I'll help you rename it.\n"
        "Features:\n"
        "• Real-time progress tracking\n"
        "• Speed monitoring\n"
        "• Video format selection\n"
        "• Large file support"
    )

@bot.on(events.NewMessage(func=lambda e: e.file))
async def handle_file(event: Message):
    sender_id = event.sender_id
    current_time = get_formatted_time()
    
    user_states[sender_id] = UserState()
    state = user_states[sender_id]
    
    state.original_message = event
    state.waiting_for_name = True
    
    file_name = event.file.name or "file"
    _, extension = os.path.splitext(file_name)
    
    is_video = hasattr(event.file, 'mime_type') and 'video' in event.file.mime_type
    
    buttons = [
        [Button.inline("✏️ Enter new name", "new_name")],
        [Button.inline("✅ Keep current name", f"keep_{file_name}")]
    ]
    
    await event.reply(
        f"🕒 Time (UTC): {current_time}\n\n"
        f"📁 File: {file_name}\n"
        f"📦 Size: {format_size(event.file.size)}\n"
        f"📝 Type: {'Video' if is_video else 'Document'}\n\n"
        "Choose an option:",
        buttons=buttons
    )

@bot.on(events.CallbackQuery())
async def callback_handler(event):
    sender_id = event.sender_id
    data = event.data.decode()
    current_time = get_formatted_time()
    
    if sender_id not in user_states:
        await event.answer("Session expired. Please send the file again.")
        return
    
    state = user_states[sender_id]
    
    if data.startswith("keep_"):
        state.file_path = data[5:]
        if hasattr(state.original_message.file, 'mime_type') and 'video' in state.original_message.file.mime_type:
            buttons = [
                [Button.inline("📹 Video format", "format_video")],
                [Button.inline("📄 Document format", "format_document")]
            ]
            await event.edit(
                f"🕒 Time (UTC): {current_time}\n"
                "Choose the format:",
                buttons=buttons
            )
        else:
            await process_file(event, state, as_document=True)
    
    elif data == "new_name":
        state.waiting_for_name = True
        await event.edit(
            f"🕒 Time (UTC): {current_time}\n"
            "Please send me the new name for your file."
        )
    
    elif data.startswith("format_"):
        as_document = data == "format_document"
        await event.edit(
            f"🕒 Time (UTC): {current_time}\n"
            "Processing your file..."
        )
        await process_file(event, state, as_document)

@bot.on(events.NewMessage(func=lambda e: not e.file))
async def handle_text(event: Message):
    sender_id = event.sender_id
    current_time = get_formatted_time()
    
    if sender_id not in user_states:
        await event.reply(
            f"🕒 Time (UTC): {current_time}\n"
            "Please send me a file first!"
        )
        return
    
    state = user_states[sender_id]
    
    if state.waiting_for_name:
        new_name = event.text.strip()
        original_file = state.original_message.file
        
        old_name = original_file.name or "file"
        _, extension = os.path.splitext(old_name)
        
        if not new_name.endswith(extension):
            new_name += extension
        
        state.file_path = new_name
        
        if hasattr(original_file, 'mime_type') and 'video' in original_file.mime_type:
            buttons = [
                [Button.inline("📹 Video format", "format_video")],
                [Button.inline("📄 Document format", "format_document")]
            ]
            await event.reply(
                f"🕒 Time (UTC): {current_time}\n"
                "Choose the format:",
                buttons=buttons
            )
        else:
            await process_file(event, state, as_document=True)

async def process_file(event, state: UserState, as_document: bool):
    try:
        progress_msg = await event.respond(
            f"🕒 Time (UTC): {get_formatted_time()}\n"
            "Preparing to process your file..."
        )
        state.progress_message = progress_msg
        state.start_time = None
        
        downloaded_file = await state.original_message.download_media(
            file=state.file_path,
            progress_callback=lambda current, total: progress_callback(
                current, total, state, progress_msg, "Downloading"
            )
        )
        
        state.start_time = None
        await progress_msg.edit(
            f"🕒 Time (UTC): {get_formatted_time()}\n"
            "Preparing to upload..."
        )
        
        await bot.upload_file(
            downloaded_file,
            progress_callback=lambda current, total: progress_callback(
                current, total, state, progress_msg, "Uploading"
            ),
            part_size_kb=state.upload_chunk_size // 1024
        )
        
        uploaded_file = await bot.send_file(
            event.chat_id,
            downloaded_file,
            force_document=as_document,
            caption=f"✅ File renamed: {state.file_path}\n🕒 Completed at (UTC): {get_formatted_time()}"
        )
        
        try:
            os.remove(downloaded_file)
        except:
            pass
        await progress_msg.delete()
        del user_states[event.sender_id]
        
    except Exception as e:
        error_msg = f"❌ Error occurred: {str(e)}\n🕒 Time (UTC): {get_formatted_time()}"
        if state.progress_message:
            await state.progress_message.edit(error_msg)
        else:
            await event.respond(error_msg)
        
        if state.file_path and os.path.exists(state.file_path):
            try:
                os.remove(state.file_path)
            except:
                pass
        del user_states[event.sender_id]

print(f"Bot started at (UTC): {get_formatted_time()}")
bot.run_until_disconnected()
