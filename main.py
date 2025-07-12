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
import random
import string
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
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
    ChatMember,
    FSInputFile
)
from aiogram.utils.markdown import hbold, hcode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from typing import Union, Optional, List, Dict, Any, Tuple
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Gauge, Counter, Summary
from pydantic import BaseModel, ValidationError
from contextlib import asynccontextmanager

# ===================== КОНСТАНТЫ И НАСТРОЙКИ =====================
API_TOKEN = os.getenv("BOT_TOKEN", "7783817301:AAFxS4fXUTe9Q34NrP8110yvzZeBNIMmui4")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 0))

# Настройки генерации
MAX_IMAGE_COUNT = 8
MAX_PROMPT_LENGTH = 2000
MAX_MESSAGE_LENGTH = 4000
MAX_CONTEXT_LENGTH = 4000
IMAGE_COST = 5
AVATAR_COST = 6
LOGO_COST = 3
IMPROVE_COST = 10
TEXT_COST_PER_100_WORDS = 1
TEMPLATE_COST = 15

# Экономика
START_BALANCE_STARS = 50
REFERRAL_BONUS = 20
DAILY_BONUS = 3
WITHDRAW_MIN = 500
SESSION_TIMEOUT = 2592000  # 30 дней

# Системные настройки
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_TOKEN", "YOUR_PAYMENT_TOKEN")
IMAGE_URL = "https://image.pollinations.ai/prompt/"
TEXT_URL = "https://text.pollinations.ai/prompt/"
PAYMENT_ADMIN = "@telichko_a"
DB_FILE = "users_db.json"
LOG_FILE = "bot_errors.log"
PROMO_FILE = "promo_codes.json"
STATS_FILE = "bot_stats.json"
TEMPLATES_FILE = "templates.json"
ACHIEVEMENTS_FILE = "achievements.json"
SYSTEM_PROMPT = "Ты — полезный ИИ-ассистент. Отвечай точно и информативно."
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "admin123")

# Настройки логирования
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

# Инициализация бота
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ===================== МОДЕЛИ ДАННЫХ =====================
class GenerationModel(BaseModel):
    key: str
    name: str
    description: str
    cost_multiplier: float = 1.0
    prompt: str = ""
    premium_only: bool = False
    max_tokens: int = 2000
    temperature: float = 0.7

class Template(BaseModel):
    id: str
    name: str
    description: str
    prompt: str
    example: str
    category: str
    created_by: int
    created_at: str
    usage_count: int = 0

class Achievement(BaseModel):
    id: str
    name: str
    description: str
    condition: str
    reward: int
    icon: str

# Модели ИИ
IMAGE_MODELS = {
    "dalle3": GenerationModel(
        key="dalle3",
        name="🖼️ DALL·E 3", 
        description="Новейшая модель от OpenAI с фотографическим качеством", 
        cost_multiplier=1.0,
        prompt="masterpiece, best quality, 8K resolution, cinematic lighting, ultra-detailed, sharp focus"
    ),
    "midjourney": GenerationModel(
        key="midjourney",
        name="🎨 Midjourney V6", 
        description="Лидер в художественной генерации с уникальным стилем", 
        cost_multiplier=1.2,
        prompt="masterpiece, intricate details, artistic composition, vibrant colors, atmospheric perspective, trending on artstation"
    ),
    "stablediff": GenerationModel(
        key="stablediff",
        name="⚡ Stable Diffusion XL", 
        description="Открытая модель с быстрой генерацией и высокой кастомизацией", 
        cost_multiplier=0.8,
        prompt="photorealistic, ultra HD, 32k, detailed texture, realistic lighting, DSLR quality"
    ),
    "firefly": GenerationModel(
        key="firefly",
        name="🔥 Adobe Firefly", 
        description="Оптимизирована для профессионального дизайна и коммерческого использования", 
        cost_multiplier=1.1,
        prompt="commercial quality, professional design, clean composition, vector art, modern aesthetics, brand identity"
    ),
    "deepseek": GenerationModel(
        key="deepseek",
        name="🤖 DeepSeek Vision", 
        description="Экспериментальная модель с акцентом на технологичные образы", 
        cost_multiplier=0.9,
        prompt="futuristic, cyberpunk, neon glow, holographic elements, sci-fi aesthetics, digital art"
    ),
    "playground": GenerationModel(
        key="playground",
        name="🎮 Playground v2.5", 
        description="Художественная модель с уникальным стилем", 
        cost_multiplier=1.0,
        prompt="dynamic composition, vibrant palette, artistic brushwork, impressionist style, emotional impact"
    )
}

