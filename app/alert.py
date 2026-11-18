import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart, CommandObject
from contextlib import asynccontextmanager
from fastapi import FastAPI
from datetime import datetime, timezone
import os
import html


from crud import find_user_by_link, save_chat_id, save_telegram_link, get_status
from database import SessionLocal
from services import cleanup_loop


BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = "HSalertdetectbot"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ALERT_COOLDOWN = 1800
last_alert: dict[int, datetime] = {}


def should_alert(chat_id: int) -> bool:
    now = datetime.now(timezone.utc)
    if chat_id in last_alert:
        last = last_alert[chat_id]
        if last and (now - last).total_seconds() < ALERT_COOLDOWN:
            return False
    last_alert[chat_id] = now
    return True


@dp.message(CommandStart(deep_link=True))
async def handle_telegram_link(message: Message, command: CommandObject):
    link_token = command.args
    chat_id = str(message.chat.id)

    with SessionLocal() as session:
        user = find_user_by_link(session, link_token)

        if not user:
            await message.answer("❗ Invalid or expired link. Please generate a new link from your web dashboard.")
            return

        user_id = user.id
        save_chat_id(session, chat_id, user_id)
        save_telegram_link(session, None, user_id)

    await message.answer("✅ Success! Your Telegram account is now linked to your IoT dashboard. You will receive alerts here.")


@dp.message(F.text == "/status")
async def send_current(message: Message):
    with SessionLocal() as session:
        status_data = get_status(session, message.chat.id)
    if not status_data or 'error' in status_data:
        await message.answer("⚠️ No devices found linked to your Telegram account.")
        return
    text = "📊 <b>Your Devices Status:</b>\n\n"

    for device_name, metric in status_data.items():
        text += f"🔵<b>{html.escape(device_name)}</b>\n"
        if not metric or not metric.get('metrics'):
            text += "No recent data\n\n"
            continue
        metrics_dict = metric['metrics']
        raw_time = metric['received_at']
        if raw_time:
            if hasattr(raw_time, 'strftime'):
                formatted_time = raw_time.strftime("%d.%m.%Y %H:%M:%S")
            else:
                formatted_time = str(raw_time).split(".")[0]
        else:
            formatted_time = "N/A" 

        text += f'⏰<code>{formatted_time}</code>\n'

        for key, value in metrics_dict.items():
            text += f"<b>{html.escape(key)}</b>: <code>{html.escape(str(value))}</code>\n"
        text += '\n'
    await message.answer(text, parse_mode="HTML")


async def send_alert(chat_id: str, alert_text: str):
    if should_alert(int(chat_id)):
        try:
            await bot.send_message(chat_id=chat_id, text=alert_text, parse_mode="HTML")
        except Exception as e:
            print(f'Failed to send Telegram alert: {e}')

@asynccontextmanager
async def lifespan(app: FastAPI):
    polling_task = asyncio.create_task(dp.start_polling(bot))
    cleanup_task = asyncio.create_task(cleanup_loop())
    # print('Telegram bot started')

    yield

    for task in (polling_task, cleanup_task):
        task.cancel()
    for task in (polling_task, cleanup_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
    await bot.session.close()
    # print("Telegram bot stopped")

