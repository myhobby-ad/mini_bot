import os
from groq import Groq
from dotenv import load_dotenv

# 1. Sozlamalarni yuklash
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    print("Xatolik: .env faylida GROQ_API_KEY topilmadi!")
else:
    # 2. Groq mijozini sozlash
    client = Groq(api_key=api_key)

    print("--- Groq AI Agent ishga tushdi ---")
    print("Chiqish uchun 'exit' deb yozing.\n")

    while True:
        user_input = input("Siz: ")
        
        if user_input.lower() in ['exit', 'stop', 'chiqish']:
            break

        try:
            # 3. Groq-ga so'rov yuborish (Llama 3 modelini ishlatamiz)
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": user_input}],
            )
            
            print(f"\nAI Agent: {completion.choices[0].message.content}\n")
            print("-" * 30)
            
        except Exception as e:
            print(f"Xatolik yuz berdi: {e}")