TEXT_MODELS = {
    "gpt4": GenerationModel(
        key="gpt4",
        name="🧠 GPT-4 Turbo", 
        description="Самый мощный текстовый ИИ от OpenAI", 
        cost_multiplier=1.0,
        prompt="Ты - продвинутый ИИ-ассистент. Отвечай точно, информативно и креативно."
    ),
    "claude": GenerationModel(
        key="claude",
        name="🤖 Claude 3 Opus", 
        description="Модель с самым большим контекстом и аналитическими способностями", 
        cost_multiplier=1.3,
        prompt="Ты - полезный, честный и безвредный ассистент. Отвечай подробно и обстоятельно.",
        max_tokens=4000
    ),
    "gemini": GenerationModel(
        key="gemini",
        name="💎 Gemini Pro", 
        description="Мультимодальная модель от Google с интеграцией сервисов", 
        cost_multiplier=0.9,
        prompt="Ты - многофункциональный ассистент Google. Отвечай кратко и по существу."
    ),
    "mixtral": GenerationModel(
        key="mixtral",
        name="🌀 Mixtral 8x7B", 
        description="Открытая модель с лучшим соотношением скорости и качества", 
        cost_multiplier=0.7,
        prompt="Ты - эксперт в различных областях знаний. Отвечай профессионально и точно."
    ),
    "llama3": GenerationModel(
        key="llama3",
        name="🦙 Llama 3 70B", 
        description="Новейшая открытая модель от Meta с улучшенными возможностями", 
        cost_multiplier=0.8,
        prompt="Ты - дружелюбный и креативный ассистент. Отвечай с юмором и творческим подходом."
    ),
    "claude_sonnet_4": GenerationModel(
        key="claude_sonnet_4",
        name="🧠 Claude Sonnet 4", 
        description="Экспертный уровень аналитики", 
        cost_multiplier=1.5,
        prompt="Ты - продвинутый ИИ Claude 4. Отвечай как профессиональный консультант: анализируй проблему, предлагай решения, предупреждай о рисках. Будь максимально полезным.",
        premium_only=True
    ),
    "gemini_2_5": GenerationModel(
        key="gemini_2_5",
        name="💎 Google Gemini 2.5", 
        description="Максимально практичные ответы", 
        cost_multiplier=1.4,
        prompt="Ты - Gemini, ИИ нового поколения. Отвечай кратко, но содержательно. Используй маркированные списки для структуры. Всегда предлагай практические шаги.",
        premium_only=True
    ),
    "grok_3": GenerationModel(
        key="grok_3",
        name="🚀 xAI Grok 3", 
        description="Технически точно с юмором", 
        cost_multiplier=1.2,
        prompt="Ты - Grok, ИИ с чувством юмора. Отвечай информативно, но с долей иронии. Используй современные аналогии. Не будь занудой.",
        premium_only=True
    ),
    "o3_mini": GenerationModel(
        key="o3_mini",
        name="⚡ OpenAI o3-mini", 
        description="Сверхбыстрые и точные ответы", 
        cost_multiplier=0.9,
        prompt="Ты - o3-mini, эксперт по эффективности. Отвечай максимально кратко, но содержательно. Используй тезисы. Избегай 'воды'.",
        premium_only=True
    )
}

# ===================== КЛАСС ПОЛЬЗОВАТЕЛЯ =====================
class User:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.stars = START_BALANCE_STARS
        self.referral_balance = 0
        self.referral_code = f"REF{user_id}{int(time.time()) % 10000}"
        self.invited_by = None
        self.state = "check_subscription"
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
        self.join_date = datetime.datetime.now().isoformat()
        self.images_generated = 0
        self.texts_generated = 0
        self.avatars_generated = 0
        self.logos_generated = 0
        self.templates_used = 0
        self.level = 1
        self.xp = 0
        self.achievements = {}
        self.settings = {
            "notifications": True,
            "language": "ru",
            "auto_translate": False
        }
        self.last_feedback = None
        self.feedback_count = 0
        
    def mark_modified(self):
        self._modified = True
        
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        user = cls(data["user_id"])
        for key, value in data.items():
            if hasattr(user, key):
                setattr(user, key, value)
        user._modified = False
        return user
        
    def can_make_request(self, cost: int = 0) -> bool:
        return self.is_premium or self.stars >= cost
            
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
        
        # Обрезаем контекст если превышен лимит
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
        bonus = DAILY_BONUS
        self.stars += bonus
        self.last_daily_bonus = time.time()
        self.add_xp(5)
        self.mark_modified()
        return bonus
        
    def clear_context(self):
        self.context = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.context_active = False
        self.mark_modified()
        
    def add_xp(self, amount: int):
        self.xp += amount
        new_level = self.calculate_level()
        if new_level > self.level:
            self.level = new_level
            return True
        return False
        
    def calculate_level(self) -> int:
        return min(50, int((self.xp / 100) ** 0.5) )+ 1
        
    def unlock_achievement(self, achievement_id: str) -> bool:
        if achievement_id in self.achievements:
            return False
        achievement = achievements.get(achievement_id)
        if not achievement:
            return False
        self.achievements[achievement_id] = datetime.datetime.now().isoformat()
        self.stars += achievement.reward
        self.add_xp(achievement.reward * 5)
        self.mark_modified()
        bot_stats["achievements_unlocked"] += 1
        return True
        
    def check_achievements(self):
        unlocked = []
        # Проверяем достижения по количеству генераций
        if self.images_generated >= 10 and "image_master" not in self.achievements:
            if self.unlock_achievement("image_master"):
                unlocked.append("image_master")
                
        if self.texts_generated >= 10 and "text_master" not in self.achievements:
            if self.unlock_achievement("text_master"):
                unlocked.append("text_master")
                
        # Достижения по уровню
        if self.level >= 5 and "level_5" not in self.achievements:
            if self.unlock_achievement("level_5"):
                unlocked.append("level_5")
                
        if self.is_premium and "premium_user" not in self.achievements:
            if self.unlock_achievement("premium_user"):
                unlocked.append("premium_user")
                
        return unlocked

# ===================== СИСТЕМА ХРАНЕНИЯ =====================
users_db = {}
referral_codes = {}
promo_codes = {}
templates = {}
achievements = {}
bot_stats = {
    "total_users": 0,
    "active_today": 0,
    "images_generated": 0,
    "texts_generated": 0,
    "avatars_generated": 0,
    "logos_generated": 0,
    "templates_used": 0,
    "stars_purchased": 0,
    "premium_purchased": 0,
    "achievements_unlocked": 0,
    "last_update": datetime.datetime.now().isoformat()
}
admin_broadcast_data = {}
db_lock = asyncio.Lock()
BOT_USERNAME = ""

