import logging
import urllib.parse
import aiohttp
import asyncio
import re
import time
import html
import os
import json
import sys
import datetime
from fastapi import FastAPI
import uvicorn
from aiogram import Bot, Dispatcher, types, F, html
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    CallbackQuery,
    LabeledPrice,
    PreCheckoutQuery,
    InputMediaPhoto,
    Message,
    ChatMember
)
from aiogram.utils.markdown import hbold, hcode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from typing import Union, Optional, List, Dict, Any, Tuple

# ===================== КОНСТАНТЫ =====================
API_TOKEN = "7965257689:AAGEiEit2zlc0hIQC0MiYAjAgclOw8DzuO4"
ADMIN_ID = 750638552
CHANNEL_ID = -1002712232742

PAYMENT_PROVIDER_TOKEN = ""
IMAGE_URL = "https://image.pollinations.ai/prompt/"
TEXT_URL = "https://text.pollinations.ai/prompt/"
PAYMENT_ADMIN = "@telichko_a"
DB_FILE = "users_db.json"
LOG_FILE = "bot_errors.log"

# Константы
IMAGE_COST = 5
AVATAR_COST = 6
LOGO_COST = 3
IMPROVE_COST = 10
TEXT_COST_PER_100_WORDS = 1
MAX_IMAGE_COUNT = 8
MAX_CONTEXT_LENGTH = 4000
MAX_CAPTION_LENGTH = 1000
REFERRAL_BONUS = 20
START_BALANCE_STARS = 50
WITHDRAW_MIN = 500
MAX_RETRIES = 5
RETRY_DELAY = 1.5
MAX_PROMPT_LENGTH = 2000
MAX_MESSAGE_LENGTH = 4000
SESSION_TIMEOUT = 300
DAILY_BONUS = 3
SYSTEM_PROMPT = "Ты — полезный ИИ-ассистент. Отвечай точно и информативно."

# ===================== ИНИЦИАЛИЗАЦИЯ =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ===================== МОДЕЛИ ДАННЫХ =====================
class UserState:
    MAIN_MENU = "main_menu"
    GENERATE_MENU = "generate_menu"
    PROFILE_MENU = "profile_menu"
    IMAGE_GEN = "image_gen"
    TEXT_GEN = "text_gen"
    AVATAR_GEN = "avatar_gen"
    LOGO_GEN = "logo_gen"
    PREMIUM_INFO = "premium_info"
    SHOP = "shop"
    REFERRAL = "referral"
    BALANCE = "balance"
    IMAGE_OPTIONS = "image_options"
    AVATAR_OPTIONS = "avatar_options"
    LOGO_OPTIONS = "logo_options"
    IMAGE_IMPROVE = "image_improve"
    PAYMENT_PROCESSING = "payment_processing"
    ACTIVATE_PROMO = "activate_promo"
    SUPPORT = "support"
    IMAGE_COUNT_SELECT = "image_count_select"
    IMAGE_MODEL_SELECT = "image_model_select"
    TEXT_MODEL_SELECT = "text_model_select"
    MODEL_SELECT = "model_select"
    CHECK_SUBSCRIPTION = "check_subscription"
    DAILY_BONUS = "daily_bonus"
    CLEAR_CONTEXT = "clear_context"

class GenerationModel:
    def __init__(self, key: str, name: str, description: str, cost_multiplier: float, 
                 prompt: str = "", premium_only: bool = False):
        self.key = key
        self.name = name
        self.description = description
        self.cost_multiplier = cost_multiplier
        self.prompt = prompt
        self.premium_only = premium_only

# Модели ИИ
IMAGE_MODELS = {
    "dalle3": GenerationModel(
        "dalle3", "🖼️ DALL·E 3", 
        "Новейшая модель от OpenAI с фотографическим качеством", 1.0,
        "masterpiece, best quality, 8K resolution, cinematic lighting, ultra-detailed, sharp focus"
    ),
    "midjourney": GenerationModel(
        "midjourney", "🎨 Midjourney V6", 
        "Лидер в художественной генерации с уникальным стилем", 1.2,
        "masterpiece, intricate details, artistic composition, vibrant colors, atmospheric perspective, trending on artstation"
    ),
    "stablediff": GenerationModel(
        "stablediff", "⚡ Stable Diffusion XL", 
        "Открытая модель с быстрой генерацией и высокой кастомизацией", 0.8,
        "photorealistic, ultra HD, 32k, detailed texture, realistic lighting, DSLR quality"
    ),
    "firefly": GenerationModel(
        "firefly", "🔥 Adobe Firefly", 
        "Оптимизирована для профессионального дизайна и коммерческого использования", 1.1,
        "commercial quality, professional design, clean composition, vector art, modern aesthetics, brand identity"
    ),
    "deepseek": GenerationModel(
        "deepseek", "🤖 DeepSeek Vision", 
        "Экспериментальная модель с акцентом на технологичные образы", 0.9,
        "futuristic, cyberpunk, neon glow, holographic elements, sci-fi aesthetics, digital art"
    ),
    "playground": GenerationModel(
        "playground", "🎮 Playground v2.5", 
        "Художественная модель с уникальным стилем", 1.0,
        "dynamic composition, vibrant palette, artistic brushwork, impressionist style, emotional impact"
    )
}

TEXT_MODELS = {
    "gpt4": GenerationModel(
        "gpt4", "🧠 GPT-4 Turbo", 
        "Самый мощный текстовый ИИ от OpenAI", 1.0,
        "Ты - продвинутый ИИ-ассистент. Отвечай точно, информативно и креативно."
    ),
    "claude": GenerationModel(
        "claude", "🤖 Claude 3 Opus", 
        "Модель с самым большим контекстом и аналитическими способностями", 1.3,
        "Ты - полезный, честный и безвредный ассистент. Отвечай подробно и обстоятельно."
    ),
    "gemini": GenerationModel(
        "gemini", "💎 Gemini Pro", 
        "Мультимодальная модель от Google с интеграцией сервисов", 0.9,
        "Ты - многофункциональный ассистент Google. Отвечай кратко и по существу."
    ),
    "mixtral": GenerationModel(
        "mixtral", "🌀 Mixtral 8x7B", 
        "Открытая модель с лучшим соотношением скорости и качества", 0.7,
        "Ты - эксперт в различных областях знаний. Отвечай профессионально и точно."
    ),
    "llama3": GenerationModel(
        "llama3", "🦙 Llama 3 70B", 
        "Новейшая открытая модель от Meta с улучшенными возможностями", 0.8,
        "Ты - дружелюбный и креативный ассистент. Отвечай с юмором и творческим подходом."
    ),
    "claude_sonnet_4": GenerationModel(
        "claude_sonnet_4", "🧠 Claude Sonnet 4", 
        "Экспертный уровень аналитики", 1.5,
        "Ты - продвинутый ИИ Claude 4. Отвечай как профессиональный консультант: анализируй проблему, предлагай решения, предупреждай о рисках. Будь максимально полезным.",
        True
    ),
    "gemini_2_5": GenerationModel(
        "gemini_2_5", "💎 Google Gemini 2.5", 
        "Максимально практичные ответы", 1.4,
        "Ты - Gemini, ИИ нового поколения. Отвечай кратко, но содержательно. Используй маркированные списки для структуры. Всегда предлагай практические шаги.",
        True
    ),
    "grok_3": GenerationModel(
        "grok_3", "🚀 xAI Grok 3", 
        "Технически точно с юмором", 1.2,
        "Ты - Grok, ИИ с чувством юмора. Отвечай информативно, но с долей иронии. Используй современные аналогии. Не будь занудой.",
        True
    ),
    "o3_mini": GenerationModel(
        "o3_mini", "⚡ OpenAI o3-mini", 
        "Сверхбыстрые и точные ответы", 0.9,
        "Ты - o3-mini, эксперт по эффективности. Отвечай максимально кратко, но содержательно. Используй тезисы. Избегай 'воды'.",
        True
    )
}

# Глобальные структуры данных
users_db = {}
referral_codes = {}
db_lock = asyncio.Lock()
BOT_USERNAME = ""

