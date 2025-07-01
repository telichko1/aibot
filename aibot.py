import telebot
import requests
import time
import threading
import queue
import logging
import html
import re
from datetime import datetime, timezone, timedelta
from telebot.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton,
    ReplyKeyboardRemove
)
from collections import defaultdict, deque

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("ai_assistant.log")
    ]
)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
TOKEN = "7965257689:AAGEiEit2zlc0hIQC0MiYAjAgclOw8DzuO4"
TEXT_GENERATION_URL = "https://text.pollinations.ai/openai"
PREMIUM_CHANNEL_ID = -1002712232742
PREMIUM_CHANNEL_LINK = "https://t.me/+5yZ8ZBXkHCY2Zjcy"

FREE_MODEL = "mistral-8x22b"
PREMIUM_MODELS = [
    "gpt-3.5-turbo", "claude-3-haiku", "gemini-pro",
    "llama-3-8b", "mixtral-8x7b", "claude-3-sonnet", 
    "gpt-4-turbo", "llama-3-70b", "mistral-8x22b"
]

# Системные промпты для разных ассистентов
ASSISTANTS = {
    "standard": "🤖 Стандартный",
    "programmer": "👨‍💻 Программист",
    "scientist": "🔬 Ученый",
    "writer": "✍️ Писатель",
    "designer": "🎨 Дизайнер",
    "marketer": "📈 Маркетолог",
    "teacher": "👨‍🏫 Учитель",
    "lawyer": "⚖️ Юрист",
    "psychologist": "🧠 Психолог",
    "analyst": "📊 Аналитик"
}

ASSISTANT_PROMPTS = {
    "standard": "Ты - профессиональный AI-ассистент. Отвечай точно, кратко и по существу.",
    "programmer": "Ты - эксперт-программист. Отвечай технически точно, предоставляй примеры кода там, где это уместно. Всегда оформляй код в markdown-блоки с указанием языка. Убедись, что код: 1. Полностью рабочий без дополнительных зависимостей 2. Содержит минимальный необходимый функционал 3. Имеет комментарии для ключевых частей",
    "scientist": "Ты - ученый. Отвечай научно обоснованно, приводи данные и исследования. Будь точным и объективным.",
    "writer": "Ты - профессиональный писатель. Отвечай творчески, используй богатый язык и литературные приемы. Формулируй мысли элегантно.",
    "designer": "Ты - дизайнер. Отвечай с фокусом на эстетику, пользовательский опыт и визуальное восприятие. Предлагай креативные решения.",
    "marketer": "Ты - маркетолог. Отвечай с фокусом на выгоды, УТП и конверсию. Используй убедительные формулировки.",
    "teacher": "Ты - учитель. Объясняй сложные концепции простыми словами. Приводи примеры и аналогии. Будь терпеливым и поддерживающим.",
    "lawyer": "Ты - юрист. Отвечай точно, ссылайся на нормативные акты. Предупреждай о рисках. Будь формальным и профессиональным.",
    "psychologist": "Ты - психолог. Отвечай с эмпатией, поддерживай и помогай решать проблемы. Задавай уточняющие вопросы.",
    "analyst": "Ты - аналитик данных. Отвечай с фокусом на метрики, тренды и выводы. Предоставляй структурированный анализ."
}

# --- Инициализация бота ---
bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=10)

# --- Хранилище состояния пользователей ---
user_context = defaultdict(lambda: {
    "model": FREE_MODEL,
    "assistant": "standard",
    "history": deque(maxlen=20),
    "last_interaction": time.time(),
    "premium": False,
    "premium_checked_at": 0,
    "premium_cache_duration": 600,
    "premium_until": None,
    "referrals": set(),
    "active_typing": {},
    "menu_stack": []
})

request_queue = queue.Queue()
edit_lock = threading.Lock()

# --- Вспомогательные функции ---
def get_current_datetime():
    return datetime.now(timezone.utc)