async def load_db():
    global users_db, referral_codes, promo_codes, templates, achievements, bot_stats
    try:
        # Загрузка пользователей
        if os.path.exists(DB_FILE):
            async with db_lock:
                with open(DB_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    users_db = {int(k): User.from_dict(v) for k, v in data.get('users', {}).items()}
                    referral_codes = data.get('referral_codes', {})
                    logger.info("Database loaded successfully")
        
        # Загрузка промокодов
        if os.path.exists(PROMO_FILE):
            with open(PROMO_FILE, 'r', encoding='utf-8') as f:
                promo_codes = json.load(f)
                logger.info(f"Loaded {len(promo_codes)} promo codes")
                
        # Загрузка шаблонов
        if os.path.exists(TEMPLATES_FILE):
            with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
                templates_data = json.load(f)
                for t_id, t_data in templates_data.items():
                    templates[t_id] = Template(**t_data)
                logger.info(f"Loaded {len(templates)} templates")
                
        # Загрузка достижений
        if os.path.exists(ACHIEVEMENTS_FILE):
            with open(ACHIEVEMENTS_FILE, 'r', encoding='utf-8') as f:
                achievements_data = json.load(f)
                for a_id, a_data in achievements_data.items():
                    achievements[a_id] = Achievement(**a_data)
                logger.info(f"Loaded {len(achievements)} achievements")
                
        # Загрузка статистики
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                bot_stats = json.load(f)
                logger.info("Bot stats loaded")
                    
        # Создаем пользователя для админа если его нет
        if ADMIN_ID not in users_db:
            admin_user = User(ADMIN_ID)
            admin_user.is_premium = True
            admin_user.stars = 1000
            users_db[ADMIN_ID] = admin_user
            admin_user.mark_modified()
            logger.info(f"Created admin user: {ADMIN_ID}")
            
        # Создаем базовые достижения, если их нет
        if not achievements:
            create_default_achievements()
            
        # Создаем базовые шаблоны, если их нет
        if not templates:
            create_default_templates()
            
    except Exception as e:
        logger.error(f"Error loading database: {e}")
        users_db = {}
        referral_codes = {}
        promo_codes = {}
        templates = {}
        achievements = {}

async def save_db():
    try:
        async with db_lock:
            data = {
                'users': {k: v.to_dict() for k, v in users_db.items()},
                'referral_codes': referral_codes
            }
            
            with open(DB_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Сохраняем промокоды
            with open(PROMO_FILE, 'w', encoding='utf-8') as f:
                json.dump(promo_codes, f, ensure_ascii=False, indent=2)
                
            # Сохраняем шаблоны
            templates_data = {t_id: t.dict() for t_id, t in templates.items()}
            with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
                json.dump(templates_data, f, ensure_ascii=False, indent=2)
                
            # Сохраняем достижения
            achievements_data = {a_id: a.dict() for a_id, a in achievements.items()}
            with open(ACHIEVEMENTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(achievements_data, f, ensure_ascii=False, indent=2)
                
            # Сохраняем статистику
            with open(STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(bot_stats, f, ensure_ascii=False, indent=2)
            
            for user in users_db.values():
                user._modified = False
                
            logger.info("Database saved")
    except Exception as e:
        logger.error(f"Error saving database: {e}")

def create_default_achievements():
    global achievements
    achievements = {
        "first_generation": Achievement(
            id="first_generation",
            name="Первый шаг",
            description="Создайте ваш первый контент",
            condition="generated_content_count >= 1",
            reward=20,
            icon="🚀"
        ),
        "image_master": Achievement(
            id="image_master",
            name="Мастер изображений",
            description="Создайте 10 изображений",
            condition="images_generated >= 10",
            reward=50,
            icon="🎨"
        ),
        "text_master": Achievement(
            id="text_master",
            name="Мастер текстов",
            description="Создайте 10 текстов",
            condition="texts_generated >= 10",
            reward=50,
            icon="📝"
        ),
        "level_5": Achievement(
            id="level_5",
            name="Опытный пользователь",
            description="Достигните 5 уровня",
            condition="level >= 5",
            reward=100,
            icon="🌟"
        ),
        "premium_user": Achievement(
            id="premium_user",
            name="Премиум статус",
            description="Активируйте премиум подписку",
            condition="is_premium = true",
            reward=150,
            icon="💎"
        )
    }

def create_default_templates():
    global templates
    templates = {
        "social_post": Template(
            id="social_post",
            name="Пост для соцсетей",
            description="Создайте привлекательный пост для социальных сетей",
            prompt="Напиши креативный пост для соцсетей на тему: {topic}. Длина: 200-300 символов. Добавь эмодзи и хэштеги.",
            example="Тема: Открытие нового кофейного магазина",
            category="Текст",
            created_by=ADMIN_ID,
            created_at=datetime.datetime.now().isoformat()
        ),
        "business_idea": Template(
            id="business_idea",
            name="Бизнес-идея",
            description="Сгенерируйте уникальную бизнес-идею",
            prompt="Предложи инновационную бизнес-идею в сфере: {industry}. Опиши целевую аудиторию, уникальное предложение и потенциальные риски.",
            example="Сфера: экологически чистые продукты",
            category="Текст",
            created_by=ADMIN_ID,
            created_at=datetime.datetime.now().isoformat()
        ),
        "logo_design": Template(
            id="logo_design",
            name="Дизайн логотипа",
            description="Создайте описание для логотипа",
            prompt="Создай описание для логотипа компании: {company_name}, сфера: {industry}. Стиль: {style}. Основные элементы: {elements}.",
            example="Название: TechVision, Сфера: IT-консалтинг, Стиль: минимализм, Элементы: глаз, микросхема",
            category="Изображение",
            created_by=ADMIN_ID,
            created_at=datetime.datetime.now().isoformat()
        )
    }

async def get_user(user_id: int) -> User:
    if user_id in users_db:
        user = users_db[user_id]
        user.check_premium_status()
        return user
        
    user = User(user_id)
    users_db[user_id] = user
    referral_codes[user.referral_code] = user_id
    bot_stats["total_users"] += 1
    user.mark_modified()
    return user

# ===================== УТИЛИТЫ =====================
def detect_language(text: str) -> str:
    return 'ru' if re.search(r'[а-яА-Я]', text) else 'en'

def format_menu_title(title: str) -> str:
    return f"✨ {title.upper()} ✨\n{'═' * 35}\n"

def create_keyboard(buttons: List[List[Tuple[str, str]]], back: bool = True, home: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in buttons:
        for text, data in row:
            builder.button(text=text, callback_data=data)
        builder.adjust(len(row))
    
    if back:
        builder.button(text="🔙 Назад", callback_data="back")
    if home:
        builder.button(text="🏠 Главное", callback_data="home")
        
    return builder.as_markup()

def main_keyboard() -> InlineKeyboardMarkup:
    return create_keyboard([
        [("🛠️ Генерация", "generate_menu")],
        [("👤 Профиль", "profile_menu")],
        [("💎 Премиум", "premium_info"), ("🎁 Бонус", "daily_bonus")]
    ])

def generate_menu_keyboard() -> InlineKeyboardMarkup:
    return create_keyboard([
        [("📝 Текст", "gen_text"), ("🎨 Изображение", "gen_image")],
        [("👤 Аватар", "gen_avatar"), ("🖼️ Логотип", "gen_logo")],
        [("📋 Шаблоны", "template_select"), ("🤖 Модели", "model_select")]
    ])

def profile_menu_keyboard() -> InlineKeyboardMarkup:
    return create_keyboard([
        [("💰 Баланс", "balance_info"), ("🛒 Магазин", "shop")],
        [("👥 Рефералы", "referral_info"), ("🏆 Достижения", "achievements_list")],
        [("⚙️ Настройки", "settings_menu"), ("🆘 Поддержка", "support")]
    ])

def shop_keyboard() -> InlineKeyboardMarkup:
    return create_keyboard([
        [("⭐ 30 Звезд", "buy_stars30"), ("⭐ 50 Звезд", "buy_stars50")],
        [("⭐ 150 Звезд", "buy_stars150"), ("⭐ 500 Звезд", "buy_stars500")],
        [("💎 Премиум 1 мес", "buy_premium_month"), ("💎 Премиум навсегда", "buy_premium_forever")]
    ])

def image_options_keyboard() -> InlineKeyboardMarkup:
    return create_keyboard([
        [("✨ Улучшить", "improve_image"), ("🔄 Сгенерить снова", "regenerate_image")],
        [("⭐ Оценить", "feedback_image")]
    ], home=True, back=False)

def text_options_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = [
        [("🔄 Сгенерить снова", "regenerate_text"), ("📄 Увеличить", "extend_text")],
        [("✍️ Перефразировать", "rephrase_text"), ("⭐ Оценить", "feedback_text")]
    ]
    if user.context_active:
        buttons.append([("🧹 Очистить контекст", "clear_context")])
    return create_keyboard(buttons)

def premium_keyboard() -> InlineKeyboardMarkup:
    return create_keyboard([
        [("🛒 Перейти в магазин", "shop")],
        [("🎁 Активировать промокод", "activate_promo")],
        [("👥 Реферальная система", "referral_info")]
    ])

def image_count_keyboard() -> InlineKeyboardMarkup:
    buttons = [[(str(i), f"img_count_{i}") for i in range(1, MAX_IMAGE_COUNT + 1)]]
    return create_keyboard(buttons, back=True, home=True)

def model_select_keyboard() -> InlineKeyboardMarkup:
    return create_keyboard([
        [("🖼️ Для изображений", "image_model_select")],
        [("📝 Для текста", "text_model_select")]
    ])

def image_models_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    for key, model in IMAGE_MODELS.items():
        selected = " ✅" if user.image_model == key else ""
        buttons.append([(f"{model.name}{selected}", f"image_model_{key}")])
    return create_keyboard(buttons, back=True, home=True)

def text_models_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    for key, model in TEXT_MODELS.items():
        if model.premium_only and not user.is_premium:
            buttons.append([(f"🔒 {model.name} (премиум)", "premium_required")])
        else:
            selected = " ✅" if user.text_model == key else ""
            buttons.append([(f"{model.name}{selected}", f"text_model_{key}")])
    return create_keyboard(buttons, back=True, home=True)

def admin_keyboard() -> InlineKeyboardMarkup:
    return create_keyboard([
        [("👤 Пользователи", "admin_user_management"), ("🎫 Промокоды", "admin_promo_list")],
        [("📊 Статистика", "admin_stats"), ("📣 Рассылка", "admin_broadcast")],
        [("📋 Шаблоны", "admin_template_management")]
    ])

def admin_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")]]
    )

def template_list_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for template_id, template in templates.items():
        buttons.append([(f"📋 {template.name}", f"template_select_{template_id}")])
    return create_keyboard(buttons, back=True, home=True)

def achievements_list_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    for achievement_id, achievement in achievements.items():
        if achievement_id in user.achievements:
            unlocked_date = user.achievements[achievement_id]
            date_str = datetime.datetime.fromisoformat(unlocked_date).strftime("%d.%m.%Y")
            buttons.append([(f"✅ {achievement.icon} {achievement.name} ({date_str})", f"achievement_detail_{achievement_id}")])
        else:
            buttons.append([(f"🔒 {achievement.icon} {achievement.name}", "locked_achievement")])
    return create_keyboard(buttons, back=True, home=True)

def settings_menu_keyboard(user: User) -> InlineKeyboardMarkup:
    notifications = "🔔 Уведомления: Вкл" if user.settings["notifications"] else "🔕 Уведомления: Выкл"
    language = "🌐 Русский" if user.settings["language"] == "ru" else "🌐 English"
    auto_translate = "🔄 Автоперевод: Вкл" if user.settings["auto_translate"] else "🔄 Автоперевод: Выкл"
    
    return create_keyboard([
        [(notifications, "toggle_notifications")],
        [(language, "toggle_language")],
        [(auto_translate, "toggle_auto_translate")]
    ])

def feedback_keyboard(content_type: str) -> InlineKeyboardMarkup:
    return create_keyboard([
        [("⭐ 1", f"feedback_1_{content_type}"), ("⭐ 2", f"feedback_2_{content_type}"), ("⭐ 3", f"feedback_3_{content_type}")],
        [("⭐ 4", f"feedback_4_{content_type}"), ("⭐ 5", f"feedback_5_{content_type}")]
    ], back=False, home=True)

async def safe_edit_message(
    callback: CallbackQuery, 
    text: str, 
    reply_markup: InlineKeyboardMarkup = None
):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=reply_markup)

async def animate_loading(message: Message, text: str) -> Message:
    msg = await message.answer(f"⏳ {text}")
    await asyncio.sleep(1)
    return msg

async def animate_error(message: Message, text: str) -> Message:
    return await message.answer(f"❌ {text}")

async def animate_success(message: Message, text: str) -> Message:
    return await message.answer(f"✅ {text}")

async def fetch_with_retry(url: str, retries: int = 3) -> Optional[str]:
    for i in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as resp:
                    if resp.status == 200:
                        return await resp.text()
        except Exception:
            await asyncio.sleep(1.5)
    return None

async def translate_to_english(text: str) -> str:
    try:
        translation_prompt = f"Translate this to English without any additional text: {text}"
        result = await fetch_with_retry(f"{TEXT_URL}{urllib.parse.quote(translation_prompt)}")
        return result.strip().strip('"') if result else text
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text

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

async def check_subscription(user_id: int) -> bool:
    try:
        chat_member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return chat_member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        ]
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return False

async def ensure_subscription(update: Union[Message, CallbackQuery], user: User) -> bool:
    if user.has_subscribed:
        return True
    
    if await check_subscription(user.user_id):
        user.has_subscribed = True
        user.mark_modified()
        await save_db()
        return True
    
    text = (
        "📢 Для использования бота необходимо подписаться на наш канал!\n"
        "👉 https://t.me/neurogptpro 👈\n\n"
        "После подписки нажмите кнопку ниже"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/neurogptpro")],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")]
    ])
    
    if isinstance(update, Message):
        await update.answer(text, reply_markup=keyboard)
    else:
        await update.message.answer(text, reply_markup=keyboard)
    
    return False

