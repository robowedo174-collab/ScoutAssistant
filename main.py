import os
import logging
import asyncio
import requests # Используем requests для синхронного запроса в отдельном потоке
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties # Для совместимости с aiogram 3.7+

# Настройки логирования
logging.basicConfig(level=logging.INFO)

# --- 1. Секреты и ключи из Переменных Окружения ---
# Bothost.ru передаст эти ключи безопасно вашему скрипту
BOT_TOKEN = os.getenv("BOT_TOKEN")
GENAPI_KEY = os.getenv("GENAPI_KEY")

# URL для запросов к GPT-4o mini
URL_ENDPOINT = "https://api.gen-api.ru/api/v1/networks/gpt-4o-mini"

# Системный промпт (Душа бота)
SYSTEM_PROMPT = "Ты — Андрей Куракин, опытный инструктор скаутского лагеря с 20-летним стажем. Твой стиль общения — бодрый и структурированный. Твоя задача — помочь составить программу дня для группы детей. Отвечай только по делу, используя скаутские принципы."

# --- 2. Инициализация ---
# Инициализация с правильным способом установки ParseMode
bot = Bot(token=BOT_TOKEN, 
          default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)) 
dp = Dispatcher()

# --- 3. Вспомогательная функция для запроса к Gen-API ---
async def generate_response_from_api(user_text: str) -> str:
    """Отправляет запрос на Gen-API в синхронном режиме через requests."""
    
    input_data = {
        "is_sync": True, # Требуем немедленного ответа
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "text", "text": user_text}]}
        ]
    }
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {GENAPI_KEY}' # Формат, подтвержденный документацией
    }

    try:
        # Запускаем синхронный requests.post в отдельном потоке
        response = await asyncio.to_thread(
            requests.post, 
            URL_ENDPOINT, 
            json=input_data, 
            headers=headers,
            timeout=30 
        )
        
        # Обрабатываем HTTP-ошибки (401, 402, 404 и т.д.)
        response.raise_for_status() 
        
        # Получаем JSON-ответ
        response_data = response.json()
        
        # 6. Обработка успешного или ошибочного JSON-ответа (по формату, который вы предоставили)
        
        # Проверяем, что ответ — список с результатом
        if isinstance(response_data, list) and response_data and response_data[0].get("message"):
            
            # УСПЕШНЫЙ ОТВЕТ: Извлекаем текст из поля "content"
            ai_output = response_data[0]["message"]["content"]
            
            if ai_output:
                return ai_output
            else:
                return "❌ Ошибка: AI вернул пустой ответ."
            
        elif response_data.get("status") == "error":
            # Если Gen-API вернул ошибку в своем формате (status: error)
            error_msg = response_data.get("result", ["Нет подробностей."])[0]
            logging.error(f"Gen-API Error: Status=error, Message={error_msg}")
            return f"❌ Проблема с генерацией: Статус ошибки API — error. Причина: {error_msg}"
        
        else:
            # Непредвиденный формат ответа
            logging.error(f"Неизвестный формат ответа от Gen-API: {response_data}")
            return "❌ Непредвиденный формат ответа от сервера Gen-API."
            
    except requests.exceptions.HTTPError as e:
        # Ошибка HTTP (4xx, 5xx)
        return f"❌ Ошибка подключения Gen-API. Проблема: Код {e.response.status_code}. Проверьте токен или баланс!"
    except Exception as e:
        # Неожиданные ошибки (таймаут, проблемы сети)
        logging.error(f"Непредвиденная ошибка при запросе к AI: {e}")
        return f"❌ Непредвиденная ошибка. Пожалуйста, попробуйте еще раз. ({e})"


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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
