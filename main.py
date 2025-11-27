import os
import logging
import asyncio
import requests 
import time 
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties 

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GENAPI_KEY = os.getenv("GENAPI_KEY")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не найден. Укажи его в переменных окружения.")
if not GENAPI_KEY:
    raise RuntimeError("❌ GENAPI_KEY не найден. Укажи ключ Gen-API в переменных окружения.")

...

async def generate_response_from_api(user_text: str) -> str:
    input_data = {
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "text", "text": user_text}]}
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GENAPI_KEY}",
    }

    try:
        response_start = await asyncio.to_thread(
            requests.post, 
            URL_ENDPOINT, 
            json=input_data, 
            headers=headers,
            timeout=10
        )
        response_start.raise_for_status() 
        data_start = response_start.json()
        
        request_id = data_start.get("id") or data_start.get("request_id")
        status = (data_start.get("status") or "").strip()

        if not request_id or status not in ["starting", "processing"]:
            logging.error(f"❌ Failed to start Gen-API request: {data_start}")
            return f"❌ Gen-API не смог начать задачу. Статус: {status}."

        max_attempts = 20
        delay = 2 
        
        for attempt in range(max_attempts):
            await asyncio.to_thread(time.sleep, delay)
            
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
                try:
                    result = data_check.get("result")
                    if not result:
                        raise KeyError("result")
                    message_obj = result[0].get("message")
                    if not message_obj:
                        raise KeyError("message")
                    content = message_obj.get("content")
                    if not content:
                        raise KeyError("content")

                    if isinstance(content, str):
                        return content

                    if isinstance(content, list):
                        parts = []
                        for block in content:
                            text_part = block.get("text") or ""
                            parts.append(text_part)
                        return "\n".join(parts).strip()

                    return str(content)

                except Exception as e:
                    logging.error(
                        f"❌ Critical Error: Failed to parse content. Exact error: {e}. Full response: {data_check}"
                    )
                    return "❌ Не удалось прочитать ответ от Gen-API. Возможно, изменилась структура."

            elif current_status == "processing":
                logging.debug(f"Processing... Attempt {attempt + 1}/{max_attempts}")
                continue 

            elif current_status in ["failed", "error"]:
                error_msg = data_check.get("result", ["Нет подробностей"])
                if isinstance(error_msg, list):
                    error_msg = error_msg[0] if error_msg else "Нет подробностей"
                logging.error(f"❌ Task failed: {error_msg}")
                return f"❌ Gen-API ошибка: {error_msg}"
        
        logging.warning("❌ Timeout: Превышено время ожидания")
        return "❌ Превышено время ожидания ответа от Gen-API. Попробуйте позже."
            
    except requests.exceptions.HTTPError as e:
        logging.error(f"❌ HTTP Error {e.response.status_code}")
        return f"❌ Ошибка подключения Gen-API. Код {e.response.status_code}!"
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}", exc_info=True)
        return f"❌ Ошибка: {e}"
