import os
import logging
import asyncio
import requests 
import time 
import random 
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command 
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties 
from aiogram.fsm.context import FSMContext 
from aiogram.fsm.state import State, StatesGroup 

# --- Настройки ---
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
GENAPI_KEY = os.getenv("GENAPI_KEY")

URL_ENDPOINT = "https://api.gen-api.ru/api/v1/networks/gpt-4o"
URL_GET_REQUEST = "https://api.gen-api.ru/api/v1/request/get/"

# --- FSM (Машина состояний) и Промпты ---
# (Остаются без изменений)

class BotStates(StatesGroup):
    waiting_for_raw_goal = State()
    confirming_goal = State()      
    working_mode = State()         

GOAL_REFINER_PROMPT = """
Ты — старший методист скаутского движения. Твоя задача — взять черновик цели, который написал вожатый, и переформулировать его в **профессиональную, четкую педагогическую цель** по системе SMART и скаутскому методу.
Не меняй смысл, но добавь глубины, укажи развиваемый навык или качество.
Ответ должен содержать ТОЛЬКО сформулированную цель, без лишних слов "Вот вариант...".
"""

SYSTEM_PROMPT_BASE = """
Твоё имя — **Личный помошник Андрея Куракина**. Ты — эксперт по скаутской педагогике.

### ТЕКУЩАЯ МЕТОДОЛОГИЧЕСКАЯ ЦЕЛЬ:
**{program_goal}**

### ТВОЯ ЗАДАЧА:
Разрабатывать активности, которые работают НА ЭТУ ЦЕЛЬ.

### ТРЕБОВАНИЯ К ОТВЕТУ:
1.  **Связь с Целью:** В начале ответа кратко объясни, как именно это упражнение работает на цель "{program_goal}".
2.  **Структура:** Название, Время, Снаряжение, Ход действия, Рефлексия.
3.  **Вариативность:** Предложи Вариант А (попроще) и Вариант В (посложнее/другой формат) Вариант С (творческий/совсем другой формат).
4.  **Метод:** Используй скаутские методы (малые группы, символизм, природа).
"""

# --- Инициализация ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)) 
dp = Dispatcher()

# --- Универсальная функция запроса к API ---
# (send_to_gpt остается без изменений)

