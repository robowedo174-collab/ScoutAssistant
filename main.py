import os
import logging
import asyncio
import requests 
import time 
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties 

# Настройки логирования
logging.basicConfig(level=logging.INFO)

# --- 1. Секреты и ключи из Переменных Окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GENAPI_KEY = os.getenv("GENAPI_KEY")

URL_ENDPOINT = "https://api.gen-api.ru/api/v1/networks/gpt-4o-mini"
URL_GET_REQUEST = "https://api.gen-api.ru/api/v1/request/get/"

SYSTEM_PROMPT = "Ты — Андрей Куракин, опытный инструктор скаутского лагеря с 20-летним стажем. Твой стиль общения — бодрый и структурированный. Твоя задача — помочь составить программу дня для группы детей. Отвечай только по делу, используя скаутские принципы."

# --- 2. Инициализация ---
bot = Bot(token=BOT_TOKEN, 
          default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)) 
dp = Dispatcher()


# --- 3. Вспомогательная функция для запроса к Gen-API (Long Polling) ---
async def generate_response_from_api(user_text: str) -> str:
    """
    Отправляет запрос на Gen-API и ждет результата через Long Polling.
    """
    
    input_data = {
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
        # --- ШАГ 1: Отправляем запрос и получаем ID задачи ---
        response_start = await asyncio.to_thread(
            requests.post, 
            URL_ENDPOINT, 
            json=input_data, 
            headers=headers,
            timeout=10
        )
        response_start.raise_for_status() 
        data_start = response_start.json()
        
        request_id = data_start.get("id")
        if not request_id:
             request_id = data_start.get("request_id")
             
        status = data_start.get("status")

        # Очищаем статус от невидимых пробелов
        if isinstance(status, str):
            status = status.strip()

        # Проверка на успешный старт задачи (допускаем "starting" или "processing")
        if not request_id or status not in ["starting", "processing"]:
            logging.error(f"❌ Failed to start Gen-API request: {data_start}")
            return f"❌ Gen-API не смог начать задачу. Статус: {status}."

        # --- ШАГ 2: В цикле ждем выполнения задачи (Long Polling) ---
        max_attempts = 25 # <-- УВЕЛИЧЕН ТАЙМАУТ: 25 попыток * 2 сек = 50 сек
        delay = 2 
        
        for attempt in range(max_attempts):
            await asyncio.to_thread(time.sleep, delay)
            
            # Отправляем GET-запрос для проверки статуса
            response_check = await asyncio.to_thread(
                requests.get, 
                f"{URL_GET_REQUEST}{request_id}",
                headers=headers,
                timeout=5
            )
            response_check.raise_for_status()
            data_check = response_check.json()
            
            current_status = data_check.get("status")
            
            if current_status == "success":
                                
                # --- УНИВЕРСАЛЬНЫЙ БЕЗОПАСНЫЙ ПАРСЕР V11 (Ищем в 'result') ---
                try:
                    # Ищем в 'result', как показал последний лог
                    content = data_check.get("result")[0].get("message").get("content")
                    
                    logging.info(f"✅ Content parsed successfully from 'result'.")
                    return content
                except Exception as e:
                    # Если структура отличается, логируем точную ошибку
                    logging.error(f"❌ Critical Error: Failed to parse content. Exact error: {e}. Full response: {data_check}")
                    return f"❌ Структура ответа Gen-API изменилась. Не найден ключ/индекс: {e}."
                                
            elif current_status == "processing":
                logging.debug(f"Processing... Attempt {attempt + 1}/{max_attempts}")
                continue 
                            
            elif current_status in ["failed", "error"]:
                # Обработка ошибок
                error_msg = data_check.get("result", ["Нет подробностей"])
                if isinstance(error_msg, list):
                    error_msg = error_msg[0] if error_msg else "Нет подробностей"
                logging.error(f"❌ Task failed: {error_msg}")
                return f"❌ Gen-API ошибка: {error_msg}"
        
        # Если цикл закончился без успеха (таймаут)
        logging.warning("❌ Timeout: Превышено время ожидания")
        return "❌ Превышено время ожидания ответа от Gen-API. Попробуйте позже."
            
    except requests.exceptions.HTTPError as e:
        logging.error(f"❌ HTTP Error {e.response.status_code}")
        return f"❌ Ошибка подключения Gen-API. Код {e.response.status_code}!"
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}", exc_info=True)
        return f"❌ Ошибка: {e}"


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