class User:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.stars = START_BALANCE_STARS
        self.referral_balance = 0
        self.referral_code = f"REF{user_id}{int(time.time()) % 10000}"
        self.invited_by = None
        self.state = UserState.CHECK_SUBSCRIPTION
        self.last_image_prompt = None
        self.last_image_url = None
        self.last_avatar_prompt = None
        self.last_avatar_url = None
        self.last_logo_prompt = None
        self.last_logo_url = None
        self.is_premium = False
        self.premium_expiry = None
        self.image_count = 1
        self.context = []
        self.context_active = False
        self.menu_stack = []
        self.last_text = ""
        self.last_interaction = time.time()
        self.image_model = "dalle3"
        self.text_model = "gpt4"
        self._modified = True
        self.has_subscribed = False
        self.last_daily_bonus = None
        self.pending_referral = None
        self.referral_used = False
        
    def mark_modified(self):
        self._modified = True
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "stars": self.stars,
            "referral_balance": self.referral_balance,
            "referral_code": self.referral_code,
            "invited_by": self.invited_by,
            "state": self.state,
            "last_image_prompt": self.last_image_prompt,
            "last_image_url": self.last_image_url,
            "last_avatar_prompt": self.last_avatar_prompt,
            "last_avatar_url": self.last_avatar_url,
            "last_logo_prompt": self.last_logo_prompt,
            "last_logo_url": self.last_logo_url,
            "is_premium": self.is_premium,
            "premium_expiry": self.premium_expiry,
            "image_count": self.image_count,
            "context": self.context,
            "context_active": self.context_active,
            "menu_stack": self.menu_stack,
            "last_text": self.last_text,
            "last_interaction": self.last_interaction,
            "image_model": self.image_model,
            "text_model": self.text_model,
            "has_subscribed": self.has_subscribed,
            "last_daily_bonus": self.last_daily_bonus,
            "pending_referral": self.pending_referral,
            "referral_used": self.referral_used
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        user = cls(data["user_id"])
        user.stars = data.get("stars", START_BALANCE_STARS)
        user.referral_balance = data.get("referral_balance", 0)
        user.referral_code = data.get("referral_code", f"REF{data['user_id']}{int(time.time()) % 10000}")
        user.invited_by = data.get("invited_by", None)
        user.state = data.get("state", UserState.CHECK_SUBSCRIPTION)
        user.last_image_prompt = data.get("last_image_prompt", None)
        user.last_image_url = data.get("last_image_url", None)
        user.last_avatar_prompt = data.get("last_avatar_prompt", None)
        user.last_avatar_url = data.get("last_avatar_url", None)
        user.last_logo_prompt = data.get("last_logo_prompt", None)
        user.last_logo_url = data.get("last_logo_url", None)
        user.is_premium = data.get("is_premium", False)
        user.premium_expiry = data.get("premium_expiry", None)
        user.image_count = data.get("image_count", 1)
        user.context = data.get("context", [])
        user.context_active = data.get("context_active", False)
        user.menu_stack = data.get("menu_stack", [])
        user.last_text = data.get("last_text", "")
        user.last_interaction = data.get("last_interaction", time.time())
        user.image_model = data.get("image_model", "dalle3")
        user.text_model = data.get("text_model", "gpt4")
        user.has_subscribed = data.get("has_subscribed", False)
        user.last_daily_bonus = data.get("last_daily_bonus", None)
        user.pending_referral = data.get("pending_referral", None)
        user.referral_used = data.get("referral_used", False)
        user._modified = False
        return user
        
    def can_make_request(self, cost: int = 0) -> bool:
        if self.is_premium:
            return True
        return self.stars >= cost
            
    def charge_request(self, cost: int = 0) -> bool:
        if self.is_premium:
            return True
            
        if self.stars >= cost:
            self.stars -= cost
            self.mark_modified()
            return True
        return False

    def add_context(self, role: str, content: str):
        if not self.is_premium:
            return
            
        content = content[:1000]
        self.context.append({"role": role, "content": content})
        total_length = sum(len(msg["content"]) for msg in self.context)
        
        while total_length > MAX_CONTEXT_LENGTH and len(self.context) > 1:
            removed = self.context.pop(0)
            total_length -= len(removed["content"])
        
        self.mark_modified()
        self.context_active = True
            
    def push_menu(self, menu_state: str, menu_data: dict = None):
        self.menu_stack.append({
            "state": menu_state,
            "data": menu_data or {}
        })
        self.mark_modified()
        
    def pop_menu(self) -> Optional[Dict[str, Any]]:
        if self.menu_stack:
            prev_menu = self.menu_stack.pop()
            self.mark_modified()
            return prev_menu
        return None

    def check_premium_status(self) -> bool:
        if self.is_premium and self.premium_expiry and self.premium_expiry < time.time():
            self.is_premium = False
            self.premium_expiry = None
            self.mark_modified()
            return False
        return self.is_premium
    
    def update_interaction(self):
        self.last_interaction = time.time()
        self.mark_modified()
        
    def can_claim_daily(self) -> bool:
        if not self.last_daily_bonus:
            return True
            
        last_date = datetime.datetime.fromtimestamp(self.last_daily_bonus).date()
        current_date = datetime.datetime.now().date()
        return last_date < current_date
        
    def claim_daily_bonus(self) -> int:
        self.stars += DAILY_BONUS
        self.last_daily_bonus = time.time()
        self.mark_modified()
        return DAILY_BONUS
        
    def clear_context(self):
        self.context = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.context_active = False
        self.mark_modified()

# ===================== УТИЛИТЫ =====================
async def load_db():
    global users_db, referral_codes
    try:
        users_db = {}
        referral_codes = {}
        
        if os.path.exists(DB_FILE):
            async with db_lock:
                with open(DB_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    users_db = {int(k): User.from_dict(v) for k, v in data.get('users', {}).items()}
                    referral_codes = data.get('referral_codes', {})
                    
                    for user_id, user in users_db.items():
                        if user.referral_code:
                            referral_codes[user.referral_code] = user_id
                    
                    logger.info("Database loaded successfully")
                    
        # Создаем пользователя для админа если его нет
        if ADMIN_ID not in users_db:
            admin_user = User(ADMIN_ID)
            admin_user.is_premium = True
            admin_user.premium_expiry = None
            admin_user.stars = 10000
            admin_user.has_subscribed = True
            users_db[ADMIN_ID] = admin_user
            admin_user.mark_modified()
            logger.info(f"Created admin user: {ADMIN_ID}")
        else:
            admin_user = users_db[ADMIN_ID]
            admin_user.is_premium = True
            admin_user.premium_expiry = None
            admin_user.has_subscribed = True
            admin_user.mark_modified()
            logger.info(f"Admin premium status set for {ADMIN_ID}")
            
    except Exception as e:
        logger.error(f"Error loading database: {e}")
        users_db = {}
        referral_codes = {}

async def save_db():
    try:
        async with db_lock:
            data = {
                'users': {k: v.to_dict() for k, v in users_db.items()},
                'referral_codes': referral_codes
            }
            
            with open(DB_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            for user in users_db.values():
                user._modified = False
                
            logger.info("Database saved")
    except Exception as e:
        logger.error(f"Error saving database: {e}")

async def get_user(user_id: int) -> User:
    if user_id in users_db:
        user = users_db[user_id]
        user.check_premium_status()
    else:
        user = User(user_id)
        users_db[user_id] = user
        referral_codes[user.referral_code] = user_id
        user.mark_modified()
    
    return users_db[user_id]

def detect_language(text: str) -> str:
    if re.search(r'[а-яА-Я]', text):
        return 'ru'
    return 'en'

def trim_caption(text: str, max_length: int = MAX_CAPTION_LENGTH) -> str:
    if len(text) > max_length:
        return text[:max_length-3] + "..."
    return text

def truncate_prompt(text: str, max_length: int = MAX_PROMPT_LENGTH) -> str:
    if len(text) > max_length:
        return text[:max_length-3] + "..."
    return text

def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> List[str]:
    return [text[i:i+max_length] for i in range(0, len(text), max_length)]

def clean_html(text: str) -> str:
    text = re.sub(r'<!?[^>]+>', '', text)
    replacements = {
        '<': '&lt;',
        '>': '&gt;',
        '&': '&amp;',
        '"': '&quot;'
    }
    for char, entity in replacements.items():
        text = text.replace(char, entity)
    text = re.sub(r'<\?.*?\?>', '', text)
    return text

def format_code_blocks(text: str) -> str:
    text = clean_html(text)
    text = re.sub(r'```(.*?)```', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    return text

async def fetch_with_retry(url: str, retries: int = MAX_RETRIES, delay: float = RETRY_DELAY) -> Optional[str]:
    for i in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    elif resp.status in [400, 401, 403, 404]:
                        logger.error(f"Client error {resp.status}: {url}")
                        return None
                    elif resp.status in [500, 502, 503, 504]:
                        logger.warning(f"Server error {resp.status}, retry {i+1}/{retries}")
                        await asyncio.sleep(delay)
                    else:
                        logger.warning(f"Unexpected status {resp.status}, retry {i+1}/{retries}")
                        await asyncio.sleep(delay)
        except (aiohttp.ClientConnectionError, aiohttp.ServerDisconnectedError) as e:
            logger.warning(f"Connection error (attempt {i+1}/{retries}): {e}")
            await asyncio.sleep(delay)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"Request error (attempt {i+1}/{retries}): {e}")
            await asyncio.sleep(delay)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            break
    logger.error(f"Failed after {retries} attempts: {url}")
    return None

async def safe_send_photo(
    message: Message, 
    photo: str, 
    caption: str, 
    reply_markup: InlineKeyboardMarkup,
    max_retries: int = 3
) -> Optional[types.Message]:
    for attempt in range(max_retries):
        try:
            return await message.answer_photo(
                photo=photo,
                caption=caption,
                reply_markup=reply_markup
            )
        except TelegramBadRequest as e:
            if "failed to get HTTP URL content" in str(e) and attempt < max_retries-1:
                logger.warning(f"Telegram download failed, retry {attempt+1}/{max_retries}")
                await asyncio.sleep(1)
            else:
                raise
    raise Exception(f"Failed to send photo after {max_retries} attempts")

async def translate_to_english(text: str) -> str:
    try:
        translation_prompt = f"Translate this to English without any additional text: {text}"
        result = await fetch_with_retry(f"{TEXT_URL}{urllib.parse.quote(translation_prompt)}")
        return result.strip().strip('"') if result else text
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text

async def send_typing_effect(chat_id: int, duration: int = 5):
    end_time = time.time() + duration
    while time.time() < end_time:
        await bot.send_chat_action(chat_id, "typing")
        await asyncio.sleep(2.5)

async def improve_prompt(original_prompt: str) -> str:
    try:
        improvement_prompt = (
            "Улучши следующий промпт для генерации изображения, добавив: "
            "1. Конкретные детали визуализации "
            "2. Художественные дескрипторы "
            "3. Технические параметры качества\n\n"
            f"Исходный промпт: {original_prompt}"
        )
        result = await fetch_with_retry(f"{TEXT_URL}{urllib.parse.quote(improvement_prompt)}")
        return result.strip().strip('"') if result else original_prompt
    except Exception as e:
        logger.error(f"Prompt improvement error: {e}")
        return original_prompt

def count_words(text: str) -> int:
    words = re.findall(r'\b\w+\b', text)
    return len(words)

# ===================== КЛАВИАТУРЫ =====================
def create_keyboard(
    buttons: List[Union[Tuple[str, str], List[Tuple[str, str]]]],
    back_button: bool = False,
    home_button: bool = False,
    cancel_button: bool = False
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    for row in buttons:
        if isinstance(row, list):
            for btn in row:
                builder.button(text=btn[0], callback_data=btn[1])
            builder.adjust(len(row))
        else:
            builder.button(text=row[0], callback_data=row[1])
    
    if back_button:
        builder.button(text="🔙 Назад", callback_data="back")
    if home_button:
        builder.button(text="🏠 Главное", callback_data="home")
    if cancel_button:
        builder.button(text="❌ Отмена", callback_data="cancel")
    
    return builder.as_markup()

def main_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = [
        [("🛠️ Генерация", "generate_menu")],
        [("👤 Профиль", "profile_menu")],
        [("💎 Премиум", "premium_info")],
        [("🎁 Ежедневный бонус", "daily_bonus")]
    ]
    return create_keyboard(buttons)

def generate_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("📝 Текст", "gen_text")],
        [("🎨 Изображение", "gen_image")],
        [("👤 Аватар", "gen_avatar")],
        [("🖼️ Логотип", "gen_logo")],
        [("🤖 Модели ИИ", "model_select")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons)

def profile_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("💰 Баланс", "balance_info")],
        [("🛒 Магазин", "shop")],
        [("👥 Рефералы", "referral_info")],
        [("🆘 Поддержка", "support")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons)

def shop_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("⭐ 30 Звезд", "buy_stars30")],
        [("⭐ 50 Звезд", "buy_stars50")],
        [("⭐ 150 Звезд", "buy_stars150")],
        [("⭐ 500 Звезд", "buy_stars500")],
        [("💎 Премиум 1 мес", "buy_premium_month")],
        [("💎 Премиум навсегда", "buy_premium_forever")],
        [("🏠 Главное меню", "home"), ("❌ Отмена", "cancel")]
    ]
    return create_keyboard(buttons)

