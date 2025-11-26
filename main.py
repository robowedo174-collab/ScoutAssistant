# --- 3. Вспомогательная функция для запроса к Gen-API (Long Polling) ---
async def generate_response_from_api(user_text: str) -> str:
    """Отправляет запрос на Gen-API и ждет результата через Long Polling с ОДНОЙ, жесткой проверкой."""
    
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

        if not request_id or status != "starting":
            logging.error(f"❌ Failed to start Gen-API request: {data_start}")
            return f"❌ Gen-API не смог начать задачу. Статус: {status}."

        # --- ШАГ 2: В цикле ждем выполнения задачи (Long Polling) ---
        max_attempts = 15 
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
                                
                # --- ЖЕСТКАЯ ПРОВЕРКА (Сценарий: 'response' всегда есть) ---
                try:
                    # Пытаемся получить текст по САМОМУ СТАБИЛЬНОМУ пути
                    content = data_check["response"][0]["message"]["content"]
                    logging.info(f"✅ Content parsed successfully using direct path.")
                    return content
                except (KeyError, IndexError, TypeError) as e:
                    # В случае ошибки, мы получим ТОЧНУЮ информацию:
                    logging.error(f"❌ Critical Error: Failed to parse content. Missing key/index: {e}. Full response: {data_check}")
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