def format_balance(user: User) -> str:
    user.check_premium_status()
    
    daily_status = "✅ Доступен" if user.can_claim_daily() else "❌ Уже получен"
    premium_status = "Активен" if user.is_premium else "Неактивен"
    next_level_xp = (user.level ** 2) * 100
    
    text = (
        f"💰 <b>ВАШ БАЛАНС</b>\n"
        f"{'═' * 35}\n"
        f"⭐ Звезды: {hbold(user.stars)}\n"
        f"🎁 Ежедневный бонус: {daily_status}\n"
        f"💎 Премиум: {premium_status}\n"
        f"🏆 Уровень: {user.level} (XP: {user.xp}/{next_level_xp})\n"
        f"{'═' * 35}\n"
    )
    
    if user.is_premium and user.premium_expiry:
        days_left = max(0, int((user.premium_expiry - time.time()) / (24 * 3600)))
        text += f"💎 Премиум активен! Осталось: {days_left} дней\n"
    elif user.is_premium:
        text += f"💎 Премиум активен (Навсегда)\n"
    else:
        text += (
            f"ℹ️ Премиум дает безлимитную генерацию контента\n"
            f"{'═' * 35}"
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
            f"{'═' * 35}\n"
            f"⏳ {status}\n\n"
            f"✨ <b>Преимущества:</b>\n"
            f"• 🎨 Безлимитная генерация изображений\n"
            f"• 👤 Безлимитная генерация аватаров\n"
            f"• 🖼️ Безлимитная генерация логотипов\n"
            f"• 📝 Безлимитная генерация текста\n"
            f"• 📋 Безлимитное использование шаблонов\n"
            f"• 🧠 Расширенный контекст\n"
            f"• 🖼️ Генерация до 8 вариантов\n"
            f"• 🤖 Эксклюзивные модели ИИ\n"
            f"• 🏆 Эксклюзивные достижения\n"
            f"{'═' * 35}"
        )
    else:
        text = (
            f"💎 <b>ПРЕМИУМ ПОДПИСКА</b>\n"
            f"{'═' * 35}\n"
            f"✨ <b>Преимущества:</b>\n"
            f"• 🎨 Безлимитная генерация изображений\n"
            f"• 👤 Безлимитная генерация аватаров\n"
            f"• 🖼️ Безлимитная генерация логотипов\n"
            f"• 📝 Безлимитная генерация текста\n"
            f"• 📋 Безлимитное использование шаблонов\n"
            f"• 🧠 Расширенный контекст\n"
            f"• 🖼️ Генерация до 8 вариантов\n"
            f"• 🤖 Эксклюзивные модели ИИ\n"
            f"• 🏆 Эксклюзивные достижения\n\n"
            f"💡 <b>Для активации премиума приобретите подписку в магазине</b>\n"
            f"{'═' * 35}"
        )
    return text

