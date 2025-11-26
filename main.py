import os
import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

# Настройки логирования
logging.basicConfig(level=logging.INFO)

# --- 1. Секреты и ключи из Переменных Окружения ---
# ВАЖНО! Ваш код здесь НЕ СОДЕРЖИТ ваших реальных ключей.
# Он просит систему (Bothost) предоставить их.
BOT_TOKEN = os.getenv("BOT_TOKEN")
GENAPI_KEY = os.getenv("GENAPI_KEY")

# URL для запросов к GPT-4o mini (синхронный режим)
URL_ENDPOINT = "https://api.gen-api.ru/api/v1/networks/gpt-4o-mini"

# Системный промпт (Душа бота)
SYSTEM_PROMPT = "Ты — Андрей Куракин, опытный инструктор скаутского лагеря с 20-летним стажем. Твой стиль общения — бодрый и структурированный. Твоя задача — помочь составить программу дня для группы детей. Отвечай только по делу, используя скаутские принципы."

# --- 2. Инициализация ---
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.MARKDOWN)
dp = Dispatcher()

# --- 3. Вспомогательная функция для запроса к Gen-API ---
async def generate_response_from_api(user_text: str) -> str:
    """Отправляет запрос на Gen-API в синхронном режиме и возвращает ответ."""
    
    input_data = {
        # Используем синхронный режим, чтобы не настраивать Webhook для ответа
        "is_sync": True, 
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "text", "text": user_text}]}
        ]
    }
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {GENAPI_KEY}'
    }

    try:
        # Используем aiohttp для асинхронного выполнения запроса
        async with aiohttp.ClientSession() as session:
            async with session.post(URL_ENDPOINT, json=input_data, headers=headers) as response:
                response.raise_for_status() # Проверяем на ошибки HTTP (4xx, 5xx)
                response_data = await response.json()
                
                if response_data.get("status") == "success":
                    ai_output = response_data.get("output", {}).get("text", "Ошибка: не удалось извлечь текст.")
                    return ai_output
                else:
                    error_msg = response_data.get("error_message", "Неизвестная ошибка API.")
                    return f"❌ Проблема с генерацией: {error_msg}"
                
    except Exception as e:
        logging.error(f"Ошибка при запросе к AI: {e}")
        return "❌ Произошла ошибка. Проверьте ваш GENAPI_KEY в панели Bothost."


# --- 4. Обработчик команды /start ---
@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    await message.answer(
        f"Привет, *{message.from_user.full_name}*! Я Мистер Куракин, твой личный помощник по скаутингу. \n\n"
        f"Я готов помочь тебе составить идеальную программу для лагеря. *Просто напиши мне запрос*!"
    )

# --- 5. Обработчик всех текстовых сообщений ---
@dp.message(F.text)
async def handle_text_message(message: types.Message) -> None:
    """Обрабатывает текстовые запросы пользователя и отправляет их в AI."""
    
    # Показываем, что бот думает
    thinking_message = await message.answer("⏳ *Мистер Куракин* думает над программой...")
    
    # Получаем ответ от AI
    ai_response = await generate_response_from_api(message.text)
    
    # Удаляем сообщение "думаю" и отправляем ответ
    await bot.delete_message(message.chat.id, thinking_message.message_id)
    await message.answer(ai_response)

# --- 6. Запуск бота ---
async def main() -> None:
    """Запускает бота."""
    # Bothost.ru автоматически настроит окружение
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