def get_model_name(model_id):
    names = {
        "gpt-3.5-turbo": "🤖 GPT-3.5",
        "claude-3-haiku": "🎨 Claude Haiku",
        "gemini-pro": "🌐 Gemini Pro",
        "llama-3-8b": "🦙 Llama 3",
        "mixtral-8x7b": "🧠 Mixtral",
        "claude-3-sonnet": "🎭 Claude Sonnet",
        "gpt-4-turbo": "🌟 GPT-4 Turbo",
        "llama-3-70b": "🧩 Llama 70B",
        "mistral-8x22b": "🐢 Mistral 8x22B"
    }
    return names.get(model_id, model_id)

def is_premium_active(ctx):
    now = get_current_datetime()
    if ctx["premium"]:
        return True
    if ctx["premium_until"] and now < ctx["premium_until"]:
        return True
    return False

def update_premium_status(user_id):
    ctx = user_context[user_id]
    now = get_current_datetime()

    if time.time() - ctx["premium_checked_at"] > ctx["premium_cache_duration"]:
        try:
            status = bot.get_chat_member(PREMIUM_CHANNEL_ID, user_id).status
            ctx["premium"] = status in ['member', 'administrator', 'creator']
            ctx["premium_checked_at"] = time.time()
        except Exception as e:
            logger.warning(f"Ошибка проверки подписки: {e}")
            ctx["premium"] = False

    if ctx["premium_until"] and now > ctx["premium_until"]:
        ctx["premium_until"] = None

    return is_premium_active(ctx)

def add_referral(referrer_id, new_user_id):
    if referrer_id == new_user_id:
        return
    referrer_ctx = user_context[referrer_id]
    if new_user_id in referrer_ctx["referrals"]:
        return
        
    referrer_ctx["referrals"].add(new_user_id)
    logger.info(f"Новый реферал: {referrer_id} → {new_user_id}")

    if len(referrer_ctx["referrals"]) >= 10:
        now = get_current_datetime()
        if referrer_ctx.get("premium_until") and referrer_ctx["premium_until"] > now:
            referrer_ctx["premium_until"] += timedelta(days=5)
        else:
            referrer_ctx["premium_until"] = now + timedelta(days=5)
        
        referrer_ctx["referrals"].clear()
        logger.info(f"Начислен премиум пользователю {referrer_id}")
        
        try:
            bot.send_message(referrer_id, "🎉 Вы получили премиум на 5 дней за 10 приглашенных!")
        except:
            pass

def clean_html(text: str) -> str:
    """Удаляет все HTML-теги из текста"""
    return re.sub(r'<[^>]+>', '', text)

def safe_format(text: str) -> str:
    """Идеальное форматирование для Telegram с сохранением код-блоков"""
    # Удаляем все HTML-теги из обычного текста
    text = clean_html(text)
    
    # Обработка код-блоков
    code_blocks = []
    def replace_code(match):
        language = match.group(1) or ""
        code = match.group(2).strip()
        # Очищаем и экранируем код
        code = clean_html(code)
        code = html.escape(code)
        code_blocks.append((language, code))
        return f"▸CODE_BLOCK_{len(code_blocks)-1}◂"
    
    # Ищем блоки кода
    text = re.sub(r"```(\w*)\n?([\s\S]+?)```", replace_code, text)
    
    # Восстанавливаем код-блоки
    for i, (lang, code) in enumerate(code_blocks):
        placeholder = f"▸CODE_BLOCK_{i}◂"
        lang_display = lang.upper() if lang else "КОД"
        text = text.replace(placeholder, f"<b>▸{lang_display}◂</b>\n<pre><code>{code}</code></pre>")
    
    # Простое форматирование
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    
    # Удаляем оставшиеся служебные символы
    text = text.replace('▸', '').replace('◂', '')
    
    return text

def create_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("💬 Новый запрос"),
        KeyboardButton("🛠 Сменить модель"),
        KeyboardButton("👨‍💻 Сменить ассистента"),
        KeyboardButton("💎 Премиум-статус"),
        KeyboardButton("👥 Рефералы"),
        KeyboardButton("📜 Показать историю"),
        KeyboardButton("♻️ Очистить историю"),
        KeyboardButton("ℹ️ Помощь")
    )
    return keyboard

