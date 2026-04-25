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
ADMIN_ID = 7563343710  # Sizning ID-ingiz

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_KEY)

logging.basicConfig(level=logging.INFO)

# --- 1. YORDAMCHI FUNKSIYALAR ---

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

# --- 2. BAZA BILAN ISHLASH (Neon.tech) ---

def get_db_connection():
    return psycopg2.connect(DB_URL, sslmode='require')

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Foydalanuvchilar va xabarlar tarixi jadvallari
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS history (id SERIAL PRIMARY KEY, user_id BIGINT, role TEXT, content TEXT)")
    conn.commit()
    cur.close()
    conn.close()

# --- 3. TUGMALAR ---

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💵 Kurs"), KeyboardButton(text="☁️ Ob-havo")],
            [KeyboardButton(text="🎨 Rasm chizish"), KeyboardButton(text="📄 PDF o'qish")]
        ],
        resize_keyboard=True
    )

# --- 4. OVOZNI MATNGA AYLANTIRISH (Whisper) ---

async def speech_to_text(file_id):
    file = await bot.get_file(file_id)
    voice_buffer = await bot.download_file(file.file_path)
    # Groq API fayl nomini talab qiladi
    voice_buffer.name = "voice.ogg" 
    transcription = client.audio.transcriptions.create(
        file=voice_buffer, 
        model="whisper-large-v3", 
        response_format="text"
    )
    return transcription

# --- 5. HANDLERLAR (TARTIB MUHIM!) ---

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", 
                (message.from_user.id, message.from_user.username))
    conn.commit()
    cur.close()
    conn.close()
    await message.answer("Salom! Men universal AI botman. Men bilan gaplashishingiz yoki tugmalardan foydalanishingiz mumkin.", reply_markup=get_main_keyboard())

@dp.message(Command("rasm"))
async def handle_draw_command(message: types.Message, command: Command):
    prompt = command.args
    if not prompt: 
        return await message.answer("Nima chizishni yozing. Masalan: /rasm robot.")
    await message.answer("🎨 Rasm chizilyapti...")
    await message.answer_photo(photo=draw_image(prompt), caption=f"Natija: {prompt}")

@dp.message(F.content_type == ContentType.VOICE)
async def handle_voice(message: types.Message):
    await message.answer("🎤 Eshitaman...")
    try:
        text = await speech_to_text(message.voice.file_id)
        await message.answer(f"Siz: {text}")
        # Ovozni matnga aylantirib, AI-ga yuboramiz
        message.text = text 
        await chat_handler(message)
    except Exception as e:
        logging.error(f"Ovoz xatosi: {e}")
        await message.answer("Ovozni tushunib bo'lmadi.")

@dp.message() # Umumiy chat handleri (Har doim eng pastda bo'ladi)
async def chat_handler(message: types.Message):
    if not message.text: return
    text = message.text
    user_id = message.from_user.id
    if text == "💵 Kurs":
        return await message.answer(f"Dollar kursi: {get_currency()} so'm")
    if text == "☁️ Ob-havo":
        return await message.answer(f"Ob-havo: {get_weather()}")

    # AI va Kontekst (Neon Baza orqali)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Oxirgi 6 ta xabarni olish
        cur.execute("SELECT role, content FROM history WHERE user_id = %s ORDER BY id DESC LIMIT 6", (user_id,))
        rows = cur.fetchall()[::-1] # Tarixni to'g'ri tartiblash
        history = [{"role": r, "content": c} for r, c in rows]
        
        msgs = [{"role": "system", "content": "Siz aqlli yordamchisiz."}] + history + [{"role": "user", "content": text}]
        res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=msgs)
        ans = res.choices[0].message.content
        
        # Tarixni bazaga yozish
        cur.execute("INSERT INTO history (user_id, role, content) VALUES (%s, 'user', %s)", (user_id, text))
        cur.execute("INSERT INTO history (user_id, role, content) VALUES (%s, 'assistant', %s)", (user_id, ans))
        conn.commit()
        cur.close()
        conn.close()
        await message.answer(ans)
    except Exception as e:
        logging.error(f"Chat xatosi: {e}")
        await message.answer("Hozir javob bera olmayman.")

async def main():
    init_db()
    print("Bot ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())   