def image_options_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    buttons.append([("✨ Улучшить", "improve_image")])
    buttons.append([("🔄 Сгенерить снова", "regenerate_image"), ("🏠 Главное", "home")])
    return create_keyboard(buttons)

def avatar_options_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🔄 Сгенерить снова", "regenerate_avatar")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons)

def logo_options_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🔄 Сгенерить снова", "regenerate_logo")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons)

def text_options_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    buttons.append([("🔄 Сгенерить снова", "regenerate_text"), ("📄 Увеличить", "extend_text")])
    buttons.append([("✍️ Перефразировать", "rephrase_text")])
    
    if user.context_active:
        buttons.append([("🧹 Очистить контекст", "clear_context")])
    
    buttons.append([("🏠 Главное", "home")])
    return create_keyboard(buttons)

def premium_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🛒 Перейти в магазин", "shop")],
        [("🎁 Активировать промокод", "activate_promo")],
        [("👥 Реферальная система", "referral_info")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons)

def image_count_keyboard() -> InlineKeyboardMarkup:
    buttons = [[(str(i), f"img_count_{i}") for i in range(1, MAX_IMAGE_COUNT + 1)]]
    buttons.append([("🏠 Главное", "home")])
    return create_keyboard(buttons)

def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное", callback_data="home")]]
    )

def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    )

def subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/neurogptpro")],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")]
        ]
    )

def pay_keyboard(amount: int, currency: str = "⭐") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"💳 Оплатить {amount} {currency}", pay=True)
    builder.button(text="🆘 Поддержка", url=f"tg://user?username={PAYMENT_ADMIN[1:]}")
    builder.button(text="🏠 Главное меню", callback_data="home")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1, 2, 1)
    return builder.as_markup()

def balance_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🔄 Обновить", "refresh_balance"), ("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons)

def referral_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("💸 Вывести средства", "withdraw_referral")],
        [("🎁 Активировать промокод", "activate_promo")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons)

def model_select_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🖼️ Для изображений", "image_model_select")],
        [("📝 Для текста", "text_model_select")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons)

def image_models_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    for key, model in IMAGE_MODELS.items():
        # Для выбранной модели используем другой эмодзи
        if user.image_model == key:
            buttons.append([(f"✅ {model.name}", f"image_model_{key}")])
        else:
            buttons.append([(model.name, f"image_model_{key}")])
    
    buttons.append([("🔙 Назад", "model_select")])
    return create_keyboard(buttons)

def text_models_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    for key, model in TEXT_MODELS.items():
        if model.premium_only and not user.is_premium:
            # Показываем премиум модели, но с иконкой замка
            buttons.append([(f"🔒 {model.name} (премиум)", "premium_required")])
        else:
            if user.text_model == key:
                buttons.append([(f"✅ {model.name}", f"text_model_{key}")])
            else:
                buttons.append([(model.name, f"text_model_{key}")])
    
    buttons.append([("🔙 Назад", "model_select")])
    return create_keyboard(buttons)

# ===================== АНИМАЦИИ И УВЕДОМЛЕНИЯ =====================
async def animate_loading(message: Message, text: str, duration: float = 1.5) -> Message:
    msg = await message.answer(f"⏳ {text}")
    await asyncio.sleep(duration)
    return msg

async def animate_error(message: Message, text: str) -> Message:
    msg = await message.answer(f"❌ {text}")
    await asyncio.sleep(1)
    return msg

async def animate_success(message: Message, text: str) -> Message:
    msg = await message.answer(f"✅ {text}")
    await asyncio.sleep(1)
    return msg

async def animate_progress(message: Message, text: str, progress: float):
    bar_length = 10
    filled = int(progress * bar_length)
    bar = '🟩' * filled + '⬜️' * (bar_length - filled)
    try:
        await message.edit_text(f"⏳ {text}\n{bar} {int(progress*100)}%")
    except TelegramBadRequest:
        pass

async def safe_edit_message(
    callback: CallbackQuery, 
    text: str, 
    reply_markup: InlineKeyboardMarkup = None, 
    parse_mode: str = "HTML"
):
    try:
        if callback.message.text:
            await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        elif callback.message.caption:
            await callback.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        logger.warning(f"Message edit failed: {e}, sending new message")
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)

# ===================== ФОРМАТИРОВАНИЕ =====================
def format_balance(user: User) -> str:
    user.check_premium_status()
    
    daily_status = "✅ Доступен" if user.can_claim_daily() else "❌ Уже получен"
    premium_status = "Активен" if user.is_premium else "Неактивен"
    
    text = (
        f"💰 <b>ВАШ БАЛАНС</b>\n"
        f"══════════════════\n"
        f"⭐ Звезды: {hbold(user.stars)}\n"
        f"🎁 Ежедневный бонус: {daily_status}\n"
        f"💎 Премиум: {premium_status}\n"
        f"══════════════════\n"
    )
    
    if user.is_premium and user.premium_expiry:
        days_left = max(0, int((user.premium_expiry - time.time()) / (24 * 3600)))
        text += f"💎 Премиум активен! Осталось: {days_left} дней\n"
    elif user.is_premium:
        text += f"💎 Премиум активен (Навсегда)\n"
    else:
        text += (
            f"ℹ️ Премиум дает безлимитную генерацию контента\n"
            f"══════════════════"
        )
        
    return text