def format_achievement(achievement: Achievement, unlocked: bool = False, date: str = None) -> str:
    status = f"✅ Разблокировано: {date}" if unlocked else "🔒 Не разблокировано"
    return (
        f"{achievement.icon} <b>{achievement.name}</b>\n"
        f"{'═' * 35}\n"
        f"📝 {achievement.description}\n\n"
        f"🎯 Условие: {achievement.condition}\n"
        f"🎁 Награда: {achievement.reward} ⭐\n\n"
        f"{status}\n"
        f"{'═' * 35}"
    )

def format_template(template: Template) -> str:
    return (
        f"📋 <b>{template.name}</b>\n"
        f"{'═' * 35}\n"
        f"📝 Описание: {template.description}\n"
        f"🏷️ Категория: {template.category}\n"
        f"🔄 Использовано: {template.usage_count} раз\n\n"
        f"🔍 Пример:\n{template.example}\n\n"
        f"📌 Промпт:\n<code>{template.prompt}</code>\n"
        f"{'═' * 35}"
    )

# ===================== ОСНОВНЫЕ ОБРАБОТЧИКИ =====================
@dp.message(Command("start", "help"))
async def send_welcome(message: Message):
    user = await get_user(message.from_user.id)
    user.menu_stack = []
    user.update_interaction()
    
    # Обработка реферального кода
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("REF"):
        ref_code = args[1]
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
            user.state = "check_subscription"
            await message.answer(
                "📢 Для использования бота необходимо подписаться на наш канал!\n"
                "👉 https://t.me/neurogptpro 👈\n\n"
                "После подписки нажмите кнопку ниже",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/neurogptpro")],
                    [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")]
                ])
            )
            return
    
    # Обработка реферального кода после подписки
    if user.pending_referral and not user.referral_used:
        await process_referral(user, user.pending_referral)
    
    welcome_text = (
        f"✨ <b>Добро пожаловать, {html.quote(message.from_user.first_name)}!</b> ✨\n"
        f"{'═' * 35}\n"
        "🚀 Ваш персональный ИИ-ассистент для создания контента\n\n"
        "• 🎨 Генерация уникальных изображений по описанию\n"
        "• 📝 Создание текстов любого формата и стиля\n"
        "• 💎 Премиум-функции для профессионалов\n\n"
        f"🎁 <b>Стартовый бонус:</b> {START_BALANCE_STARS} ⭐\n"
        f"{'═' * 35}"
    )
    user.state = "main_menu"
    await message.answer(welcome_text, reply_markup=main_keyboard())
    await save_db()

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
            reply_markup=main_keyboard()
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
        await safe_edit_message(callback, text, reply_markup=create_keyboard([[("🔄 Обновить", "refresh_balance")]]))
        await save_db()
    else:
        last_date = datetime.datetime.fromtimestamp(user.last_daily_bonus).strftime("%d.%m.%Y")
        await callback.answer(f"❌ Вы уже получали бонус сегодня ({last_date})", show_alert=True)