async def send_to_gpt(system_prompt: str, user_text: str) -> str:
    """Отправляет запрос к GPT-4o с заданным системным промптом."""
    input_data = {
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "text", "text": user_text}]}
        ]
    }
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {GENAPI_KEY}'}

    try:
        # Старт задачи
        resp = await asyncio.to_thread(requests.post, URL_ENDPOINT, json=input_data, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        req_id = data.get("id") or data.get("request_id")
        
        status = str(data.get("status")).strip()
        if not req_id or status not in ["starting", "processing"]:
            return "❌ Ошибка старта API."

        # Ожидание (Long Polling)
        for _ in range(25): # 50 секунд таймаут
            await asyncio.to_thread(time.sleep, 2)
            check = await asyncio.to_thread(requests.get, f"{URL_GET_REQUEST}{req_id}", headers=headers, timeout=5)
            d_check = check.json()
            
            if d_check.get("status") == "success":
                try:
                    return d_check.get("result")[0].get("message").get("content")
                except:
                    return "❌ Ошибка структуры JSON."
            elif d_check.get("status") in ["failed", "error"]:
                return "❌ Ошибка генерации."
        return "❌ Таймаут."
    except Exception as e:
        return f"❌ Ошибка соединения: {e}"


# --- НОВАЯ ФУНКЦИЯ: Установка главного меню ---
async def set_main_menu(bot: Bot):
    """
    Устанавливает главное меню команд бота, которое видно слева от поля ввода.
    """
    main_menu_commands = [
        types.BotCommand(command='/show_goal', description='Цель программы 🎯'),
        types.BotCommand(command='/set_goal', description='Изменить/Цель 📝')
    ]
    await bot.set_my_commands(main_menu_commands)


# --- ОБРАБОТЧИКИ (HANDLERS) ---
# (Все обработчики остаются без изменений: cmd_start, cmd_show_goal, cmd_set_new_goal, process_raw_goal, confirm_goal, handle_working_mode)
# ... (вставьте сюда весь код обработчиков из V18, он не меняется)
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    """Обработчик команды /start."""
    user_data = await state.get_data()
    current_goal = user_data.get("program_goal")

    if current_goal:
        # Если цель уже сохранена
        await state.set_state(BotStates.working_mode)
        await message.answer(
            f"Здравия желаю, *{message.from_user.full_name}*! \n"
            f"Твоя **текущая Цель:** `{current_goal}`. Продолжай работу!\n"
            f"Чтобы посмотреть цель: `/show_goal`"
        )
    else:
        # Если цель не установлена, начинаем процесс
        await message.answer(
            f"Я — **Личный помошник Андрея Куракина**. Без Цели мы никуда. \n"
            f"Напиши мне, чего ты хочешь добиться от детей (черновик цели).\n"
            f"Я помогу сформулировать это профессионально."
        )
        await state.set_state(BotStates.waiting_for_raw_goal)


@dp.message(Command("show_goal"))
async def cmd_show_goal(message: types.Message, state: FSMContext):
    """Показывает текущую сохраненную цель программы."""
    user_data = await state.get_data()
    current_goal = user_data.get("program_goal")

    if current_goal:
        await message.answer(
            f"✅ **Твоя текущая Методическая Цель:**\n\n"
            f"🎯 *{current_goal}*\n\n"
            f"Вся работа ведется именно на эту цель. Чтобы изменить цель, используй `/set_goal`."
        )
    else:
        await message.answer(
            "⚠️ **Цель не установлена.**\n"
            "Используй команду `/set_goal`, чтобы начать работу."
        )


@dp.message(Command("set_goal"))
async def cmd_set_new_goal(message: types.Message, state: FSMContext):
    """Триггерит процесс установки/изменения цели в любой момент."""
    await message.answer(
        "📝 **Начинаем установку новой Цели.**\n"
        "Напиши мне, чего ты хочешь добиться от детей. Я помогу сформулировать это профессионально."
    )
    await state.set_state(BotStates.waiting_for_raw_goal)


@dp.message(BotStates.waiting_for_raw_goal)
async def process_raw_goal(message: types.Message, state: FSMContext):
    """Получаем черновик, улучшаем его через ИИ и предлагаем юзеру."""
    raw_goal = message.text
    waiting_msg = await message.answer("🤔 *Формулирую методическую цель...*")
    
    refined_goal = await send_to_gpt(GOAL_REFINER_PROMPT, raw_goal)
    
    await bot.delete_message(message.chat.id, waiting_msg.message_id)
    await state.update_data(temp_goal=refined_goal)
    
    await message.answer(
        f"Вот как это звучит на языке профессиональной педагогики:\n\n"
        f"🎯 **{refined_goal}**\n\n"
        f"Тебе подходит эта формулировка?\n"
        f"Напиши **«Да»**, чтобы утвердить, или свой исправленный вариант."
    )
    await state.set_state(BotStates.confirming_goal)


@dp.message(BotStates.confirming_goal)
async def confirm_goal(message: types.Message, state: FSMContext):
    """Фиксация цели, сохранение и переход в рабочий режим."""
    text = message.text.lower().strip()
    user_data = await state.get_data()
    
    if text in ["да", "ок", "хорошо", "yes", "+"]:
        final_goal = user_data.get("temp_goal")
    else:
        final_goal = message.text
        
    # Сохранение Цели и инициализация "Режима Карен Прайор"
    await state.update_data(
        program_goal=final_goal, # <-- Здесь цель сохраняется в FSMContext
        msg_count=0, 
        trigger_threshold=random.randint(3, 5)
    )
    
    await state.set_state(BotStates.working_mode)
    
    await message.answer(
        f"✅ **Цель утверждена:**\n`{final_goal}`\n\n"
        f"Теперь мы работаем на неё. Пиши запрос на активность, и я буду тренировать твое мышление."
    )

@dp.message(BotStates.working_mode, F.text)
async def handle_working_mode(message: types.Message, state: FSMContext):
    """Основной цикл работы с подкреплением Карен Прайор."""
    user_data = await state.get_data()
    current_goal = user_data.get("program_goal")
    
    if not current_goal:
        await message.answer("⚠️ Цель программы потеряна. Пожалуйста, установите ее снова: `/set_goal`")
        return
        
    msg_count = user_data.get("msg_count", 0) + 1
    trigger_threshold = user_data.get("trigger_threshold", 4)
    
    thinking_msg = await message.answer(f"⏳ Разрабатываю активность под цель: `{current_goal}`...")
    
    final_prompt = SYSTEM_PROMPT_BASE.format(program_goal=current_goal)
    ai_response = await send_to_gpt(final_prompt, message.text)
    
    await bot.delete_message(message.chat.id, thinking_msg.message_id)
    await message.answer(ai_response)
    
    if msg_count >= trigger_threshold:
        await asyncio.sleep(1.5)
        reflection_msg = (
            "🧐 **СТОП-КАДР! Тренировка методического мышления.**\n\n"
            f"Оцени от 1 до 10 про себя. Если меньше 10 — спроси меня: *«Как усилить влияние на цель?»*"
        )
        await message.answer(reflection_msg)
        await state.update_data(msg_count=0, trigger_threshold=random.randint(3, 5))
    else:
        await state.update_data(msg_count=msg_count)


# --- ФУНКЦИЯ ЗАПУСКА: Включаем установку меню ---
async def main() -> None:
    # 1. Установка команд меню перед запуском
    await set_main_menu(bot) 
    # 2. Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