def format_premium_info(user: User) -> str:
    if user.is_premium:
        status = "Осталось: "
        if user.premium_expiry:
            days_left = max(0, int((user.premium_expiry - time.time()) / (24 * 3600)))
            status += f"{days_left} дней"
        else:
            status = "НАВСЕГДА"
        
        text = (
            f"💎 <b>ПРЕМИУМ ПОДПИСКА АКТИВНА!</b>\n"
            f"══════════════════\n"
            f"⏳ {status}\n\n"
            f"✨ <b>Преимущества:</b>\n"
            f"• 🎨 Безлимитная генерация изображений\n"
            f"• 👤 Безлимитная генерация аватаров\n"
            f"• 🖼️ Безлимитная генерация логотипов\n"
            f"• 📝 Безлимитная генерация текста\n"
            f"• 🧠 Расширенный контекст\n"
            f"• 🖼️ Генерация до 8 вариантов\n"
            f"• 🤖 Эксклюзивные модели ИИ\n"
            f"══════════════════"
        )
    else:
        text = (
            f"💎 <b>ПРЕМИУМ ПОДПИСКА</b>\n"
            f"══════════════════\n"
            f"✨ <b>Преимущества:</b>\n"
            f"• 🎨 Безлимитная генерация изображений\n"
            f"• 👤 Безлимитная генерация аватаров\n"
            f"• 🖼️ Безлимитная генерация логотипов\n"
            f"• 📝 Безлимитная генерация текста\n"
            f"• 🧠 Расширенный контекст\n"
            f"• 🖼️ Генерация до 8 вариантов\n"
            f"• 🤖 Эксклюзивные модели ИИ\n\n"
            f"💡 <b>Для активации премиума приобретите подписку в магазине</b>\n"
            f"══════════════════"
        )
    return text

def format_generation_cost(model: GenerationModel, base_cost: int, is_premium: bool) -> str:
    cost = int(base_cost * model.cost_multiplier)
    if is_premium:
        return "💎 Безлимит (премиум)"
    return f"💎 Стоимость: {cost} ⭐"

def format_model_info(model: GenerationModel) -> str:
    return f"{model.name}\n{model.description}\n💰 Множитель стоимости: {model.cost_multiplier}x"

# ===================== ОБРАБОТКА МЕНЮ =====================
async def handle_text_gen(callback: CallbackQuery, user: User):
    model = TEXT_MODELS[user.text_model]
    base_cost = int(TEXT_COST_PER_100_WORDS * model.cost_multiplier)
    cost_text = format_generation_cost(model, TEXT_COST_PER_100_WORDS, user.is_premium)
    
    await safe_edit_message(
        callback, 
        "📝 <b>Генерация текста</b>\n"
        "══════════════════\n"
        f"🤖 Модель: {model.name}\n\n"
        "🔍 <b>Отправьте ваш запрос:</b>\n"
        f"{cost_text}\n"
        f"⚠️ Максимум {MAX_PROMPT_LENGTH} символов\n"
        f"══════════════════",
        reply_markup=cancel_keyboard()
    )

async def show_menu(callback: CallbackQuery, user: User):
    user.update_interaction()
    logger.info(f"Showing menu for state: {user.state}")
    
    menu_handlers = {
        UserState.MAIN_MENU: handle_main_menu,
        UserState.GENERATE_MENU: handle_generate_menu,
        UserState.PROFILE_MENU: handle_profile_menu,
        UserState.IMAGE_GEN: handle_image_gen,
        UserState.TEXT_GEN: handle_text_gen,  # ДОБАВЛЕНО
        UserState.AVATAR_GEN: handle_avatar_gen,
        UserState.LOGO_GEN: handle_logo_gen,
        UserState.PREMIUM_INFO: handle_premium_info,
        UserState.SHOP: handle_shop,
        UserState.SUPPORT: handle_support,
        UserState.REFERRAL: handle_referral,
        UserState.ACTIVATE_PROMO: handle_activate_promo,
        UserState.BALANCE: handle_balance,
        UserState.IMAGE_COUNT_SELECT: handle_image_count_select,
        UserState.IMAGE_MODEL_SELECT: handle_image_model_select,
        UserState.MODEL_SELECT: handle_model_select,
        UserState.TEXT_MODEL_SELECT: handle_text_model_select
    }
    
    handler = menu_handlers.get(user.state)
    if handler:
        logger.info(f"Calling handler for state {user.state}")
        await handler(callback, user)
    else:
        logger.warning(f"No handler for state {user.state}")
        await callback.message.answer("🏠 <b>Главное меню</b>\n══════════════════", reply_markup=main_keyboard(user))

async def handle_main_menu(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "🌟 <b>Главное меню</b>\n"
        "══════════════════\n"
        "Выберите действие:",
        reply_markup=main_keyboard(user)
    )

async def handle_generate_menu(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "🚀 <b>Генерация контента</b>\n"
        "══════════════════\n"
        "Выберите тип:",
        reply_markup=generate_menu_keyboard()
    )

async def handle_profile_menu(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "👤 <b>Ваш профиль</b>\n"
        "══════════════════\n"
        "Выберите действие:",
        reply_markup=profile_menu_keyboard()
    )

async def handle_image_gen(callback: CallbackQuery, user: User):
    model = IMAGE_MODELS[user.image_model]
    base_cost = int(IMAGE_COST * model.cost_multiplier)
    cost_text = format_generation_cost(model, IMAGE_COST, user.is_premium)
    
    await safe_edit_message(
        callback, 
        "🎨 <b>Генерация изображения</b>\n"
        "══════════════════\n"
        f"🤖 Модель: {model.name}\n\n"
        "🔍 <b>Отправьте описание изображения:</b>\n"
        "Примеры:\n"
        "• Космический корабль в стиле киберпанк\n"
        "• Реалистичный портрет кота\n\n"
        f"{cost_text}\n"
        f"⚠️ Максимум {MAX_PROMPT_LENGTH} символов\n"
        f"══════════════════",
        reply_markup=cancel_keyboard()
    )

async def handle_image_count_select(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "🎨 <b>Генерация изображения (премиум)</b>\n"
        "══════════════════\n"
        f"🤖 Модель: {IMAGE_MODELS[user.image_model].name}\n"
        "Выберите количество вариантов:",
        reply_markup=image_count_keyboard()
    )

async def handle_avatar_gen(callback: CallbackQuery, user: User):
    model = IMAGE_MODELS[user.image_model]
    base_cost = int(AVATAR_COST * model.cost_multiplier)
    cost_text = format_generation_cost(model, AVATAR_COST, user.is_premium)
    
    await safe_edit_message(
        callback, 
        "👤 <b>Генерация аватара</b>\n"
        "══════════════════\n"
        f"🤖 Модель: {model.name}\n\n"
        "🔍 <b>Отправьте описание аватара:</b>\n"
        "Примеры:\n"
        "• Девушка с розовыми волосами\n"
        "• Мужчина в стиле самурая\n\n"
        f"{cost_text}\n"
        f"⚠️ Максимум {MAX_PROMPT_LENGTH} символов\n"
        f"══════════════════",
        reply_markup=cancel_keyboard()
    )

async def handle_logo_gen(callback: CallbackQuery, user: User):
    model = IMAGE_MODELS[user.image_model]
    base_cost = int(LOGO_COST * model.cost_multiplier)
    cost_text = format_generation_cost(model, LOGO_COST, user.is_premium)
    
    await safe_edit_message(
        callback, 
        "🖼️ <b>Генерация логотипа</b>\n"
        "══════════════════\n"
        f"🤖 Модель: {model.name}\n\n"
        "🔍 <b>Отправьте описание логотипа:</b>\n"
        "Примеры:\n"
        "• Лого для IT компании\n"
        "• Значок для кафе\n\n"
        f"{cost_text}\n"
        f"⚠️ Максимум {MAX_PROMPT_LENGTH} символов\n"
        f"══════════════════",
        reply_markup=cancel_keyboard()
    )

async def handle_premium_info(callback: CallbackQuery, user: User):
    text = format_premium_info(user)
    reply_markup = premium_keyboard() if not user.is_premium else home_keyboard()
    await safe_edit_message(callback, text, reply_markup=reply_markup)

async def handle_shop(callback: CallbackQuery, user: User):
    text = f"🛒 <b>МАГАЗИН</b>\n══════════════════\n{format_balance(user)}\n══════════════════\nВыберите товар:"
    await safe_edit_message(callback, text, reply_markup=shop_keyboard())

async def handle_support(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "🆘 <b>ПОДДЕРЖКА</b>\n══════════════════\n"
        f"• По вопросам: {PAYMENT_ADMIN}\n"
        "• По оплате: @telichko_a\n"
        "• Предложения: @telichko_a\n\n"
        "Мы отвечаем в течение 24 часов.\n"
        "══════════════════",
        reply_markup=home_keyboard()
    )

