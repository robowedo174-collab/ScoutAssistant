import os
import logging
import asyncio
import requests 
import time # Добавляем для задержки при Long Polling
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties 

# ... (Настройки логирования, ключи, URL_ENDPOINT, SYSTEM_PROMPT остаются прежними) ...

# URL для проверки статуса запроса (Long Polling)
URL_GET_REQUEST = "https://api.gen-api.ru/api/v1/request/get/"


# --- 3. Вспомогательная функция для запроса к Gen-API (Long Polling) ---
async def generate_response_from_api(user_text: str) -> str:
    """Отправляет запрос на Gen-API и ждет результата через Long Polling."""
    
    input_data = {
        # Теперь не отправляем is_sync: true, используем поведение по умолчанию (асинхронный старт)
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

        if not request_id or status != "starting":
            logging.error(f"Failed to start Gen-API request: {data_start}")
            return f"❌ Gen-API не смог начать задачу. Статус: {status}."

        # --- ШАГ 2: В цикле ждем выполнения задачи (Long Polling) ---
        max_attempts = 15 # Максимум 15 попыток
        delay = 2 # Задержка 2 секунды между попытками
        
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
                # УСПЕХ: Извлекаем контент из output
                output_data = data_check.get("output")
                if output_data and isinstance(output_data, list) and output_data[0].get("message"):
                    return output_data[0]["message"]["content"]
                else:
                    # Если формат ответа success, но структура не та, что ожидаем
                    logging.error(f"Success, but unexpected output structure: {data_check}")
                    return "❌ Успех, но получен неожиданный формат ответа."
                    
            elif current_status == "processing":
                # Задача еще в работе, ждем следующей попытки
                continue
                
            elif current_status == "failed" or current_status == "error":
                # Задача завершилась ошибкой
                error_msg = data_check.get("result", ["Нет подробностей."])[0]
                return f"❌ Задача Gen-API провалена. Причина: {error_msg}"
        
        # Если цикл закончился без успеха
        return "❌ Превышено время ожидания ответа от Gen-API (30 секунд). Попробуйте позже."
            
    except requests.exceptions.HTTPError as e:
        return f"❌ Ошибка подключения Gen-API. Код {e.response.status_code}. Проверьте токен или адрес API!"
    except Exception as e:
        logging.error(f"Непредвиденная ошибка Long Polling: {e}")
        return f"❌ Непредвиденная ошибка. ({e})"

# ... (Остальной код бота - инициализация, /start, handle_text_message - остается без изменений) ...