@dp.callback_query(F.data == "back")
async def back_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    prev_menu = user.pop_menu()
    if prev_menu:
        user.state = prev_menu["state"]
        await show_menu(callback, user)
    else:
        await home_handler(callback)
    await callback.answer()

@dp.callback_query(F.data == "home")
async def home_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    user.state = "main_menu"
    user.menu_stack = []
    await show_menu(callback, user)
    await callback.answer()

async def show_menu(callback: CallbackQuery, user: User):
    menu_handlers = {
        "main_menu": handle_main_menu,
        "generate_menu": handle_generate_menu,
        "profile_menu": handle_profile_menu,
        "image_gen": handle_image_gen,
        "text_gen": handle_text_gen,
        "avatar_gen": handle_avatar_gen,
        "logo_gen": handle_logo_gen,
        "premium_info": handle_premium_info,
        "shop": handle_shop,
        "referral": handle_referral,
        "activate_promo": handle_activate_promo,
        "balance": handle_balance,
        "image_count_select": handle_image_count_select,
        "image_model_select": handle_image_model_select,
        "model_select": handle_model_select,
        "text_model_select": handle_text_model_select,
        "admin_panel": handle_admin_panel,
        "admin_create_promo": handle_admin_create_promo,
        "admin_stats": handle_admin_stats,
        "admin_broadcast": handle_admin_broadcast,
        "admin_promo_list": handle_admin_promo_list,
        "admin_user_management": handle_admin_user_management,
        "admin_template_management": handle_admin_template_management,
        "template_select": handle_template_select,
        "achievements_list": handle_achievements_list,
        "settings_menu": handle_settings_menu,
        "check_subscription": handle_check_subscription
    }
    
    handler = menu_handlers.get(user.state, handle_main_menu)
    await handler(callback, user)

async def handle_main_menu(callback: CallbackQuery, user: User):
    text = format_menu_title("Главное меню")
    text += "Выберите раздел:"
    await safe_edit_message(callback, text, main_keyboard())

async def handle_generate_menu(callback: CallbackQuery, user: User):
    text = format_menu_title("Генерация контента")
    text += "Что вы хотите создать?"
    await safe_edit_message(callback, text, generate_menu_keyboard())

async def handle_profile_menu(callback: CallbackQuery, user: User):
    text = format_menu_title("Ваш профиль")
    text += "Управление вашим аккаунтом:"
    await safe_edit_message(callback, text, profile_menu_keyboard())

