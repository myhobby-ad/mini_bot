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
ADMIN_ID = 7563343710  # Sizning ID raqamingiz

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
    except Exception: return "aniqlab bo'lmadi"

def get_weather():
    try:
        # Tashkent uchun ob-havo
        res = requests.get("https://wttr.in/Tashkent?format=3")
        return res.text.strip()
    except Exception: return "aniqlab bo'lmadi"

def draw_image(prompt):
    return f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"

# --- 2. MA'LUMOTLAR BAZASI (Neon.tech) ---

def get_db_connection():
    return psycopg2.connect(DB_URL, sslmode='require')

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS history (id SERIAL PRIMARY KEY, user_id BIGINT, role TEXT, content TEXT)")
    conn.commit()
    cur.close()
    conn.close()

# --- 3. KLAVIATURA ---

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💵 Kurs"), KeyboardButton(text="☁️ Ob-havo")],
            [KeyboardButton(text="🎨 Rasm chizish"), KeyboardButton(text="📄 PDF o'qish")]
        ],
        resize_keyboard=True
    )

# --- 4. OVOZNI MATNGA AYLANTIRISH (Sifatni oshirish) ---

async def speech_to_text(file_id):
    file = await bot.get_file(file_id)
    voice_buffer = await bot.download_file(file.file_path)
    voice_buffer.name = "voice.ogg" 
    
    # Whisper modeliga tilni aniq ko'rsatamiz (O'zbek tili tushunishini yaxshilaydi)
    transcription = client.audio.transcriptions.create(
        file=voice_buffer, 
        model="whisper-large-v3", 
        response_format="text",
        language="uz" 
    )
    return transcription

# --- 5. HANDLERLAR ---

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    # Foydalanuvchini bazaga qo'shish
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", 
                    (message.from_user.id, message.from_user.username))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"DB Error: {e}")
        
    await message.answer("Salom! Men yangilangan AI botman. Menga yozishingiz yoki ovoz yuborishingiz mumkin.", 
                         reply_markup=get_main_keyboard())

# Ovozli xabar handler (Matnli handlerdan tepada turishi shart!)
@dp.message(F.content_type == ContentType.VOICE)
async def handle_voice(message: types.Message):
    msg = await message.answer("🎤 Ovozingiz tahlil qilinmoqda...")
    try:
        text = await speech_to_text(message.voice.file_id)
        # Ovozli xabarni matn sifatida qayta ishlash uchun chat_handlerga uzatamiz
        message.text = text
        await msg.delete()
        await message.answer(f"Siz: {text}")
        await chat_handler(message)
    except Exception as e:
        logging.error(f"Voice error: {e}")
        await message.answer("Kechirasiz, ovozingizni tushuna olmadim. Iltimos, aniqroq gapiring.")

@dp.message()
async def chat_handler(message: types.Message):
    if not message.text: return
    
    text = message.text
    user_id = message.from_user.id
    # Oddiy buyruqlar
    if text == "💵 Kurs":
        return await message.answer(f"Bugungi dollar kursi: {get_currency()} so'm")
    
    if text == "☁️ Ob-havo":
        return await message.answer(f"Toshkentdagi ob-havo: {get_weather()}")

    # AI bilan muloqot (Kontekstni saqlash bilan)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Oxirgi 5 ta xabarni olish (Suhbat davomliligi uchun)
        cur.execute("SELECT role, content FROM history WHERE user_id = %s ORDER BY id DESC LIMIT 5", (user_id,))
        rows = cur.fetchall()[::-1]
        history = [{"role": r, "content": c} for r, c in rows]
        
        system_prompt = {"role": "system", "content": "Siz o'zbek tilida so'zlashuvchi aqlli yordamchisiz."}
        msgs = [system_prompt] + history + [{"role": "user", "content": text}]
        
        response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=msgs)
        answer = response.choices[0].message.content
        
        # Tarixni bazaga yozish
        cur.execute("INSERT INTO history (user_id, role, content) VALUES (%s, 'user', %s)", (user_id, text))
        cur.execute("INSERT INTO history (user_id, role, content) VALUES (%s, 'assistant', %s)", (user_id, answer))
        conn.commit()
        cur.close()
        conn.close()
        
        await message.answer(answer)
    except Exception as e:
        logging.error(f"AI Error: {e}")
        await message.answer("Hozircha javob bera olmayman, birozdan so'ng urinib ko'ring.")

async def main():
    init_db() # Baza jadvallarini yaratish
    print("Bot muvaffaqiyatli ishga tushdi!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
