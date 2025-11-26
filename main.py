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
# Уровень INFO будет показывать только важные события и успешный парсинг.
logging.basicConfig(level=logging.INFO)

# --- 1. Секреты и ключи из Переменных Окружения ---
# Убедитесь, что эти переменные установлены на Bothost.ru
BOT_TOKEN = os.getenv("BOT_TOKEN")
GENAPI_KEY = os.getenv("GENAPI_KEY")

# URL для запросов к GPT-4o mini (Старт задачи)
URL_ENDPOINT = "https://api.gen-api.ru/api/v1/networks/gpt-4o-mini"
# URL для проверки статуса запроса (Long Polling)
URL_GET_REQUEST = "https://api.gen-api.ru/api/v1/request/get/"


# Системный промпт (Душа бота)
SYSTEM_PROMPT = "Ты — Андрей Куракин, опытный инструктор скаутского лагеря с 20-летним стажем. Твой стиль общения — бодрый и структурированный. Твоя задача — помочь составить программу дня для группы детей. Отвечай только по делу, используя скаутские принципы."

# --- 2. Инициализация ---
# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, 
          default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)) 
dp = Dispatcher()


# --- 3. Вспомогательная функция для запроса к Gen-API (Long Polling) ---
async def generate_response_from_api(user_text: str) -> str:
    """
    Отправляет запрос на Gen-API и ждет результата через Long Polling.
    Включает гибкий старт и безопасный парсинг ответа.
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
        
        request_id = data_start.get("request_id")
        status = data_start.get("status")

        # *** КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ V10: Очищаем статус от невидимых пробелов ***
        if isinstance(status, str):
            status = status.strip()

        # Проверка на успешный старт задачи (допускаем "starting" или "processing")
        if not request_id or status not in ["starting", "processing"]:
            logging.error(f"❌ Failed to start Gen-API request: {data_start}")
            return f"❌ Gen-API не смог начать задачу. Статус: {status}."

        # --- ШАГ 2: В цикле ждем выполнения задачи (Long Polling) ---
        max_attempts = 15 # Максимум 15 попыток * 2 секунды = 30 секунд
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
                                
                # --- МИНИМАЛЬНЫЙ БЕЗОПАСНЫЙ ПАРСЕР (Основан на ТОЧНОЙ структуре) ---
                try:
                    # Прямой и безопасный доступ к тексту
                    content = data_check.get("response")[0].get("message").get("content")
                    
                    logging.info(f"✅ Content parsed successfully.")
                    return content
                except Exception as e:
                    # Если структура отличается, логируем точную ошибку и полный ответ
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
