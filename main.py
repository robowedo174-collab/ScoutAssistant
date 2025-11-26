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

# Модель: GPT-4o (для глубоких ответов)
URL_ENDPOINT = "https://api.gen-api.ru/api/v1/networks/gpt-4o"
URL_GET_REQUEST = "https://api.gen-api.ru/api/v1/request/get/"


# ИЗМЕНЕНИЕ: ОБЪЕМНЫЙ МЕТОДОЛОГИЧЕСКИЙ СИСТЕМНЫЙ ПРОМПТ
SYSTEM_PROMPT = """
Твоё имя — **Андрей Куракин младший**. Ты — ведущий эксперт по скаутской педагогике с 15-летним опытом разработки программ для детей от 7 до 12 лет. 

Твоя задача — **методологически разработать** практикоориентированные, глубокие и безопасные активности для палаточного лагеря, строго следуя принципам скаутинга.

### ТРЕБОВАНИЯ К ОТВЕТУ (Структура и Стиль):
1.  **Стиль:** Твой тон должен быть **бодрым, вдохновляющим и авторитетным**. Используй богатый, но понятный язык.
2.  **Практика:** Каждый ответ должен быть максимально **практикоориентированным**, включая необходимое снаряжение, продолжительность и чёткие этапы.
3.  **Вариативность:** Всегда предлагай **минимум два альтернативных варианта** активности (например, вариант A и вариант B) для того же этапа программы, чтобы дать пользователю выбор.
4.  **Методологическое Обоснование:** Самое важное — **каждый выбор активности** ты должен **подробно привязывать и объяснять** через один или несколько основополагающих **методов скаутинга**. Используй яркие **метафоры** и **аналогии** для объяснения.

### ОСНОВНЫЕ МЕТОДЫ СКАУТИНГА для обоснования:
* **Обучение Делом (Learning by Doing):** Получение опыта через активную практику, а не через пассивное слушание.
* **Система Патрулей/Малых Групп:** Работа в малых, самостоятельных командах для развития лидерства и ответственности.
* **Символическая Рамка:** Использование легенд, церемоний, знаков и ритуалов для эмоционального вовлечения.
* **Жизнь на Природе:** Максимальное использование природного окружения как учебной лаборатории.
* **Прогрессивное Развитие (Программы Роста):** Постепенное усложнение задач и движение к цели.

В конце каждого ответа всегда спрашивай, какой из предложенных вариантов активности (А или В) пользователь хочет выбрать.
"""

# --- 2. Инициализация ---
bot = Bot(token=BOT_TOKEN, 
          default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)) 
dp = Dispatcher()


# --- 3. Вспомогательная функция для запроса к Gen-API (Long Polling) ---
async def generate_response_from_api(user_text: str) -> str:
    """Отправляет запрос на Gen-API и ждет результата через Long Polling."""
    
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

        # Очищаем статус от невидимых пробелов (для стабильности)
        if isinstance(status, str):
            status = status.strip()

        # Проверка на успешный старт задачи 
        if not request_id or status not in ["starting", "processing"]:
            logging.error(f"❌ Failed to start Gen-API request: {data_start}")
            return f"❌ Gen-API не смог начать задачу. Статус: {status}."

        # --- ШАГ 2: В цикле ждем выполнения задачи (Long Polling) ---
        max_attempts = 25 # Таймаут 50 сек
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
                                
                # --- БЕЗОПАСНЫЙ ПАРСЕР (Ищем в 'result') ---
                try:
                    content = data_check.get("result")[0].get("message").get("content")
                    
                    logging.info(f"✅ Content parsed successfully from 'result'.")
                    return content
                except Exception as e:
                    logging.error(f"❌ Critical Error: Failed to parse content. Exact error: {e}. Full response: {data_check}")
                    return f"❌ Структура ответа Gen-API изменилась. Не найден ключ/индекс: {e}."
                                
            elif current_status == "processing":
                logging.debug(f"Processing... Attempt {attempt + 1}/{max_attempts}")
                continue 
                            
            elif current_status in ["failed", "error"]:
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
    # ИЗМЕНЕНИЕ: Приветствие с новым именем
    await message.answer(
        f"Привет, *{message.from_user.full_name}*! Я **Андрей Куракин младший** — твой личный эксперт по скаутской методологии. \n\n"
        f"Я готов разработать глубокую и практичную программу для лагеря. *Просто напиши мне запрос*!"
    )

# --- 5. Обработчик всех текстовых сообщений ---
@dp.message(F.text)
async def handle_text_message(message: types.Message) -> None:
    """Обрабатывает текстовые запросы пользователя и отправляет их в AI."""
    
    # Показываем, что бот думает
    thinking_message = await message.answer("⏳ *Андрей Куракин младший* методично разрабатывает программу...")
    
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
