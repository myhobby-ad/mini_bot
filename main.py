import os
import asyncio
import requests
import logging
import psycopg2
import io
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ContentType
from groq import Groq
from dotenv import load_dotenv

# --- SOZLAMALAR ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
DB_URL = os.getenv("DATABASE_URL")
ADMIN_ID = 7563343710 # Sizning ID-ingiz rasmda shunday ekan

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_KEY)

logging.basicConfig(level=logging.INFO)

# --- QO'SHIMCHA FUNKSIYALAR (Xatolar yo'qolishi uchun shu yerda bo'lishi shart) ---

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

# --- BAZA BILAN ISHLASH ---
def get_db_connection():
    return psycopg2.connect(DB_URL, sslmode='require')

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS history (user_id BIGINT, role TEXT, content TEXT)")
    conn.commit()
    cur.close()
    conn.close()

# --- TUGMALAR ---
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💵 Kurs"), KeyboardButton(text="☁️ Ob-havo")],
            [KeyboardButton(text="🎨 Rasm chizish"), KeyboardButton(text="📄 PDF o'qish")]
        ],
        resize_keyboard=True
    )
    return keyboard

# --- OVOZNI MATNGA AYLANTIRISH ---
async def speech_to_text(file_id):
    file = await bot.get_file(file_id)
    voice_buffer = await bot.download_file(file.file_path)
    voice_buffer.name = "voice.ogg"
    transcription = client.audio.transcriptions.create(
        file=voice_buffer, model="whisper-large-v3", response_format="text"
    )
    return transcription

# --- HANDLERLAR ---

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", 
                (message.from_user.id, message.from_user.username))
    conn.commit()
    cur.close()
    conn.close()
    await message.answer("Salom! Men endi hamma narsani tushunaman (Ovoz, rasm, PDF).", reply_markup=get_main_keyboard())

@dp.message(Command("rasm"))
async def handle_draw_command(message: types.Message, command: Command):
    prompt = command.args
    if not prompt: 
        return await message.answer("Nima chizishni yozing. Masalan: /rasm uchar mashina.")
    
    await message.answer("🎨 Rasm chizilyapti, kuting...")
    url = draw_image(prompt)
    await message.answer_photo(photo=url, caption=f"Sizning so'rovingiz: {prompt}")

@dp.message(F.content_type == ContentType.VOICE)
async def handle_voice(message: types.Message):
    await message.answer("🎤 Eshitaman...")
    try:
        text = await speech_to_text(message.voice.file_id)
        await message.answer(f"Siz: {text}")
        # Ovozni matnga aylantirib, chat_handlerga uzatamiz
        message.text = text
        await chat_handler(message)
    except Exception as e:
        await message.answer("Ovozni tushuna olmadim.")

@dp.message()
async def chat_handler(message: types.Message):
    if not message.text: return
    text = message.text
    user_id = message.from_user.id
    # Tugmalar uchun shartlar
    if "Kurs" in text:
        return await message.answer(f"Bugungi dollar kursi: {get_currency()} so'm")
    
    if "Ob-havo" in text:
        return await message.answer(f"Toshkent: {get_weather()}")

    # AI va Tarix (Neon Baza)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT role, content FROM history WHERE user_id = %s ORDER BY rowid ASC LIMIT 6", (user_id,))
        history = [{"role": r, "content": c} for r, c in cur.fetchall()]
        
        msgs = [{"role": "system", "content": "Siz universal yordamchisiz."}] + history + [{"role": "user", "content": text}]
        res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=msgs)
        ans = res.choices[0].message.content
        
        cur.execute("INSERT INTO history (user_id, role, content) VALUES (%s, 'user', %s)", (user_id, text))
        cur.execute("INSERT INTO history (user_id, role, content) VALUES (%s, 'assistant', %s)", (user_id, ans))
        conn.commit()
        cur.close()
        conn.close()
        await message.answer(ans)
    except Exception as e:
        await message.answer("Xatolik yuz berdi.")

async def main():
    init_db()
    print("--- BOT ISHGA TUSHDI ---")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
