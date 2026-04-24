import os
import asyncio
import requests
import logging
import sqlite3
import io
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ContentType
from groq import Groq
from dotenv import load_dotenv
from pypdf import PdfReader

# --- SOZLAMALAR ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_KEY)

logging.basicConfig(level=logging.INFO)

# --- TUGMALAR (KEYBOARDS) ---
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💵 Kurs"), KeyboardButton(text="☁️ Ob-havo")],
            [KeyboardButton(text="🎨 Rasm chizish"), KeyboardButton(text="📄 PDF o'qish")]
        ],
        resize_keyboard=True
    )
    return keyboard

# --- MA'LUMOTLAR BAZASI (SQLITE) ---
DB_NAME = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS history (user_id INTEGER, role TEXT, content TEXT)")
    conn.commit()
    conn.close()

def save_message(user_id, role, content):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (user_id, role, content) VALUES (?, ?, ?)", (user_id, role, content))
    cursor.execute("DELETE FROM history WHERE rowid NOT IN (SELECT rowid FROM history WHERE user_id = ? ORDER BY rowid DESC LIMIT 10) AND user_id = ?", (user_id, user_id))
    conn.commit()
    conn.close()

def get_history(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM history WHERE user_id = ? ORDER BY rowid ASC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r, "content": c} for r, c in rows]

# --- FUNKSIYALAR ---
def get_currency():
    try:
        res = requests.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/")
        usd = next(item for item in res.json() if item['Ccy'] == 'USD')
        return usd['Rate']
    except: return "aniqlab bo'lmadi"

def get_weather():
    try:
        res = requests.get("https://wttr.in/Tashkent?format=3")
        return res.text.strip()
    except: return "aniqlab bo'lmadi"

def draw_image(prompt):
    return f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"

async def summarize_pdf(pdf_stream):
    try:
        reader = PdfReader(pdf_stream)
        text = "".join([page.extract_text() for page in reader.pages[:3]])
        if not text: return "PDF-dan matn topilmadi."
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": "PDF mazmunini o'zbekcha qisqartiring."}, {"role": "user", "content": text[:4000]}]
        )
        return completion.choices[0].message.content
    except Exception as e: return f"Xato: {e}"

# --- HANDLERLAR ---
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer("Salom! Men kuchaytirilgan AI botman.", reply_markup=get_main_keyboard())

@dp.message(F.content_type == ContentType.DOCUMENT)
async def handle_document(message: types.Message):
    if message.document.mime_type == 'application/pdf':
        await message.answer("📄 PDF o'qilyapti...")
        file = await bot.get_file(message.document.file_id)
        pdf_content = await bot.download_file(file.file_path)
        summary = await summarize_pdf(pdf_content)
        await message.answer(f"Mazmuni:\n{summary}")

@dp.message(Command("rasm"))
async def handle_draw_command(message: types.Message, command: Command):
    prompt = command.args
    if not prompt: return await message.answer("Nima chizishni yozing. Masalan: /rasm mashina")
    await message.answer_photo(photo=draw_image(prompt), caption=f"Natija: {prompt}")
@dp.message()    
async def chat_handler(message: types.Message):
    if not message.text: return
    text = message.text
    if "Kurs" in text: return await message.answer(f"Dollar: {get_currency()} so'm")
    if "Ob-havo" in text: return await message.answer(f"Toshkent: {get_weather()}")

    # Groq AI
    history = get_history(message.from_user.id)
    msgs = [{"role": "system", "content": "Siz yordamchisiz."}] + history + [{"role": "user", "content": text}]
    res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=msgs)
    ans = res.choices[0].message.content
    save_message(message.from_user.id, "user", text)
    save_message(message.from_user.id, "assistant", ans)
    await message.answer(ans)

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