def create_back_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("🔙 Назад"))
    return keyboard

def create_model_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for model in PREMIUM_MODELS:
        buttons.append(InlineKeyboardButton(get_model_name(model), callback_data=f"model_{model}"))
    for i in range(0, len(buttons), 2):
        row = buttons[i:i+2]
        keyboard.add(*row)
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_menu"))
    return keyboard

def create_assistant_keyboard(user_id):
    """Создает клавиатуру с ассистентами с учетом премиум-статуса"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []
    is_premium = update_premium_status(user_id)
    
    for key, name in ASSISTANTS.items():
        if key == "standard":
            buttons.append(InlineKeyboardButton(name, callback_data=f"assistant_{key}"))
        else:
            if is_premium:
                buttons.append(InlineKeyboardButton(name, callback_data=f"assistant_{key}"))
            else:
                buttons.append(InlineKeyboardButton(f"{name} 🔒", callback_data=f"assistant_locked_{key}"))
    
    for i in range(0, len(buttons), 2):
        row = buttons[i:i+2]
        keyboard.add(*row)
        
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_menu"))
    return keyboard

def create_premium_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔓 Получить премиум", url=PREMIUM_CHANNEL_LINK))
    keyboard.add(InlineKeyboardButton("🔄 Проверить статус", callback_data="check_premium"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_menu"))
    return keyboard

def safe_send(chat_id, text, **kwargs):
    try:
        # Разбиваем длинные сообщения
        if len(text) > 4096:
            parts = []
            while text:
                cutoff = 4096
                if len(text) > cutoff:
                    while cutoff > 0 and text[cutoff] not in (' ', '\n', '.', ',', ';'):
                        cutoff -= 1
                    if cutoff <= 0:
                        cutoff = 4096
                else:
                    cutoff = len(text)
                
                part = text[:cutoff]
                text = text[cutoff:]
                parts.append(part)
            
            # Отправляем части с индикацией
            for i, part in enumerate(parts):
                if i == 0:
                    part = f"{part}\n\n⏳ <b>Продолжение следует...</b>"
                elif i == len(parts) - 1:
                    part = f"📝 <b>Продолжение:</b>\n\n{part}"
                else:
                    part = f"📝 <b>Продолжение:</b>\n\n{part}\n\n⏳ <b>Продолжение следует...</b>"
                
                bot.send_message(chat_id, part, parse_mode="HTML", **kwargs)
                time.sleep(0.2)
            return None
        else:
            return bot.send_message(chat_id, text, parse_mode="HTML", **kwargs)
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        return None

def safe_edit(chat_id, message_id, text, **kwargs):
    try:
        if len(text) > 4096:
            text = text[:4000] + "\n... [сообщение обрезано]"
            
        with edit_lock:
            bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", **kwargs)
        return True
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" in str(e):
            return True
        if "can't parse entities" in str(e):
            fixed_text = re.sub(r'<[^>]+>', '', text)
            with edit_lock:
                bot.edit_message_text(fixed_text, chat_id, message_id)
            return True
        logger.error(f"Ошибка редактирования: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка редактирования: {e}")
        return False

def typing_effect(chat_id, message_id, full_text, user_id):
    """Ускоренный эффект печатания с HTML-форматированием"""
    ctx = user_context[user_id]
    ctx["active_typing"]["stop"] = False
    
    # Разбиваем текст на части
    parts = []
    current = ""
    buffer_size = 30
    
    for char in full_text:
        current += char
        if len(current) >= buffer_size:
            parts.append(current)
            current = ""
    if current:
        parts.append(current)
    
    # Отображаем текст постепенно
    displayed = ""
    start_time = time.time()
    
    for i, part in enumerate(parts):
        if ctx["active_typing"].get("stop", False):
            return
            
        new_text = displayed + part
        
        # Добавляем прогресс-бар
        progress = int((i+1) / len(parts) * 10)
        progress_bar = f"[{'■' * progress}{'□' * (10 - progress)}]"
        status = f"\n\n⏳ <b>Генерация...</b>\n<pre>{progress_bar}</pre> <code>{progress*10}%</code>"
        
        safe_edit(chat_id, message_id, new_text + status)
        time.sleep(0.02)
        
        displayed = new_text
    
    # Финальное обновление
    gen_time = time.time() - start_time
    model_name = get_model_name(ctx["model"])
    footer = f"\n\n<code>⏱ {gen_time:.1f}s │ 🧠 {model_name}</code>"
    safe_edit(chat_id, message_id, full_text + footer)
    ctx["active_typing"] = {}

def generate_ai_response(user_id, prompt):
    ctx = user_context[user_id]
    messages = []
    
    # Усиленный промпт для программиста
    if ctx["assistant"] == "programmer":
        prompt = f"{prompt}\n\nПожалуйста, предоставь полный работающий код с комментариями. Убедись, что код: 1. Корректно оформлен в markdown-блоки 2. Не содержит placeholder'ов 3. Решает поставленную задачу полностью"
    
    # Добавляем промпт выбранного ассистента
    assistant_prompt = ASSISTANT_PROMPTS.get(ctx["assistant"], ASSISTANT_PROMPTS["standard"])
    messages.append({"role": "system", "content": assistant_prompt})
    
    # Добавляем историю
    for i, msg in enumerate(ctx["history"]):
        role = "user" if i % 2 == 0 else "assistant"
        messages.append({"role": role, "content": msg})
    
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": ctx["model"],
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 3000,
        "top_p": 0.9
    }

    try:
        start_time = time.time()
        response = requests.post(TEXT_GENERATION_URL, json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()
        
        if "choices" in data and data["choices"]:
            answer = data["choices"][0]["message"]["content"]
            
            # Проверяем наличие кода
            if "```" not in answer and ctx["assistant"] == "programmer":
                answer = "⚠️ Код не обнаружен. Пожалуйста, повторите запрос.\n\n" + answer
            
            # Сохраняем в историю
            ctx["history"].append(prompt)
            ctx["history"].append(answer)
            ctx["last_interaction"] = time.time()
            
            # Форматируем и возвращаем
            return safe_format(answer)
        return "⚠️ Ошибка генерации ответа"
    except requests.exceptions.Timeout:
        return "⌛️ Превышено время ожидания ответа от сервера"
    except Exception as e:
        logger.error(f"Ошибка API: {e}")
        return "⚠️ Ошибка сервера, попробуйте позже"

# --- Обработчики команд ---
@bot.message_handler(commands=['start', 'menu'])
def start(message):
    user_id = message.from_user.id
    ctx = user_context[user_id]
    ctx["menu_stack"] = []

    # Обработка рефералов
    if "ref_" in message.text:
        try:
            referrer_id = int(message.text.split("ref_")[1])
            add_referral(referrer_id, user_id)
        except:
            pass

    ctx["premium"] = update_premium_status(user_id)
    if not ctx["premium"]:
        ctx["model"] = FREE_MODEL

    # Приветствие
    welcome = (
        f"✨ <b>Добро пожаловать, {message.from_user.first_name}!</b>\n\n"
        "Я — ваш персональный AI-ассистент нового поколения\n"
        f"🧠 Модель: <b>{get_model_name(ctx['model'])}</b>\n"
        f"👨‍💻 Ассистент: <b>{ASSISTANTS[ctx['assistant']]}</b>\n"
        f"💎 Статус: {'<b>Премиум</b> 🔓' if ctx['premium'] else 'Базовый 🔒'}\n\n"
        "Выберите действие:"
    )
    safe_send(message.chat.id, welcome, reply_markup=create_main_keyboard())

@bot.message_handler(func=lambda m: m.text == "💬 Новый запрос")
def new_query(message):
    user_context[message.from_user.id]["menu_stack"].append("query")
    safe_send(message.chat.id, "💬 Введите ваш запрос:", reply_markup=create_back_keyboard())

@bot.message_handler(func=lambda m: m.text == "🛠 Сменить модель")
def choose_model(message):
    user_id = message.from_user.id
    user_context[user_id]["menu_stack"].append("model")
    if not update_premium_status(user_id):
        safe_send(
            message.chat.id,
            "🚫 Доступно только для премиум пользователей",
            reply_markup=create_premium_keyboard()
        )
        return
    safe_send(message.chat.id, "🚀 Выберите AI-модель:", reply_markup=create_model_keyboard())

@bot.callback_query_handler(func=lambda c: c.data.startswith("model_"))
def set_model(call):
    user_id = call.from_user.id
    model = call.data[len("model_"):]
    
    if not update_premium_status(user_id) or model not in PREMIUM_MODELS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещен")
        return
        
    user_context[user_id]["model"] = model
    bot.edit_message_text(
        f"✅ Установлена модель: <b>{get_model_name(model)}</b>",
        call.message.chat.id, call.message.message_id
    )
    bot.answer_callback_query(call.id, f"Модель изменена на {get_model_name(model)}")

@bot.message_handler(func=lambda m: m.text == "👨‍💻 Сменить ассистента")
def choose_assistant(message):
    user_id = message.from_user.id
    user_context[user_id]["menu_stack"].append("assistant")
    safe_send(
        message.chat.id, 
        "👨‍💻 Выберите ассистента:", 
        reply_markup=create_assistant_keyboard(user_id)
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("assistant_"))
def set_assistant(call):
    user_id = call.from_user.id
    assistant_key = call.data[len("assistant_"):]
    
    # Обработка заблокированных ассистентов
    if assistant_key.startswith("locked_"):
        bot.answer_callback_query(
            call.id, 
            "🚫 Этот ассистент доступен только для премиум пользователей",
            show_alert=True
        )
        return
        
    if assistant_key not in ASSISTANTS:
        bot.answer_callback_query(call.id, "❌ Неизвестный ассистент")
        return
        
    # Проверка доступа для премиум-ассистентов
    if assistant_key != "standard" and not update_premium_status(user_id):
        bot.answer_callback_query(
            call.id, 
            "🚫 Этот ассистент доступен только для премиум пользователей",
            show_alert=True
        )
        return
        
    user_context[user_id]["assistant"] = assistant_key
    
    # Оптимизированное сообщение без лишних тегов
    assistant_name = ASSISTANTS[assistant_key]
    prompt_preview = ASSISTANT_PROMPTS[assistant_key][:50].replace('\n', ' ')
    response = (
        f"✅ Установлен ассистент: <b>{assistant_name}</b>\n"
        f"<i>{prompt_preview}...</i>"
    )
    
    bot.edit_message_text(
        response,
        call.message.chat.id, call.message.message_id
    )
    bot.answer_callback_query(call.id, "Ассистент изменен")

@bot.message_handler(func=lambda m: m.text == "💎 Премиум-статус")
def premium_info(message):
    user_id = message.from_user.id
    user_context[user_id]["menu_stack"].append("premium")
    ctx = user_context[user_id]
    update_premium_status(user_id)
    
    premium_status = "🔓 АКТИВЕН" if ctx["premium"] else "🔒 НЕАКТИВЕН"
    premium_expire = ""
    
    if ctx["premium_until"]:
        expire_date = ctx["premium_until"].strftime("%d.%m.%Y")
        premium_expire = f"\n⏳ Срок действия: <b>{expire_date}</b>"
    
    text = (
        "💎 <b>ПРЕМИУМ ДОСТУП</b>\n\n"
        f"<b>Статус:</b> {premium_status}{premium_expire}\n\n"
        "<b>Преимущества:</b>\n"
        "• Доступ к GPT-4 Turbo и Claude 3\n"
   