async def handle_referral(callback: CallbackQuery, user: User):
    referral_link = f"https://t.me/NeuroAlliance_bot?start={user.referral_code}"
    await safe_edit_message(
        callback,
        f"👥 <b>РЕФЕРАЛЬНАЯ СИСТЕМА</b>\n══════════════════\n"
        f"🔗 Ваша ссылка:\n{hcode(referral_link)}\n"
        f"💎 За приглашенного:\n"
        f"• Вы получаете: {REFERRAL_BONUS} ⭐\n"
        f"• Друг получает: {START_BALANCE_STARS//2} ⭐\n\n"
        f"💰 Реферальный баланс: {hbold(user.referral_balance)} 💎\n"
        f"⚠️ Минимальный вывод: {WITHDRAW_MIN} 💎\n"
        f"══════════════════",
        reply_markup=referral_keyboard()
    )

async def handle_activate_promo(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "🎁 <b>АКТИВАЦИЯ ПРОМОКОДА</b>\n══════════════════\n"
        "🔑 Введите промокод:",
        reply_markup=cancel_keyboard()
    )

async def handle_balance(callback: CallbackQuery, user: User):
    text = format_balance(user)
    await safe_edit_message(callback, text, reply_markup=balance_keyboard())

async def handle_image_model_select(callback: CallbackQuery, user: User):
    text = "🤖 <b>Выберите модель для генерации изображений</b>\n══════════════════\n"
    
    # Создаем список доступных моделей
    model_list = []
    for key, model in IMAGE_MODELS.items():
        selected = " ✅" if user.image_model == key else ""
        model_list.append(f"{model.name}{selected}")
    
    text += "\n".join(model_list)
    await safe_edit_message(callback, text, reply_markup=image_models_keyboard(user))

async def handle_model_select(callback: CallbackQuery, user: User):
    current_image_model = IMAGE_MODELS[user.image_model].name
    current_text_model = TEXT_MODELS[user.text_model].name
    
    text = (
        "🤖 <b>Выберите тип модели</b>\n"
        "══════════════════\n"
        f"🖼️ Текущая модель изображений: {current_image_model}\n"
        f"📝 Текущая текстовая модель: {current_text_model}\n"
        "══════════════════"
    )
    
    await safe_edit_message(callback, text, reply_markup=model_select_keyboard())

async def handle_text_model_select(callback: CallbackQuery, user: User):
    text = "🤖 <b>Выберите модель для генерации текста</b>\n══════════════════\n"
    
    # Создаем список доступных моделей с учетом премиум статуса
    model_list = []
    for key, model in TEXT_MODELS.items():
        if model.premium_only and not user.is_premium:
            continue
            
        selected = " ✅" if user.text_model == key else ""
        model_list.append(f"{model.name}{selected}")
    
    text += "\n".join(model_list)
    
    # Добавляем информацию о премиум моделях
    if any(model.premium_only for model in TEXT_MODELS.values()):
        text += "\n\n🔒 Премиум-модели доступны только с подпиской"
    
    await safe_edit_message(callback, text, reply_markup=text_models_keyboard(user))

# ===================== ОБРАБОТЧИКИ КОМАНД =====================
@dp.callback_query(F.data == "back")
async def back_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    prev_menu = user.pop_menu()
    
    if prev_menu:
        user.state = prev_menu["state"]
        await show_menu(callback, user)
    else:
        user.state = UserState.MAIN_MENU
        await show_menu(callback, user)
    
    await callback.answer()

@dp.callback_query(F.data == "home")
async def home_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.state = UserState.MAIN_MENU
    user.menu_stack = []
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "cancel")
async def cancel_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.state = UserState.MAIN_MENU
    user.menu_stack = []
    await callback.message.answer("❌ Действие отменено", reply_markup=main_keyboard(user))
    await callback.answer()

@dp.callback_query(F.data == "check_subscription")
async def check_subscription_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    
    if await check_subscription(user.user_id):
        user.has_subscribed = True
        user.mark_modified()
        
        if user.pending_referral and not user.referral_used:
            await process_referral(user, user.pending_referral)
            user.pending_referral = None
            user.referral_used = True
        
        await callback.message.delete()
        await bot.send_message(
            user.user_id,
            "✅ Подписка подтверждена!",
            reply_markup=main_keyboard(user)
        )
    else:
        await callback.answer("❌ Вы все еще не подписаны! Пожалуйста, подпишитесь.", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data == "daily_bonus")
async def daily_bonus_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    if user.can_claim_daily():
        bonus = user.claim_daily_bonus()
        await callback.answer(f"🎁 Получено {bonus} звёзд!", show_alert=True)
        text = format_balance(user)
        await safe_edit_message(callback, text, reply_markup=balance_keyboard())
        await save_db()
    else:
        last_date = datetime.datetime.fromtimestamp(user.last_daily_bonus).strftime("%d.%m.%Y")
        await callback.answer(f"❌ Вы уже получали бонус сегодня ({last_date})", show_alert=True)