async def handle_image_gen(callback: CallbackQuery, user: User):
    model = IMAGE_MODELS[user.image_model]
    cost = 0 if user.is_premium else int(IMAGE_COST * model.cost_multiplier)
    cost_text = "💎 Безлимит (премиум)" if user.is_premium else f"💎 Стоимость: {cost} ⭐"
    
    text = format_menu_title("Генерация изображения")
    text += (
        f"🤖 Модель: {model.name}\n\n"
        "🔍 <b>Отправьте описание изображения:</b>\n"
        "Примеры:\n"
        "• Космический корабль в стиле киберпанк\n"
        "• Реалистичный портрет кота\n\n"
        f"{cost_text}\n"
        f"⚠️ Максимум {MAX_PROMPT_LENGTH} символов\n"
        f"{'═' * 35}"
    )
    
    await safe_edit_message(callback, text, 
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]])
    )

async def handle_text_gen(callback: CallbackQuery, user: User):
    model = TEXT_MODELS[user.text_model]
    cost = 0 if user.is_premium else int(TEXT_COST_PER_100_WORDS * model.cost_multiplier)
    cost_text = "💎 Безлимит (премиум)" if user.is_premium else f"💎 Стоимость: {cost} ⭐ за 100 слов"
    
    text = format_menu_title("Генерация текста")
    text += (
        f"🤖 Модель: {model.name}\n\n"
        "🔍 <b>Отправьте ваш запрос:</b>\n"
        f"{cost_text}\n"
        f"⚠️ Максимум {MAX_PROMPT_LENGTH} символов\n"
        f"{'═' * 35}"
    )
    
    await safe_edit_message(callback, text, 
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]])
    )

async def handle_premium_info(callback: CallbackQuery, user: User):
    text = format_premium_info(user)
    await safe_edit_message(callback, text, premium_keyboard() if not user.is_premium else None)

async def handle_shop(callback: CallbackQuery, user: User):
    text = format_menu_title("Магазин")
    text += format_balance(user)
    text += "\nВыберите товар:"
    await safe_edit_message(callback, text, shop_keyboard())

async def handle_referral(callback: CallbackQuery, user: User):
    referral_link = f"https://t.me/NeuroAlliance_bot?start={user.referral_code}"
    text = format_menu_title("Реферальная система")
    text += (
        f"🔗 <b>Ваша реферальная ссылка:</b>\n"
        f"{hcode(referral_link)}\n\n"
        f"💎 <b>За приглашенного друга:</b>\n"
        f"• Вы получаете: {REFERRAL_BONUS} ⭐\n"
        f"• Друг получает: {START_BALANCE_STARS//2} ⭐\n\n"
        f"💰 <b>Реферальный баланс:</b> {hbold(user.referral_balance)} 💎\n"
        f"⚠️ Минимальный вывод: {WITHDRAW_MIN} 💎\n"
        f"{'═' * 35}"
    )
    
    keyboard = create_keyboard([
        [("💸 Вывести средства", "withdraw_referral")],
        [("🎁 Активировать промокод", "activate_promo")]
    ])
    
    await safe_edit_message(callback, text, keyboard)

async def handle_activate_promo(callback: CallbackQuery, user: User):
    text = format_menu_title("Активация промокода")
    text += "🔑 Введите промокод:"
    await safe_edit_message(callback, text, 
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]])
    )

async def handle_balance(callback: CallbackQuery, user: User):
    text = format_menu_title("Ваш баланс")
    text += format_balance(user)
    await safe_edit_message(callback, text, create_keyboard([[("🔄 Обновить", "refresh_balance")]]))

async def handle_image_model_select(callback: CallbackQuery, user: User):
    text = format_menu_title("Модели для изображений")
    text += "Выберите модель генерации:"
    await safe_edit_message(callback, text, image_models_keyboard(user))

async def handle_model_select(callback: CallbackQuery, user: User):
    text = format_menu_title("Выбор модели ИИ")
    text += "Выберите тип модели:"
    await safe_edit_message(callback, text, model_select_keyboard())

async def handle_text_model_select(callback: CallbackQuery, user: User):
    text = format_menu_title("Модели для текста")
    text += "Выберите модель генерации:"
    if any(model.premium_only for model in TEXT_MODELS.values()):
        text += "\n🔒 Премиум-модели доступны только с подпиской"
    await safe_edit_message(callback, text, text_models_keyboard(user))

# ===================== ГЕНЕРАЦИЯ КОНТЕНТА =====================
async def generate_image(user: User, prompt: str, message: Message):
    try:
        # Проверка подписки и баланса
        if not await ensure_subscription(message, user):
            return
            
        if len(prompt) > MAX_PROMPT_LENGTH:
            await animate_error(message, f"⚠️ Максимальная длина описания: {MAX_PROMPT_LENGTH} символов")
            return
            
        model = IMAGE_MODELS[user.image_model]
        cost = 0 if user.is_premium else int(IMAGE_COST * model.cost_multiplier)
        
        if not user.can_make_request(cost):
            await animate_error(
                message, 
                f"❌ Недостаточно звёзд! Требуется: {cost} ⭐\n"
                f"Ваш баланс: {user.stars} ⭐"
            )
            return
            
        # Показываем анимацию загрузки
        processing_msg = await animate_loading(message, "🎨 Создаю ваше изображение...")
        
        # Обработка промпта
        if user.settings["auto_translate"] and detect_language(prompt) != 'en':
            prompt = await translate_to_english(prompt)
            
        enhanced_prompt = f"{prompt}, {model.prompt}"
        
        # Генерация изображения
        encoded_prompt = urllib.parse.quote(enhanced_prompt)
        image_url = f"{IMAGE_URL}{encoded_prompt}?nologo=true"
        
        # Создаем клавиатуру с опциями
        keyboard = image_options_keyboard()
        
        # Отправляем результат
        caption = (
            f"🎨 <b>Ваше изображение готово!</b>\n"
            f"{'═' * 35}\n"
            f"🤖 Модель: {model.name}\n"
            f"💎 Стоимость: {'Бесплатно (премиум)' if user.is_premium else f'{cost} ⭐'}\n"
            f"{'═' * 35}"
        )
        
        await processing_msg.delete()
        result = await message.answer_photo(
            photo=image_url,
            caption=caption,
            reply_markup=keyboard
        )
        
        # Обновляем данные пользователя
        user.last_image_prompt = prompt
        user.last_image_url = result.photo[-1].file_id
        user.images_generated += 1
        if not user.is_premium:
            user.stars -= cost
        user.mark_modified()
        
        # Проверка достижений
        unlocked = user.check_achievements()
        if unlocked:
            for achievement_id in unlocked:
                achievement = achievements[achievement_id]
                await message.answer(
                    f"🏆 <b>НОВОЕ ДОСТИЖЕНИЕ!</b>\n"
                    f"{'═' * 35}\n"
                    f"{achievement.icon} {achievement.name}\n"
                    f"{achievement.description}\n\n"
                    f"🎁 Награда: {achievement.reward} ⭐"
                )
        
        await save_db()
        
    except Exception as e:
        logger.error(f"Image generation error: {str(e)}")
        await animate_error(message, "⚠️ Произошла ошибка при генерации изображения. Пожалуйста, попробуйте позже.")

