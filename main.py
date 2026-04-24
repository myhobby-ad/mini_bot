import os
import asyncio
import requests
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from groq import Groq
from dotenv import load_dotenv

# .env faylidan yoki Render Environment Variables'dan o'qiymiz
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

# Bot va AI mijozini sozlash
bot = Bot(token=TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_KEY)

logging.basicConfig(level=logging.INFO)

# --- FUNKSIYALAR ---

def get_currency():
    """Markaziy bankdan dollar kursini olish"""
    try:
        res = requests.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/")
        data = res.json()
        usd = next(item for item in data if item['Ccy'] == 'USD')
        return usd['Rate']
    except Exception:
        return "kurs ma'lumotini olib bo'lmadi."

def get_weather():
    """Toshkent ob-havosini olish"""
    try:
        res = requests.get("https://wttr.in/Tashkent?format=3")
        return res.text.strip()
    except Exception:
        return "ob-havo ma'lumotini olib bo'lmadi."

# --- HANDLERLAR ---

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    """/start komandasi yuborilganda"""
    await message.answer(
        "Salom! Men universal AI botman. 🤖\n\n"
        "Men bilan istalgan tilda gaplashishingiz mumkin. "
        "Shuningdek, 'kurs' yoki 'ob-havo' deb yozsangiz, kerakli ma'lumotlarni beraman."
    )

@dp.message()
async def universal_chat_handler(message: types.Message):
    """Barcha xabarlarni qayta ishlash"""
    if not message.text:
        return

    text = message.text.lower()

    # 1. Valyuta kursi
    if "kurs" in text or "dollar" in text:
        rate = get_currency()
        await message.answer(f"Bugungi dollar kursi: {rate} so'm 💵")
        return

    # 2. Ob-havo
    if "ob-havo" in text or "weather" in text or "havo qanaqa" in text:
        weather = get_weather()
        await message.answer(f"Hozirgi holat: {weather} ☁️")
        return

    # 3. Groq AI (Llama 3.3)
    try:
        # Foydalanuvchi yozgan tilda javob berish uchun tizimli ko'rsatma
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system", 
                    "content": "Siz universal yordamchisiz. Foydalanuvchi qaysi tilda yozsa, aynan o'sha tilda javob bering."
                },
                {"role": "user", "content": message.text}
            ]
        )
        ai_response = completion.choices[0].message.content
        await message.answer(ai_response)
    except Exception as e:
        logging.error(f"AI Xatolik: {e}")
        await message.answer("Kechirasiz, AI bilan bog'lanishda xatolik yuz berdi.")

async def main():
    print("--- BOT ISHGA TUSHDI ---")
    # Eski xabarlarni o'chirib yuborish
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
