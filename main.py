import os
import asyncio
import requests
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from groq import Groq
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv()

# .env faylidan ma'lumotlarni o'qiymiz
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_KEY)

# Kurs olish funksiyasi
def get_currency():
    try:
        res = requests.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/")
        data = res.json()
        usd = next(item for item in data if item['Ccy'] == 'USD')
        return f"Bugungi dollar kursi: {usd['Rate']} so'm"
    except:
        return "Kurs ma'lumotini olib bo'lmadi."

# Ob-havo olish funksiyasi
def get_weather():
    try:
        res = requests.get("https://wttr.in/Tashkent?format=3")
        return f"Ob-havo: {res.text}"
    except:
        return "Ob-havo ma'lumotini olishda xatolik."

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer("Salom! Men universal AI botman. Kurslar, ob-havo va istalgan savolingizga javob bera olaman.")

@dp.message()
async def universal_chat_handler(message: types.Message):
    if not message.text: return
    
    msg_text = message.text.lower()

    # Kurs va ob-havoni tekshirish
    if "kurs" in msg_text or "dollar" in msg_text:
        await message.answer(get_currency())
        return
    if "ob-havo" in msg_text or "havo qanaqa" in msg_text:
        await message.answer(get_weather())
        return

    # Boshqa savollar uchun Groq AI
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Siz universal yordamchisiz. Har qanday mavzuda javob bering."},
                {"role": "user", "content": message.text}
            ]
        )
        await message.answer(completion.choices[0].message.content)
    except Exception as e:
        logging.error(f"Xato: {e}")

async def main():
    print("--- BOT ISHGA TUSHDI ---")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if  __name__ == "__main__":
    asyncio.run(main())