async def generate_text(user: User, prompt: str, message: Message):
    try:
        # Проверка подписки и баланса
        if not await ensure_subscription(message, user):
            return
            
        model = TEXT_MODELS[user.text_model]
        if model.premium_only and not user.is_premium:
            await animate_error(message, "❌ Эта модель доступна только для премиум пользователей")
            return
            
        if len(prompt) > MAX_PROMPT_LENGTH:
            await animate_error(message, f"⚠️ Максимальная длина запроса: {MAX_PROMPT_LENGTH} символов")
            return
            
        # Показываем анимацию загрузки
        processing_msg = await animate_loading(message, "🧠 Обрабатываю ваш запрос...")
        
        # Обработка промпта
        full_prompt = f"{model.prompt}\n\n{prompt}"
        
        # Генерация текста
        encoded_prompt = urllib.parse.quote(full_prompt)
        result = await fetch_with_retry(f"{TEXT_URL}{encoded_prompt}")
        
        if not result:
            raise Exception("Ошибка сервера генерации")
        
        # Форматирование результата
        formatted_result = f"📝 <b>Результат:</b>\n{'═' * 35}\n\n{result}"
        
        # Расчет стоимости
        words = len(result.split())
        cost = max(1, (words // 100) * int(TEXT_COST_PER_100_WORDS * model.cost_multiplier))
        
        if not user.is_premium and user.stars < cost:
            await processing_msg.delete()
            await animate_error(
                message, 
                f"❌ Недостаточно звёзд! Требуется: {cost} ⭐\n"
                f"Ваш баланс: {user.stars} ⭐"
            )
            return
        
        # Отправка результата
        await processing_msg.delete()
        await message.answer(formatted_result, parse_mode="HTML")
        
        # Статистика
        stats_text = (
            f"✅ <b>Готово!</b>\n"
            f"{'═' * 35}\n"
            f"🤖 Модель: {model.name}\n"
            f"💎 Стоимость: {'Бесплатно (премиум)' if user.is_premium else f'{cost} ⭐'}\n"
            f"{'═' * 35}"
        )
        
        await message.answer(stats_text, reply_markup=text_options_keyboard(user))
        
        # Обновляем данные пользователя
        user.last_text = result
        user.texts_generated += 1
        if not user.is_premium:
            user.stars -= cost
        user.mark_modified()
        
        # Проверка достижений
        unlocked = user.check_achievements()
        if unlocked:
            for achievement_id in unlocked:
                achievement = achievements[achievement_id]
                await message.answer(
                    f"🏆 <b>НОВОЕ ДОСТИЖЕНИЕ!</b>\n"
                    f"{'═' * 35}\n"
                    f"{achievement.icon} {achievement.name}\n"
                    f"{achievement.description}\n\n"
                    f"🎁 Награда: {achievement.reward} ⭐"
                )
        
        await save_db()
        
    except Exception as e:
        logger.error(f"Text generation error: {str(e)}")
        await animate_error(message, "⚠️ Произошла ошибка при генерации текста. Пожалуйста, попробуйте позже.")

# ===================== ОБРАБОТКА СООБЩЕНИЙ =====================
@dp.message(F.text)
async def handle_message(message: Message):
    user = await get_user(message.from_user.id)
    text = message.text.strip()
    user.update_interaction()
    
    if not await ensure_subscription(message, user):
        return
        
    try:
        if user.state == "image_gen":
            await generate_image(user, text, message)
        elif user.state == "text_gen":
            await generate_text(user, text, message)
        elif user.state == "avatar_gen":
            await generate_image(user, text, message)  # Используем ту же логику для аватаров
        elif user.state == "logo_gen":
            await generate_image(user, text, message)  # Используем ту же логику для логотипов
        elif user.state == "activate_promo":
            await process_promo_code(user, text, message)
    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await animate_error(message, f"⚠️ Ошибка: {str(e)}")
    finally:
        await save_db()

# ===================== ЗАПУСК ПРИЛОЖЕНИЯ =====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Загрузка данных при старте
    await load_db()
    
    # Инициализация бота
    bot_info = await bot.get_me()
    global BOT_USERNAME
    BOT_USERNAME = bot_info.username
    logger.info(f"Bot @{BOT_USERNAME} started")
    
    # Очистка предыдущих обновлений
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запуск бота в фоне
    asyncio.create_task(dp.start_polling(bot, skip_updates=True))
    
    yield
    
    # Остановка при завершении
    await save_db()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "AI Content Generator Bot", "version": "3.0"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        workers=1,
        loop="asyncio",
        timeout_keep_alive=60
    )