@dp.callback_query(F.data == "generate_menu")
async def process_generate_menu(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.GENERATE_MENU
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "profile_menu")
async def process_profile_menu(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.PROFILE_MENU
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "premium_info")
async def premium_info(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.PREMIUM_INFO
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "gen_image")
async def process_gen_image(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    if user.is_premium:
        user.state = UserState.IMAGE_COUNT_SELECT
    else:
        user.state = UserState.IMAGE_GEN
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "gen_avatar")
async def process_gen_avatar(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.AVATAR_GEN
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "gen_logo")
async def process_gen_logo(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.LOGO_GEN
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "gen_text")
async def process_gen_text(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.TEXT_GEN
    user.mark_modified()
    
    model = TEXT_MODELS[user.text_model]
    base_cost = int(TEXT_COST_PER_100_WORDS * model.cost_multiplier)
    cost_text = format_generation_cost(model, TEXT_COST_PER_100_WORDS, user.is_premium)
    
    await safe_edit_message(
        callback, 
        "📝 <b>Генерация текста</b>\n"
        "══════════════════\n"
        f"🤖 Модель: {model.name}\n\n"
        "🔍 <b>Отправьте ваш запрос:</b>\n"
        f"{cost_text}\n"
        f"⚠️ Максимум {MAX_PROMPT_LENGTH} символов\n"
        f"══════════════════",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "model_select")
async def process_model_select(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    logger.info(f"User {user.user_id} requested model selection")
    
    user.push_menu(user.state, {})
    user.state = UserState.MODEL_SELECT
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "image_model_select")
async def process_image_model_select(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    logger.info(f"User {user.user_id} selecting image model")
    
    user.push_menu(user.state, {})
    user.state = UserState.IMAGE_MODEL_SELECT
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "text_model_select")
async def process_text_model_select(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    logger.info(f"User {user.user_id} selecting text model")
    
    user.push_menu(user.state, {})
    user.state = UserState.TEXT_MODEL_SELECT
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data.startswith("image_model_"))
async def set_image_model(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    model_key = callback.data.split('_')[2]
    if model_key in IMAGE_MODELS:
        user.image_model = model_key
        user.mark_modified()
        model_name = IMAGE_MODELS[model_key].name
        await callback.answer(f"✅ Выбрана модель: {model_name}")
        
        # Возвращаемся в меню выбора моделей
        user.state = UserState.MODEL_SELECT
        user.mark_modified()
        await show_menu(callback, user)
    else:
        await callback.answer("❌ Неизвестная модель изображений")
        logger.error(f"Unknown image model: {model_key}")

@dp.callback_query(F.data.startswith("text_model_"))
async def set_text_model(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    model_key = callback.data.split('_')[2]
    model = TEXT_MODELS.get(model_key)
    
    if not model:
        await callback.answer("❌ Неизвестная текстовая модель")
        logger.error(f"Unknown text model: {model_key}")
        return
    
    if model.premium_only and not user.is_premium:
        await callback.answer("❌ Только для премиум пользователей!", show_alert=True)
        return
    
    user.text_model = model_key
    user.mark_modified()
    await callback.answer(f"✅ Выбрана модель: {model.name}")
    
    # Возвращаемся в меню выбора моделей
    user.state = UserState.MODEL_SELECT
    user.mark_modified()
    await show_menu(callback, user)

@dp.callback_query(F.data == "premium_required")
async def premium_required_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    text = (
        "🔒 <b>Премиум-модель</b>\n"
        "══════════════════\n"
        "Эта модель доступна только для пользователей с премиум-подпиской.\n\n"
        "💎 Премиум-подписка дает доступ:\n"
        "- К эксклюзивным мощным моделям\n"
        "- Безлимитной генерации контента\n"
        "- Приоритетной обработке запросов\n\n"
        "Оформить премиум можно в магазине."
    )
    
    await callback.answer("❌ Требуется премиум-подписка", show_alert=True)
    await safe_edit_message(callback, text, reply_markup=premium_keyboard())

@dp.callback_query(F.data.startswith("img_count_"))
async def process_image_count(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    count = int(callback.data.split('_')[2])
    user.image_count = count
    user.mark_modified()
    user.push_menu(user.state, {})
    user.state = UserState.IMAGE_GEN
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "balance_info")
async def show_balance(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.BALANCE
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "refresh_balance")
async def refresh_balance(callback: CallbackQuery):
    await show_balance(callback)

@dp.callback_query(F.data == "shop")
async def shop(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    user.push_menu(user.state, {})
    user.state = UserState.SHOP
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "referral_info")
async def referral_info(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.REFERRAL
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "withdraw_referral")
async def withdraw_referral(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    amount = user.referral_balance
    if amount < WITHDRAW_MIN:
        await callback.answer(
            f"❌ Минимальная сумма: {WITHDRAW_MIN} 💎\n"
            f"Ваш баланс: {amount} 💎",
            show_alert=True
        )
        return
    
    user.stars += amount
    user.referral_balance = 0
    user.mark_modified()
    
    await callback.answer(f"✅ {amount} 💎 переведены на баланс!")
    await show_menu(callback, user)
    await save_db()

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    # Исправлено: объединяем все части после первого подчеркивания
    item = '_'.join(callback.data.split('_')[1:])
    
    items = {
        "stars30": {
            "title": "30 Звезд",
            "description": "Пакет звезд для генерации контента",
            "currency": "XTR",
            "price": 30,
            "stars": 30
        },
        "stars50": {
            "title": "50 Звезд",
            "description": "Пакет звезд",
            "currency": "XTR",
            "price": 50,
            "stars": 50
        },
        "stars150": {
            "title": "150 Звезд",
            "description": "Большой пакет звезд",
            "currency": "XTR",
            "price": 150,
            "stars": 150
        },
        "stars500": {
            "title": "500 Звезд",
            "description": "Огромный пакет звезд",
            "currency": "XTR",
            "price": 500,
            "stars": 500
        },
        "premium_month": {
            "title": "Премиум 1 месяц",
            "description": "Премиум доступ на 30 дней",
            "currency": "XTR",
            "price": 600,
            "premium": True,
            "expiry": time.time() + 30 * 24 * 3600
        },
        "premium_forever": {
            "title": "Премиум навсегда",
            "description": "Постоянный премиум доступ",
            "currency": "XTR",
            "price": 1999,
            "premium": True,
            "expiry": None
        },
    }
    
    if item not in items:
        await callback.answer(f"❌ Товар недоступен: {item}", show_alert=True)
        return
    
    product = items[item]
    
    await callback.message.answer_invoice(
        title=product["title"],
        description=product["description"],
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency=product["currency"],
        prices=[LabeledPrice(label=product["title"], amount=product["price"])],
        payload=item,
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", pay=True)],
            [InlineKeyboardButton(text="🆘 Поддержка", url=f"tg://user?username={PAYMENT_ADMIN[1:]}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.SUPPORT
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "activate_promo")
async def activate_promo(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.ACTIVATE_PROMO
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "improve_image")
async def improve_image(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.IMAGE_IMPROVE
    user.mark_modified()
    
    if not user.last_image_prompt:
        await callback.answer("❌ Нет данных", show_alert=True)
        return
    
    cost = 0 if user.is_premium else IMPROVE_COST
    
    if not user.is_premium and user.stars < cost:
        await callback.answer(
            f"❌ Недостаточно звёзд!\nНужно: {cost} ⭐\nВаш баланс: {user.stars}",
            show_alert=True
        )
        return
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    processing_msg = await callback.message.answer("🪄 Улучшаю изображение...")
    
    try:
        improved_prompt = await improve_prompt(user.last_image_prompt)
        logger.info(f"Improved prompt: {user.last_image_prompt} -> {improved_prompt}")
        user.last_image_prompt = improved_prompt
        user.mark_modified()
        
        if not user.is_premium:
            user.stars -= cost
            user.mark_modified()
        
        if detect_language(improved_prompt) != 'en':
            translated_prompt = await translate_to_english(improved_prompt)
        else:
            translated_prompt = improved_prompt

        encoded_prompt = urllib.parse.quote(translated_prompt)
        image_url = f"{IMAGE_URL}{encoded_prompt}?nologo=true"
        
        await processing_msg.delete()
        
        caption = trim_caption(
            f"✨ <b>Улучшенный результат</b>\n══════════════════\n"
            f"🤖 Модель: {IMAGE_MODELS[user.image_model].name}\n"
            f"{'💎 Безлимит (премиум)' if user.is_premium else f'💎 Стоимость: {cost} ⭐'}\n"
            f"══════════════════"
        )
        
        result = await safe_send_photo(
            callback.message,
            image_url,
            caption,
            image_options_keyboard(user)
        )
        user.last_image_url = result.photo[-1].file_id
        user.mark_modified()
    except Exception as e:
        logger.error(f"Improve image error: {e}")
        await processing_msg.edit_text("⚠️ Ошибка при улучшении")
    finally:
        await save_db()

@dp.callback_query(F.data == "regenerate_image")
async def regenerate_image(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    if user.is_premium:
        user.state = UserState.IMAGE_COUNT_SELECT
    else:
        user.state = UserState.IMAGE_GEN
    user.mark_modified()
    await callback.answer("🔄 Выберите параметры заново")

@dp.callback_query(F.data == "regenerate_avatar")
async def regenerate_avatar(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.AVATAR_GEN
    user.mark_modified()
    await callback.answer("🔄 Выберите параметры заново")

@dp.callback_query(F.data == "regenerate_logo")
async def regenerate_logo(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.LOGO_GEN
    user.mark_modified()
    await callback.answer("🔄 Выберите параметры заново")

@dp.callback_query(F.data == "regenerate_text")
async def regenerate_text(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.TEXT_GEN
    user.mark_modified()
    await callback.answer("🔄 Отправьте новый запрос")

@dp.callback_query(F.data == "extend_text")
async def extend_text(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    if user.last_text:
        user.push_menu(user.state, {})
        user.state = UserState.TEXT_GEN
        user.mark_modified()
        await callback.message.answer("📝 Введите дополнительные детали:")
    else:
        await callback.answer("❌ Нет текста", show_alert=True)

@dp.callback_query(F.data == "rephrase_text")
async def rephrase_text(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    if user.last_text:
        user.push_menu(user.state, {})
        user.state = UserState.TEXT_GEN
        user.mark_modified()
        await callback.message.answer("✍️ Как перефразировать?")
    else:
        await callback.answer("❌ Нет текста", show_alert=True)

@dp.callback_query(F.data == "clear_context")
async def clear_context(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.clear_context()
    await callback.answer("🧹 Контекст очищен!", show_alert=True)
    
    # Обновляем сообщение
    text = (
        "📝 <b>Контекст очищен</b>\n"
        "══════════════════\n"
        "История диалога была сброшена.\n"
        "Следующий запрос будет обработан без учета предыдущих сообщений."
    )
    await safe_edit_message(callback, text, reply_markup=text_options_keyboard(user))

# ===================== ПРОВЕРКА ПОДПИСКИ =====================
async def check_subscription(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
        
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        logger.info(f"User {user_id} status: {member.status}")
        
        allowed_statuses = [
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER
        ]
        
        return member.status in allowed_statuses
    except TelegramBadRequest as e:
        if "bot is not a member" in str(e).lower():
            logger.critical("❌ БОТ НЕ ЯВЛЯЕТСЯ АДМИНИСТРАТОРОМ КАНАЛА! ❌")
            logger.critical("Добавьте бота как администратора в канал для проверки подписок")
        else:
            logger.error(f"Telegram error: {e}")
        return False
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return False

async def ensure_subscription(target: Union[CallbackQuery, Message], user: User) -> bool:
    if user.user_id == ADMIN_ID:
        return True
        
    subscribed = await check_subscription(user.user_id)
    
    if subscribed:
        user.has_subscribed = True
        user.mark_modified()
        
        if user.pending_referral and not user.referral_used:
            await process_referral(user, user.pending_referral)
            user.pending_referral = None
            user.referral_used = True
            
        return True
    
    logger.warning(f"User {user.user_id} is not subscribed to channel {CHANNEL_ID}")
    
    text = (
        "📢 Для использования бота необходимо подписаться на наш канал!\n"
        "👉 https://t.me/neurogptpro 👈\n\n"
        "После подписки нажмите кнопку ниже"
    )
    
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=subscribe_keyboard())
        await target.answer()
    else:
        await target.answer(text, reply_markup=subscribe_keyboard())
    
    return False

async def process_referral(user: User, ref_code: str):
    if ref_code != user.referral_code and ref_code in referral_codes and not user.referral_used:
        referrer_id = referral_codes[ref_code]
        
        if referrer_id != user.user_id and referrer_id in users_db:
            referrer = users_db[referrer_id]
            referrer.referral_balance += REFERRAL_BONUS
            referrer.stars += REFERRAL_BONUS
            referrer.mark_modified()
            
            user.invited_by = ref_code
            user.stars += START_BALANCE_STARS // 2
            user.referral_used = True
            user.mark_modified()
            
            try:
                await bot.send_message(
                    referrer_id, 
                    f"🎉 Новый пользователь по вашей ссылке! "
                    f"Ваш баланс пополнен на {REFERRAL_BONUS} ⭐"
                )
            except Exception:
                logger.warning(f"Failed to notify referrer {referrer_id}")

# ===================== ГЕНЕРАЦИЯ КОНТЕНТА =====================
async def generate_content(
    user: User,
    text: str,
    message: Message,
    content_type: str,
    base_cost: int,
    model: GenerationModel,
    options_keyboard: InlineKeyboardMarkup,
    prompt_field: str,
    url_field: str,
    description: str,
    example: str
):
    try:
        if not await ensure_subscription(message, user):
            return
            
        if len(text) > MAX_PROMPT_LENGTH:
            await animate_error(message, f"⚠️ Превышен лимит {MAX_PROMPT_LENGTH} символов")
            return
            
        setattr(user, prompt_field, text)
        user.last_text = ""
        user.mark_modified()
        user.update_interaction()
        
        processing_msg = await animate_loading(message, f"🪄 Генерирую {description}...")
        
        if detect_language(text) != 'en':
            translated_prompt = await translate_to_english(text)
            logger.info(f"Translated: {text} -> {translated_prompt}")
        else:
            translated_prompt = text
        
        enhanced_prompt = f"{translated_prompt}, {model.prompt}"
        
        cost = 0 if user.is_premium else int(base_cost * model.cost_multiplier)
        
        if not user.is_premium and user.stars < cost:
            await processing_msg.delete()
            await animate_error(
                message, 
                f"❌ <b>Недостаточно звёзд!</b>\n══════════════════\n"
                f"⭐ Нужно: {cost} ⭐\n"
                f"⭐ Ваш баланс: {user.stars}\n\n"
                f"══════════════════"
            )
            return
        
        # Для премиум-пользователей с несколькими изображениями
        if content_type == "image" and user.is_premium and user.image_count > 1:
            count = min(user.image_count, MAX_IMAGE_COUNT)
            images = []
            
            for i in range(count):
                variant_prompt = f"{enhanced_prompt} --variant {i+1}"
                encoded_prompt = urllib.parse.quote(variant_prompt)
                image_url = f"{IMAGE_URL}{encoded_prompt}?nologo=true"
                images.append(image_url)
            
            # Создаем медиагруппу
            media_group = []
            for i, img_url in enumerate(images):
                if i == 0:
                    caption = f"🎨 <b>{count} варианта</b>\n══════════════════\n"
                    caption += f"🤖 Модель: {model.name}\n"
                    caption += f"💎 Безлимит (премиум)\n"
                    caption += f"══════════════════"
                else:
                    caption = ""
                
                media_group.append(InputMediaPhoto(
                    media=img_url,
                    caption=trim_caption(caption) if caption else ""
                ))
                
                await animate_progress(processing_msg, f"Генерация {i+1}/{count}", (i+1)/count)
            
            await processing_msg.delete()
            sent_messages = await message.answer_media_group(media=media_group)
            setattr(user, url_field, sent_messages[0].photo[-1].file_id)
            
            # Отправляем клавиатуру отдельным сообщением
            await sent_messages[-1].answer(
                f"✅ {description.capitalize()} готовы!",
                reply_markup=options_keyboard
            )
        
        else:  # Одно изображение
            encoded_prompt = urllib.parse.quote(enhanced_prompt)
            image_url = f"{IMAGE_URL}{encoded_prompt}?nologo=true"
            
            if not user.is_premium:
                user.stars -= cost
                user.mark_modified()
            
            caption_text = trim_caption(
                f"{description.capitalize()} <b>Готово!</b>\n══════════════════\n"
                f"🤖 Модель: {model.name}\n"
                f"{'💎 Безлимит (премиум)' if user.is_premium else f'💎 Стоимость: {cost} ⭐'}\n"
                f"══════════════════"
            )
            
            await processing_msg.delete()
            result = await safe_send_photo(
                message,
                image_url,
                caption_text,
                options_keyboard
            )
            setattr(user, url_field, result.photo[-1].file_id)
            user.mark_modified()
            
            await animate_success(message, f"✅ {description.capitalize()} готов!")
    except aiohttp.ClientError as e:
        logger.error(f"Network error: {e}")
        await animate_error(message, "⚠️ Ошибка сети, попробуйте позже")
    except asyncio.TimeoutError:
        logger.error("Timeout during generation")
        await animate_error(message, "⌛ Таймаут при генерации")
    except Exception as e:
        logger.exception("Unhandled error in generation")
        await animate_error(message, f"⛔ Критическая ошибка: {str(e)}")
    finally:
        await save_db()

async def generate_text(user: User, text: str, message: Message):
    try:
        if not await ensure_subscription(message, user):
            return
            
        model = TEXT_MODELS[user.text_model]
        if model.premium_only and not user.is_premium:
            await animate_error(message, "❌ Эта модель доступна только для премиум пользователей")
            return
            
        if len(text) > MAX_PROMPT_LENGTH:
            await animate_error(message, f"⚠️ Превышен лимит {MAX_PROMPT_LENGTH} символов")
            return
            
        user.last_text = text
        user.last_image_prompt = ""
        user.mark_modified()
        user.update_interaction()
        
        processing_msg = await animate_loading(message, "🧠 Обрабатываю запрос...")
        
        # Инициализация контекста для премиум-пользователей
        if user.is_premium and not user.context:
            user.context = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ]
        
        if user.is_premium:
            user.add_context("user", text)
            full_prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in user.context])
        else:
            full_prompt = f"{SYSTEM_PROMPT}\n\nЗапрос: {text}"
        
        full_prompt = f"{model.prompt}\n\n{full_prompt}"
        full_prompt = truncate_prompt(full_prompt)
        
        await send_typing_effect(message.chat.id, duration=3)
        
        encoded_prompt = urllib.parse.quote(full_prompt)
        result = await fetch_with_retry(f"{TEXT_URL}{encoded_prompt}")
        
        if not result:
            raise Exception("Ошибка сервера генерации")
        
        # Форматируем с очисткой HTML
        formatted_result = format_code_blocks(result)
        
        input_words = count_words(text)
        output_words = count_words(formatted_result)
        total_words = input_words + output_words
        cost = (total_words // 100) + (1 if total_words % 100 > 0 else 0)
        cost = int(cost * model.cost_multiplier)
        
        if not user.is_premium and user.stars < cost:
            await processing_msg.delete()
            await animate_error(
                message, 
                f"❌ <b>Недостаточно звёзд!</b>\n══════════════════\n"
                f"⭐ Нужно: {cost} ⭐\n"
                f"⭐ Ваш баланс: {user.stars}\n\n"
                f"══════════════════"
            )
            return
        
        if not user.is_premium:
            user.stars -= cost
            user.mark_modified()
        elif user.is_premium:
            # Добавляем ответ ассистента в контекст
            user.add_context("assistant", result)
        
        await processing_msg.delete()
        
        # Разделяем сообщение на части
        messages = split_message(f"📝 <b>Результат:</b>\n══════════════════\n\n{formatted_result}")
        
        # Отправляем все части, кроме последней
        for msg_text in messages[:-1]:
            await message.answer(msg_text, parse_mode="HTML")
        
        # Отправляем последнюю часть
        last_msg = await message.answer(messages[-1], parse_mode="HTML")
        
        stats_text = f"✅ <b>Готово!</b>\n══════════════════\n"
        stats_text += f"🤖 Модель: {model.name}\n"
        
        if user.is_premium:
            stats_text += f"💎 Безлимит (премиум)\n"
        else:
            stats_text += f"⭐ Использовано звёзд: {cost}\n"
            stats_text += f"⭐ Остаток: {user.stars}\n"
        
        stats_text += "══════════════════"
        
        await last_msg.answer(
            stats_text,
            reply_markup=text_options_keyboard(user)
        )
        
        await animate_success(message, "✅ Текст готов!")
    except TelegramBadRequest as e:
        logger.error(f"HTML formatting error: {e}")
        # Пытаемся отправить без форматирования
        await processing_msg.delete()
        await message.answer("⚠️ Ошибка форматирования, отправляю текст без оформления:")
        await message.answer(result[:4000])
    except aiohttp.ClientError as e:
        logger.error(f"Network error: {e}")
        await animate_error(message, "⚠️ Ошибка сети, попробуйте позже")
    except asyncio.TimeoutError:
        logger.error("Timeout during text generation")
        await animate_error(message, "⌛ Таймаут при генерации")
    except Exception as e:
        logger.exception("Unhandled error in text generation")
        await animate_error(message, f"⛔ Критическая ошибка: {str(e)}")
    finally:
        await save_db()

async def process_promo_code(user: User, promo_code: str, message: Message):
    promo_code = promo_code.strip().upper()
    
    if promo_code == "FREESTARS":
        user.stars += 100
        text = "🎁 Активирован промокод! +100 ⭐"
    elif user.user_id == ADMIN_ID and promo_code == "ADMINFOREVER":
        user.is_premium = True
        user.premium_expiry = None
        user.stars += 1000
        text = "💎 Активирован VIP промокод!"
    else:
        text = "❌ Неверный промокод"
    
    user.state = UserState.MAIN_MENU
    await message.answer(text, reply_markup=main_keyboard(user))
    user.mark_modified()
    await save_db()

# ===================== ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ==================

@dp.message(Command("start", "help"))
async def send_welcome(message: Message):
    args = message.text.split()
    user = await get_user(message.from_user.id)
    user.menu_stack = []
    user.update_interaction()
    
    ref_code = args[1] if len(args) > 1 else None
    
    # Обработка реферального кода
    if ref_code and ref_code.startswith("REF"):
        if user.has_subscribed:
            await process_referral(user, ref_code)
        else:
            user.pending_referral = ref_code
            user.mark_modified()
    
    # Проверка подписки
    if not user.has_subscribed:
        if await check_subscription(user.user_id):
            user.has_subscribed = True
            user.mark_modified()
        else:
            user.state = UserState.CHECK_SUBSCRIPTION
            await message.answer(
                "📢 Для использования бота необходимо подписаться на наш канал!\n"
                "👉 https://t.me/neurogptpro 👈\n\n"
                "После подписки нажмите кнопку ниже",
                reply_markup=subscribe_keyboard()
            )
            return
    
    # Обработка реферального кода после подписки
    if ref_code and ref_code.startswith("REF") and not user.referral_used:
        await process_referral(user, ref_code)
    
    welcome_text = (
        f"✨ <b>Добро пожаловать, {html.quote(message.from_user.first_name)}!</b> ✨\n"
        f"══════════════════\n"
        "🚀 Ваш AI-ассистент для генерации контента:\n\n"
        "🎨 <b>Генерация изображений</b> - визуализирую любые идеи\n"
        "📝 <b>Текстовый контент</b> - пишу тексты, статьи, скрипты и программы\n"
        "💎 <b>Премиум</b> - безлимитная генерация изображений\n\n"
        f"🎁 <b>Стартовый бонус:</b> {START_BALANCE_STARS} ⭐\n"
        "<i>Используй для тестирования возможностей!</i>\n\n"
        f"══════════════════"
    )
    user.state = UserState.MAIN_MENU
    await message.answer(welcome_text, reply_markup=main_keyboard(user))
    await save_db()

@dp.message(Command("balance"))
async def balance_command(message: Message):
    user = await get_user(message.from_user.id)
    if not await ensure_subscription(message, user):
        return
    
    user.state = UserState.BALANCE
    text = format_balance(user)
    await message.answer(text, reply_markup=balance_keyboard())

@dp.message(F.text)
async def handle_message(message: Message):
    user = await get_user(message.from_user.id)
    text = message.text.strip()
    user.update_interaction()
    
    if not await ensure_subscription(message, user):
        return
        
    try:
        if user.state == UserState.IMAGE_GEN:
            await generate_content(
                user, text, message,
                "image", IMAGE_COST, IMAGE_MODELS[user.image_model],
                image_options_keyboard(user),
                "last_image_prompt", "last_image_url",
                "изображение", "изображения"
            )
            
        elif user.state == UserState.TEXT_GEN:
            await generate_text(user, text, message)
            
        elif user.state == UserState.AVATAR_GEN:
            await generate_content(
                user, text, message,
                "avatar", AVATAR_COST, IMAGE_MODELS[user.image_model],
                avatar_options_keyboard(),
                "last_avatar_prompt", "last_avatar_url",
                "аватар", "аватары"
            )
            
        elif user.state == UserState.LOGO_GEN:
            await generate_content(
                user, text, message,
                "logo", LOGO_COST, IMAGE_MODELS[user.image_model],
                logo_options_keyboard(),
                "last_logo_prompt", "last_logo_url",
                "логотип", "логотипы"
            )
            
        elif user.state == UserState.ACTIVATE_PROMO:
            await process_promo_code(user, text, message)
            
    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await animate_error(message, f"⚠️ <b>Ошибка:</b> {str(e)}")
    finally:
        await save_db()

# ===================== ПЛАТЕЖИ =====================
@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    user = await get_user(message.from_user.id)
    payload = message.successful_payment.invoice_payload
    
    items = {
        "stars30": {"stars": 30, "message": "✅ Куплено 30 ⭐"},
        "stars50": {"stars": 50, "message": "✅ Куплено 50 ⭐"},
        "stars150": {"stars": 150, "message": "✅ Куплено 150 ⭐"},
        "stars500": {"stars": 500, "message": "✅ Куплено 500 ⭐"},
        "premium_month": {
            "premium": True, 
            "expiry": time.time() + 30 * 24 * 60 * 60,
            "message": "💎 Премиум на 1 месяц активирован!",
        },
        "premium_forever": {
            "premium": True, 
            "expiry": None,
            "message": "💎 Премиум НАВСЕГДА активирован!",
        },
    }
    
    if payload in items:
        item = items[payload]
        text = item["message"]
        
        if "stars" in item:
            user.stars += item["stars"]
        elif "premium" in item:
            user.is_premium = True
            user.premium_expiry = item.get("expiry")
        
        user.mark_modified()
        await message.answer(text)
    else:
        await message.answer(f"Платеж получен, но товар не распознан: {payload}")
    
    await save_db()

@dp.message(Command("paysupport"))
async def pay_support_handler(message: Message):
    await message.answer(
        "Поддержка по платежам: @payment_admin\n\n"
        "Возврат средств возможен в течение 14 дней"
    )
# ... (предыдущий код без изменений до создания app) ...

# ===================== ФОНОВЫЕ ЗАДАЧИ =====================
async def auto_save_db():
    """Автоматическое сохранение базы данных каждые 5 минут"""
    while True:
        await asyncio.sleep(300)
        if any(user._modified for user in users_db.values()):
            await save_db()
            logger.info("Database auto-saved")

async def clean_inactive_sessions():
    """Очистка неактивных сессий"""
    while True:
        await asyncio.sleep(3600)  # Каждый час
        current_time = time.time()
        inactive_users = []
        
        for user_id, user in users_db.items():
            if current_time - user.last_interaction > SESSION_TIMEOUT:
                inactive_users.append(user_id)
        
        for user_id in inactive_users:
            if user_id != ADMIN_ID:  # Не удаляем админа
                del users_db[user_id]
                logger.info(f"Cleaned inactive session: {user_id}")
        
        await save_db()

async def self_pinger():
    """Регулярные ping-запросы для предотвращения сна сервиса"""
    RENDER_APP_URL = "https://aibot-plcn.onrender.com"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(RENDER_APP_URL, timeout=10) as response:
                    logger.info(f"Self-ping status: {response.status}")
        except Exception as e:
            logger.error(f"Self-ping failed: {str(e)}")
        await asyncio.sleep(600)  # 10 минут

# ===================== ОПРЕДЕЛЕНИЕ RUN_BOT =====================
async def run_bot():
    """Основная функция запуска бота"""
    try:
        # Инициализация
        await load_db()
        
        bot_info = await bot.get_me()
        logger.info(f"Bot @{bot_info.username} started")
        
        # Фоновые задачи
        asyncio.create_task(auto_save_db())
        asyncio.create_task(clean_inactive_sessions())
        
        # Очистка предыдущих обновлений
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Запуск бота
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        # Перезапуск через 30 секунд при ошибке
        await asyncio.sleep(30)
        asyncio.create_task(run_bot())

# ===================== LIFESPAN HANDLER =====================
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Запуск при старте
    asyncio.create_task(run_bot())
    asyncio.create_task(self_pinger())
    yield
    # Остановка при завершении
    # Закрываем сессию бота
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

# ===================== ENDPOINT ДЛЯ ПРОВЕРКИ =====================
@app.get("/")
async def health_check():
    return {
        "status": "ok",
        "bot": "active",
        "render": "keep-alive"
    }

# ... (остальной код без изменений) ...

# Удаляем дублирующиеся определения run_bot и self_pinger

# Удаляем блок с @app.on_event("startup"), потому что мы используем lifespan

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        app,  # Используем созданное приложение
        host="0.0.0.0",
        port=port,
        workers=1,
        loop="asyncio",
        timeout_keep_alive=60
    )
