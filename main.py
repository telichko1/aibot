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
from pydantic import BaseModel

# ===================== КОНСТАНТЫ =====================
API_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 750638552))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", -1002712232742))

PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_TOKEN", "")
IMAGE_URL = "https://image.pollinations.ai/prompt/"
TEXT_URL = "https://text.pollinations.ai/prompt/"
PAYMENT_ADMIN = "@telichko_a"
DB_FILE = "users_db.json"
LOG_FILE = "bot_errors.log"
PROMO_FILE = "promo_codes.json"
STATS_FILE = "bot_stats.json"
TEMPLATES_FILE = "templates.json"
ACHIEVEMENTS_FILE = "achievements.json"

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
SESSION_TIMEOUT = 2592000  # 30 дней
DAILY_BONUS = 3
SYSTEM_PROMPT = "Ты — полезный ИИ-ассистент. Отвечай точно и информативно."
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "admin123")  # Пароль для доступа к админ-панели
TEMPLATE_COST = 15
MAX_TEMPLATE_LENGTH = 500

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

# Создаем метрики Prometheus
USERS_TOTAL = Gauge('bot_users_total', 'Total registered users')
IMAGES_GENERATED = Counter('bot_images_generated', 'Total images generated')
TEXTS_GENERATED = Counter('bot_texts_generated', 'Total texts generated')
AVATARS_GENERATED = Counter('bot_avatars_generated', 'Total avatars generated')
LOGOS_GENERATED = Counter('bot_logos_generated', 'Total logos generated')
TEMPLATES_USED = Counter('bot_templates_used', 'Total templates used')
ACTIVE_USERS = Gauge('bot_active_users_today', 'Active users today')
STARS_PURCHASED = Counter('bot_stars_purchased', 'Total stars purchased')
PREMIUM_PURCHASED = Counter('bot_premium_purchased', 'Total premium subscriptions purchased')
REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing requests')
ERROR_COUNT = Counter('bot_errors_total', 'Total errors encountered')

# Глобальные структуры данных
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

class UserState:
    MAIN_MENU = "main_menu"
    GENERATE_MENU = "generate_menu"
    PROFILE_MENU = "profile_menu"
    IMAGE_GEN = "image_gen"
    TEXT_GEN = "text_gen"
    AVATAR_GEN = "avatar_gen"
    LOGO_GEN = "logo_gen"
    TEMPLATE_GEN = "template_gen"
    PREMIUM_INFO = "premium_info"
    SHOP = "shop"
    REFERRAL = "referral"
    BALANCE = "balance"
    IMAGE_OPTIONS = "image_options"
    AVATAR_OPTIONS = "avatar_options"
    LOGO_OPTIONS = "logo_options"
    TEXT_OPTIONS = "text_options"
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
    ADMIN_PANEL = "admin_panel"
    ADMIN_CREATE_PROMO = "admin_create_promo"
    ADMIN_STATS = "admin_stats"
    ADMIN_BROADCAST = "admin_broadcast"
    ADMIN_PROMO_LIST = "admin_promo_list"
    ADMIN_USER_MANAGEMENT = "admin_user_management"
    ADMIN_TEMPLATE_MANAGEMENT = "admin_template_management"
    ADMIN_VIEW_USER = "admin_view_user"
    ADMIN_EDIT_USER = "admin_edit_user"
    TEMPLATE_SELECT = "template_select"
    FEEDBACK = "feedback"
    ACHIEVEMENTS_LIST = "achievements_list"  # Добавлено отсутствующее состояние

class GenerationModel(BaseModel):
    key: str
    name: str
    description: str
    cost_multiplier: float
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
            "referral_used": self.referral_used,
            "join_date": self.join_date,
            "images_generated": self.images_generated,
            "texts_generated": self.texts_generated,
            "avatars_generated": self.avatars_generated,
            "logos_generated": self.logos_generated,
            "templates_used": self.templates_used,
            "level": self.level,
            "xp": self.xp,
            "achievements": self.achievements,
            "settings": self.settings,
            "last_feedback": self.last_feedback,
            "feedback_count": self.feedback_count
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
        user.join_date = data.get("join_date", datetime.datetime.now().isoformat())
        user.images_generated = data.get("images_generated", 0)
        user.texts_generated = data.get("texts_generated", 0)
        user.avatars_generated = data.get("avatars_generated", 0)
        user.logos_generated = data.get("logos_generated", 0)
        user.templates_used = data.get("templates_used", 0)
        user.level = data.get("level", 1)
        user.xp = data.get("xp", 0)
        user.achievements = data.get("achievements", {})
        user.settings = data.get("settings", {
            "notifications": True,
            "language": "ru",
            "auto_translate": False
        })
        user.last_feedback = data.get("last_feedback", None)
        user.feedback_count = data.get("feedback_count", 0)
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
        # Простая формула: уровень = sqrt(XP/100) + 1
        return min(50, int((self.xp / 100) ** 0.5)) + 1
        
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
        # Проверяем достижения, которые могут быть разблокированы
        unlocked = []
        
        # Достижения по количеству генераций
        if self.images_generated >= 10 and not self.achievements.get("image_master"):
            if self.unlock_achievement("image_master"):
                unlocked.append("image_master")
                
        if self.texts_generated >= 10 and not self.achievements.get("text_master"):
            if self.unlock_achievement("text_master"):
                unlocked.append("text_master")
                
        # Достижения по уровню
        if self.level >= 5 and not self.achievements.get("level_5"):
            if self.unlock_achievement("level_5"):
                unlocked.append("level_5")
                
        return unlocked

# ===================== УТИЛИТЫ =====================
async def load_db():
    global users_db, referral_codes, promo_codes, templates, achievements, bot_stats
    try:
        users_db = {}
        referral_codes = {}
        promo_codes = {}
        templates = {}
        achievements = {}
        
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
            admin_user.premium_expiry = None
            admin_user.stars = 1000
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
    else:
        user = User(user_id)
        users_db[user_id] = user
        referral_codes[user.referral_code] = user_id
        bot_stats["total_users"] += 1
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

def generate_random_id(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
# ===================== ФУНКЦИИ ДЛЯ ФОНОВЫХ ЗАДАЧ =====================
async def auto_save_db():
    """Фоновая задача для автоматического сохранения базы данных"""
    while True:
        try:
            await asyncio.sleep(300)  # Сохраняем каждые 5 минут
            await save_db()
            logger.info("Auto-saved database")
        except Exception as e:
            logger.error(f"Auto-save error: {e}")

async def self_pinger():
    """Фоновая задача для поддержания активности приложения"""
    while True:
        try:
            await asyncio.sleep(60)  # Пинг каждую минуту
            async with aiohttp.ClientSession() as session:
                async with session.get("https://your-app-url.onrender.com/"):
                    pass
            logger.debug("Self-ping executed")
        except Exception as e:
            logger.error(f"Self-ping error: {e}")

# ===================== ПРОВЕРКА ПОДПИСКИ =====================
async def check_subscription(user_id: int) -> bool:
    """Проверяет, подписан ли пользователь на канал"""
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
    """Обеспечивает, что пользователь подписан на канал"""
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
    
    if isinstance(update, Message):
        await update.answer(text, reply_markup=subscribe_keyboard())
    else:
        await update.message.answer(text, reply_markup=subscribe_keyboard())
    
    return False

# ===================== ОБРАБОТКА ПЛАТЕЖЕЙ И ПРОМОКОДОВ =====================
@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    user_id = pre_checkout_query.from_user.id
    user = await get_user(user_id)
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    logger.info(f"Pre-checkout approved for {user_id}")

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    user = await get_user(message.from_user.id)
    payment = message.successful_payment
    item = payment.invoice_payload
    
    items = {
        "stars30": {"stars": 30},
        "stars50": {"stars": 50},
        "stars150": {"stars": 150},
        "stars500": {"stars": 500},
        "premium_month": {"premium": True, "expiry": time.time() + 30 * 24 * 3600},
        "premium_forever": {"premium": True, "expiry": None}
    }
    
    if item in items:
        product = items[item]
        if "stars" in product:
            user.stars += product["stars"]
            bot_stats["stars_purchased"] += product["stars"]
            STARS_PURCHASED.inc(product["stars"])
            text = f"✅ Куплено {product['stars']} ⭐"
        else:
            user.is_premium = True
            user.premium_expiry = product.get("expiry")
            bot_stats["premium_purchased"] += 1
            PREMIUM_PURCHASED.inc()
            text = "💎 Премиум подписка активирована!"
        
        user.mark_modified()
        await save_db()
        await message.answer(text + "\n" + format_balance(user), reply_markup=main_keyboard(user))
    else:
        await message.answer("❌ Неизвестный товар, обратитесь в поддержку")

async def process_referral(user: User, ref_code: str):
    """Обрабатывает реферальный код"""
    if user.referral_used:
        return
    
    referrer_id = referral_codes.get(ref_code)
    if not referrer_id or referrer_id == user.user_id:
        return
    
    if referrer_id in users_db:
        referrer = users_db[referrer_id]
        referrer.referral_balance += REFERRAL_BONUS
        referrer.mark_modified()
        
        user.stars += START_BALANCE_STARS // 2
        user.referral_used = True
        user.mark_modified()
        
        await send_notification(
            referrer_id,
            f"🎉 Новый реферал!\n"
            f"Пользователь @{user.user_id} присоединился по вашей ссылке\n"
            f"+{REFERRAL_BONUS} 💎 на реферальный баланс"
        )
        
        await bot.send_message(
            user.user_id,
            f"🎁 Реферальный бонус!\n"
            f"+{START_BALANCE_STARS // 2} ⭐ на ваш баланс"
        )
        
        await save_db()

async def process_promo_code(user: User, promo_code: str, message: Message):
    """Активирует промокод для пользователя"""
    promo_data = promo_codes.get(promo_code.upper())
    
    if not promo_data or not promo_data.get("active", True):
        await message.answer("❌ Неверный или неактивный промокод")
        return
    
    # Проверка лимита использования
    used_count = promo_data.get("used_count", 0)
    if "limit" in promo_data and used_count >= promo_data["limit"]:
        await message.answer("❌ Лимит использования промокода исчерпан")
        return
    
    # Проверка, не использовал ли пользователь уже этот промокод
    if "used_by" in promo_data:
        if any(entry["user_id"] == user.user_id for entry in promo_data["used_by"]):
            await message.answer("ℹ️ Вы уже активировали этот промокод")
            return
    
    # Активация промокода
    promo_type = promo_data["type"]
    value = promo_data["value"]
    
    if promo_type == "stars":
        user.stars += value
        text = f"🎁 Активировано {value} ⭐"
    elif promo_type == "premium":
        if value == "forever":
            user.is_premium = True
            user.premium_expiry = None
            text = "💎 Активирован вечный премиум доступ!"
        else:
            days = int(value)
            expiry = time.time() + days * 24 * 3600
            user.is_premium = True
            user.premium_expiry = expiry
            text = f"💎 Активирован премиум доступ на {days} дней!"
    
    # Обновление данных промокода
    promo_data["used_count"] = used_count + 1
    if "used_by" not in promo_data:
        promo_data["used_by"] = []
    
    promo_data["used_by"].append({
        "user_id": user.user_id,
        "date": datetime.datetime.now().isoformat()
    })
    
    promo_codes[promo_code.upper()] = promo_data
    user.mark_modified()
    
    # Сохранение и уведомление
    await save_db()
    await message.answer(text + "\n" + format_balance(user), reply_markup=main_keyboard(user))

# ===================== АДМИН-ФУНКЦИИ =====================
async def process_admin_command(message: Message):
    """Обработчик команды /admin"""
    user = await get_user(message.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) > 1 and args[1] == ADMIN_PASSWORD:
        user.state = UserState.ADMIN_PANEL
        await message.answer("👑 Админ-панель", reply_markup=admin_keyboard())
    else:
        await message.answer("🔒 Введите пароль админа:")

async def process_promo_creation(message: Message):
    """Создание промокода по команде админа"""
    user = await get_user(message.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split(":")
        if len(parts) < 3:
            raise ValueError("Неверный формат")
        
        promo_type = parts[0].strip()
        value = parts[1].strip()
        limit = int(parts[2].strip())
        
        if promo_type not in ["stars", "premium"]:
            raise ValueError("Неверный тип промокода")
        
        # Генерация уникального кода
        promo_code = "PROMO" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        while promo_code in promo_codes:
            promo_code = "PROMO" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # Создание промокода
        promo_codes[promo_code] = {
            "type": promo_type,
            "value": value,
            "limit": limit if limit > 0 else 0,
            "created_by": user.user_id,
            "created_at": datetime.datetime.now().isoformat(),
            "active": True,
            "used_count": 0
        }
        
        # Сохранение
        with open(PROMO_FILE, 'w', encoding='utf-8') as f:
            json.dump(promo_codes, f, ensure_ascii=False, indent=2)
        
        await message.answer(f"✅ Промокод создан: {promo_code}")
        user.state = UserState.ADMIN_PANEL
        await show_menu(message, user)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

async def process_broadcast_message(message: Message):
    """Обработка сообщения для рассылки"""
    user = await get_user(message.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    admin_broadcast_data[user.user_id] = message.text
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="broadcast_confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="broadcast_cancel")]
    ])
    await message.answer(
        f"📣 Подтвердите рассылку:\n{message.text[:500]}...",
        reply_markup=keyboard
    )

async def execute_broadcast(admin_id: int):
    """Выполняет рассылку сообщения"""
    if admin_id not in admin_broadcast_data or admin_broadcast_data[admin_id] == "CANCEL":
        return
    
    text = admin_broadcast_data[admin_id]
    success = 0
    errors = 0
    
    await bot.send_message(admin_id, "⏳ Начинаю рассылку...")
    
    for user_id, user in list(users_db.items()):
        try:
            await bot.send_message(user_id, text)
            success += 1
            if success % 10 == 0:
                await asyncio.sleep(1)
        except Exception as e:
            errors += 1
            logger.error(f"Broadcast to {user_id} failed: {e}")
    
    del admin_broadcast_data[admin_id]
    await bot.send_message(
        admin_id,
        f"📣 Рассылка завершена!\n"
        f"✅ Успешно: {success}\n"
        f"❌ Ошибок: {errors}",
        reply_markup=admin_keyboard()
    )

async def process_admin_search_user(message: Message, text: str):
    """Поиск пользователя по ID"""
    user = await get_user(message.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    try:
        user_id = int(text)
        if user_id not in users_db:
            await message.answer("❌ Пользователь не найден")
            return
        
        target_user = users_db[user_id]
        await handle_admin_view_user(message, user, user_id)
    except ValueError:
        await message.answer("❌ Неверный формат ID")

async def process_admin_edit_user(message: Message, text: str):
    """Редактирование данных пользователя"""
    user = await get_user(message.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    try:
        parts = text.split(":")
        if len(parts) < 2:
            raise ValueError("Неверный формат")
        
        field = parts[0].strip()
        value = parts[1].strip()
        
        # Извлекаем user_id из контекста (последний просмотренный)
        if not user.last_text or not user.last_text.startswith("admin_edit_user_"):
            raise ValueError("Не выбран пользователь")
        
        user_id = int(user.last_text.split("_")[3])
        if user_id not in users_db:
            raise ValueError("Пользователь не найден")
        
        target_user = users_db[user_id]
        
        if field == "stars":
            target_user.stars = int(value)
        elif field == "premium":
            days = int(value)
            if days > 0:
                target_user.is_premium = True
                target_user.premium_expiry = time.time() + days * 24 * 3600
            else:
                target_user.is_premium = False
                target_user.premium_expiry = None
        else:
            raise ValueError("Неизвестное поле")
        
        target_user.mark_modified()
        await save_db()
        await message.answer(f"✅ Данные пользователя {user_id} обновлены")
        await handle_admin_view_user(message, user, user_id)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

async def process_admin_create_template(message: Message, text: str):
    """Создание шаблона по команде админа"""
    user = await get_user(message.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    try:
        template_data = json.loads(text)
        required_fields = ["name", "description", "prompt", "example", "category"]
        
        if not all(field in template_data for field in required_fields):
            raise ValueError("Отсутствуют обязательные поля")
        
        # Генерация ID
        template_id = "T" + generate_random_id(5)
        while template_id in templates:
            template_id = "T" + generate_random_id(5)
        
        # Создание шаблона
        template = Template(
            id=template_id,
            name=template_data["name"],
            description=template_data["description"],
            prompt=template_data["prompt"],
            example=template_data["example"],
            category=template_data["category"],
            created_by=user.user_id,
            created_at=datetime.datetime.now().isoformat()
        )
        
        templates[template_id] = template
        await save_db()
        
        await message.answer(f"✅ Шаблон создан: {template.name}")
        user.state = UserState.ADMIN_PANEL
        await show_menu(message, user)
    except json.JSONDecodeError:
        await message.answer("❌ Ошибка формата JSON")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        
# ===================== КЛАВИАТУРЫ =====================
def create_keyboard(
    buttons: List[Union[Tuple[str, str], List[Tuple[str, str]]]],
    back_button: bool = False,
    home_button: bool = False,
    cancel_button: bool = False,
    columns: int = 2
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
    
    if columns > 1:
        builder.adjust(columns)
    
    return builder.as_markup()

def main_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = [
        [("🛠️ Генерация", "generate_menu")],
        [("👤 Профиль", "profile_menu")],
        [("💎 Премиум", "premium_info")],
        [("🎁 Ежедневный бонус", "daily_bonus")]
    ]
    return create_keyboard(buttons, columns=2)

def generate_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("📝 Текст", "gen_text")],
        [("🎨 Изображение", "gen_image")],
        [("👤 Аватар", "gen_avatar")],
        [("🖼️ Логотип", "gen_logo")],
        [("📋 Шаблоны", "template_select")],
        [("🤖 Модели ИИ", "model_select")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons, columns=2)

def profile_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("💰 Баланс", "balance_info")],
        [("🛒 Магазин", "shop")],
        [("👥 Рефералы", "referral_info")],
        [("🏆 Достижения", "achievements_list")],
        [("⚙️ Настройки", "settings_menu")],
        [("🆘 Поддержка", "support")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons, columns=2)

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
    return create_keyboard(buttons, columns=2)

def image_options_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    buttons.append([("✨ Улучшить", "improve_image")])
    buttons.append([("🔄 Сгенерить снова", "regenerate_image"), ("⭐ Оценить", "feedback_image")])
    buttons.append([("🏠 Главное", "home")])
    return create_keyboard(buttons, columns=1)

def avatar_options_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🔄 Сгенерить снова", "regenerate_avatar"), ("⭐ Оценить", "feedback_avatar")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons, columns=2)

def logo_options_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🔄 Сгенерить снова", "regenerate_logo"), ("⭐ Оценить", "feedback_logo")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons, columns=2)

def text_options_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    buttons.append([("🔄 Сгенерить снова", "regenerate_text"), ("📄 Увеличить", "extend_text")])
    buttons.append([("✍️ Перефразировать", "rephrase_text"), ("⭐ Оценить", "feedback_text")])
    
    if user.context_active:
        buttons.append([("🧹 Очистить контекст", "clear_context")])
    
    buttons.append([("🏠 Главное", "home")])
    return create_keyboard(buttons, columns=2)

def premium_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🛒 Перейти в магазин", "shop")],
        [("🎁 Активировать промокод", "activate_promo")],
        [("👥 Реферальная система", "referral_info")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons, columns=1)

def image_count_keyboard() -> InlineKeyboardMarkup:
    buttons = [[(str(i), f"img_count_{i}") for i in range(1, MAX_IMAGE_COUNT + 1)]]
    buttons.append([("🏠 Главное", "home")])
    return create_keyboard(buttons, columns=4)

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
    return create_keyboard(buttons, columns=2)

def referral_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("💸 Вывести средства", "withdraw_referral")],
        [("🎁 Активировать промокод", "activate_promo")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons, columns=1)

def model_select_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🖼️ Для изображений", "image_model_select")],
        [("📝 Для текста", "text_model_select")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons, columns=1)

def image_models_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    for key, model in IMAGE_MODELS.items():
        if user.image_model == key:
            buttons.append([(f"✅ {model.name}", f"image_model_{key}")])
        else:
            buttons.append([(model.name, f"image_model_{key}")])
    
    buttons.append([("🔙 Назад", "model_select")])
    return create_keyboard(buttons, columns=1)

def text_models_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    for key, model in TEXT_MODELS.items():
        if model.premium_only and not user.is_premium:
            buttons.append([(f"🔒 {model.name} (премиум)", "premium_required")])
        else:
            if user.text_model == key:
                buttons.append([(f"✅ {model.name}", f"text_model_{key}")])
            else:
                buttons.append([(model.name, f"text_model_{key}")])
    
    buttons.append([("🔙 Назад", "model_select")])
    return create_keyboard(buttons, columns=1)

def admin_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("👤 Пользователи", "admin_user_management")],
        [("🎫 Промокоды", "admin_promo_list")],
        [("📊 Статистика", "admin_stats")],
        [("📣 Рассылка", "admin_broadcast")],
        [("📋 Шаблоны", "admin_template_management")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons, columns=2)

def admin_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")]]
    )

def admin_promo_list_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    promo_list = list(promo_codes.keys())
    
    for i in range(0, len(promo_list), 2):
        row = []
        if i < len(promo_list):
            row.append((promo_list[i], f"promo_detail_{promo_list[i]}"))
        if i+1 < len(promo_list):
            row.append((promo_list[i+1], f"promo_detail_{promo_list[i+1]}"))
        buttons.append(row)
    
    buttons.append([("➕ Создать", "admin_create_promo")])
    buttons.append([("🔙 Назад", "admin_panel")])
    return create_keyboard(buttons, columns=2)

def admin_user_management_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🔍 Поиск пользователя", "admin_search_user")],
        [("📊 Топ пользователей", "admin_top_users")],
        [("🔙 Назад", "admin_panel")]
    ]
    return create_keyboard(buttons, columns=1)

def admin_template_management_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("📋 Список шаблонов", "template_list")],
        [("➕ Создать шаблон", "admin_create_template")],
        [("🔙 Назад", "admin_panel")]
    ]
    return create_keyboard(buttons, columns=1)

def template_list_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for template_id, template in templates.items():
        buttons.append([(f"📋 {template.name}", f"template_select_{template_id}")])
    
    buttons.append([("🔙 Назад", "admin_template_management")])
    return create_keyboard(buttons, columns=1)

def user_template_list_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for template_id, template in templates.items():
        buttons.append([(f"📋 {template.name}", f"user_template_select_{template_id}")])
    
    buttons.append([("🏠 Главное", "home")])
    return create_keyboard(buttons, columns=1)

def template_detail_keyboard(template_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [("✏️ Редактировать", f"edit_template_{template_id}")],
        [("🗑️ Удалить", f"delete_template_{template_id}")],
        [("🔙 Назад", "admin_template_management")]
    ]
    return create_keyboard(buttons, columns=1)

def user_template_options_keyboard(template_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [("🚀 Использовать", f"use_template_{template_id}")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons, columns=1)

def achievements_list_keyboard(user: User) -> InlineKeyboardMarkup:
    buttons = []
    for achievement_id, achievement in achievements.items():
        if achievement_id in user.achievements:
            unlocked_date = user.achievements[achievement_id]
            date_str = datetime.datetime.fromisoformat(unlocked_date).strftime("%d.%m.%Y")
            buttons.append([(f"✅ {achievement.icon} {achievement.name} ({date_str})", f"achievement_detail_{achievement_id}")])
        else:
            buttons.append([(f"🔒 {achievement.icon} {achievement.name}", "locked_achievement")])
    
    buttons.append([("🏠 Главное", "home")])
    return create_keyboard(buttons, columns=1)

def achievement_detail_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [("🔙 Назад", "achievements_list")]
    ]
    return create_keyboard(buttons, columns=1)

def settings_menu_keyboard(user: User) -> InlineKeyboardMarkup:
    notifications = "🔔 Уведомления: Вкл" if user.settings["notifications"] else "🔕 Уведомления: Выкл"
    language = "🌐 Русский" if user.settings["language"] == "ru" else "🌐 English"
    auto_translate = "🔄 Автоперевод: Вкл" if user.settings["auto_translate"] else "🔄 Автоперевод: Выкл"
    
    buttons = [
        [(notifications, "toggle_notifications")],
        [(language, "toggle_language")],
        [(auto_translate, "toggle_auto_translate")],
        [("🔙 Назад", "profile_menu")]
    ]
    return create_keyboard(buttons, columns=1)

def feedback_keyboard(content_type: str) -> InlineKeyboardMarkup:
    buttons = [
        [("⭐ 1", f"feedback_1_{content_type}"), ("⭐ 2", f"feedback_2_{content_type}"), ("⭐ 3", f"feedback_3_{content_type}")],
        [("⭐ 4", f"feedback_4_{content_type}"), ("⭐ 5", f"feedback_5_{content_type}")],
        [("🏠 Главное", "home")]
    ]
    return create_keyboard(buttons, columns=3)

def admin_user_options_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [("✏️ Редактировать", f"admin_edit_user_{user_id}")],
        [("🔙 Назад", "admin_user_management")]
    ]
    return create_keyboard(buttons, columns=1)

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

async def send_notification(user_id: int, text: str):
    try:
        user = await get_user(user_id)
        if user.settings["notifications"]:
            await bot.send_message(user_id, text)
    except Exception as e:
        logger.error(f"Notification failed for {user_id}: {e}")

# ===================== ФОРМАТИРОВАНИЕ =====================
def format_balance(user: User) -> str:
    user.check_premium_status()
    
    daily_status = "✅ Доступен" if user.can_claim_daily() else "❌ Уже получен"
    premium_status = "Активен" if user.is_premium else "Неактивен"
    next_level_xp = (user.level ** 2) * 100
    
    text = (
        f"💰 <b>ВАШ БАЛАНС</b>\n"
        f"══════════════════\n"
        f"⭐ Звезды: {hbold(user.stars)}\n"
        f"🎁 Ежедневный бонус: {daily_status}\n"
        f"💎 Премиум: {premium_status}\n"
        f"🏆 Уровень: {user.level} (XP: {user.xp}/{next_level_xp})\n"
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
            f"• 📋 Безлимитное использование шаблонов\n"
            f"• 🧠 Расширенный контекст\n"
            f"• 🖼️ Генерация до 8 вариантов\n"
            f"• 🤖 Эксклюзивные модели ИИ\n"
            f"• 🏆 Эксклюзивные достижения\n"
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
            f"• 📋 Безлимитное использование шаблонов\n"
            f"• 🧠 Расширенный контекст\n"
            f"• 🖼️ Генерация до 8 вариантов\n"
            f"• 🤖 Эксклюзивные модели ИИ\n"
            f"• 🏆 Эксклюзивные достижения\n\n"
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

def format_admin_stats() -> str:
    total_users = bot_stats["total_users"]
    active_today = bot_stats["active_today"]
    premium_users = sum(1 for u in users_db.values() if u.is_premium)
    total_stars = sum(u.stars for u in users_db.values())
    new_users_today = sum(1 for u in users_db.values() 
                          if datetime.datetime.fromisoformat(u.join_date).date() == datetime.datetime.now().date())
    
    images = bot_stats["images_generated"]
    texts = bot_stats["texts_generated"]
    avatars = bot_stats["avatars_generated"]
    logos = bot_stats["logos_generated"]
    templates_used = bot_stats["templates_used"]
    
    stars_purchased = bot_stats["stars_purchased"]
    premium_purchased = bot_stats["premium_purchased"]
    achievements_unlocked = bot_stats["achievements_unlocked"]
    
    return (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n"
        f"══════════════════\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"👤 Активных за сутки: {active_today}\n"
        f"💎 Премиум пользователей: {premium_users}\n"
        f"⭐ Звёзд в системе: {total_stars}\n"
        f"🆕 Новых сегодня: {new_users_today}\n"
        f"🏆 Достижений: {achievements_unlocked}\n\n"
        f"🔄 <b>Генерации:</b>\n"
        f"🎨 Изображений: {images}\n"
        f"📝 Текстов: {texts}\n"
        f"👤 Аватаров: {avatars}\n"
        f"🖼️ Логотипов: {logos}\n"
        f"📋 Шаблонов: {templates_used}\n\n"
        f"🛒 <b>Покупки:</b>\n"
        f"⭐ Звёзд куплено: {stars_purchased}\n"
        f"💎 Премиум подписок: {premium_purchased}\n"
        f"══════════════════"
    )

def format_promo_code(promo_code: str, promo_data: dict) -> str:
    promo_type = promo_data["type"]
    value = promo_data["value"]
    created_by = promo_data["created_by"]
    created_at = datetime.datetime.fromisoformat(promo_data["created_at"]).strftime("%d.%m.%Y %H:%M")
    used_count = promo_data.get("used_count", 0)
    limit = promo_data.get("limit", "∞")
    active = "✅ Активен" if promo_data.get("active", True) else "❌ Неактивен"
    
    text = (
        f"🎫 <b>ПРОМОКОД: {promo_code}</b>\n"
        f"══════════════════\n"
        f"🔢 Тип: {promo_type}\n"
        f"💎 Значение: {value}\n"
        f"👤 Создал: {created_by}\n"
        f"📅 Создан: {created_at}\n"
        f"🔄 Использован: {used_count} раз\n"
        f"🎯 Лимит: {limit}\n"
        f"🔔 Статус: {active}\n"
        f"══════════════════"
    )
    
    if "used_by" in promo_data and promo_data["used_by"]:
        text += "\n👥 Использовали:\n"
        for i, user in enumerate(promo_data["used_by"][:5]):
            text += f"{i+1}. {user['user_id']} ({user['date'][:10]})\n"
        if len(promo_data["used_by"]) > 5:
            text += f"... и еще {len(promo_data['used_by']) - 5}\n"
    
    return text

def format_template(template: Template) -> str:
    return (
        f"📋 <b>{template.name}</b>\n"
        f"══════════════════\n"
        f"📝 Описание: {template.description}\n"
        f"🏷️ Категория: {template.category}\n"
        f"🔄 Использовано: {template.usage_count} раз\n\n"
        f"🔍 Пример:\n{template.example}\n\n"
        f"📌 Промпт:\n<code>{template.prompt}</code>\n"
        f"══════════════════"
    )

def format_achievement(achievement: Achievement, unlocked: bool = False, date: str = None) -> str:
    status = f"✅ Разблокировано: {date}" if unlocked else "🔒 Не разблокировано"
    return (
        f"{achievement.icon} <b>{achievement.name}</b>\n"
        f"══════════════════\n"
        f"📝 {achievement.description}\n\n"
        f"🎯 Условие: {achievement.condition}\n"
        f"🎁 Награда: {achievement.reward} ⭐\n\n"
        f"{status}\n"
        f"══════════════════"
    )

def format_user_info(user: User) -> str:
    premium_status = "💎 Премиум (навсегда)" if user.is_premium and not user.premium_expiry else (
        f"💎 Премиум (осталось {int((user.premium_expiry - time.time()) / 86400)} дней)" if user.is_premium else "❌ Без премиума"
    )
    
    return (
        f"👤 <b>Пользователь ID: {user.user_id}</b>\n"
        f"══════════════════\n"
        f"⭐ Звёзд: {user.stars}\n"
        f"💎 Статус: {premium_status}\n"
        f"🏆 Уровень: {user.level} (XP: {user.xp})\n"
        f"🎨 Изображений: {user.images_generated}\n"
        f"📝 Текстов: {user.texts_generated}\n"
        f"📋 Шаблонов: {user.templates_used}\n"
        f"📅 Регистрация: {datetime.datetime.fromisoformat(user.join_date).strftime('%d.%m.%Y')}\n"
        f"══════════════════"
    )

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
        UserState.TEXT_GEN: handle_text_gen,
        UserState.AVATAR_GEN: handle_avatar_gen,
        UserState.LOGO_GEN: handle_logo_gen,
        UserState.TEMPLATE_GEN: handle_template_gen,
        UserState.PREMIUM_INFO: handle_premium_info,
        UserState.SHOP: handle_shop,
        UserState.SUPPORT: handle_support,
        UserState.REFERRAL: handle_referral,
        UserState.ACTIVATE_PROMO: handle_activate_promo,
        UserState.BALANCE: handle_balance,
        UserState.IMAGE_COUNT_SELECT: handle_image_count_select,
        UserState.IMAGE_MODEL_SELECT: handle_image_model_select,
        UserState.MODEL_SELECT: handle_model_select,
        UserState.TEXT_MODEL_SELECT: handle_text_model_select,
        UserState.ADMIN_PANEL: handle_admin_panel,
        UserState.ADMIN_CREATE_PROMO: handle_admin_create_promo,
        UserState.ADMIN_STATS: handle_admin_stats,
        UserState.ADMIN_BROADCAST: handle_admin_broadcast,
        UserState.ADMIN_PROMO_LIST: handle_admin_promo_list,
        UserState.ADMIN_USER_MANAGEMENT: handle_admin_user_management,
        UserState.ADMIN_TEMPLATE_MANAGEMENT: handle_admin_template_management,
        UserState.ADMIN_VIEW_USER: handle_admin_view_user,
        UserState.TEMPLATE_SELECT: handle_template_select,
        UserState.FEEDBACK: handle_feedback,
        UserState.ACHIEVEMENTS_LIST: handle_achievements_list  # Добавлен обработчик
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

# Добавленные обработчики для аватаров и логотипов
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

async def handle_template_gen(callback: CallbackQuery, user: User):
    # Реализация аналогична handle_image_gen
    await safe_edit_message(
        callback,
        "📋 <b>Генерация по шаблону</b>\n"
        "══════════════════\n"
        "Выберите шаблон:",
        reply_markup=user_template_list_keyboard()
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

async def handle_admin_panel(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "👑 <b>АДМИН-ПАНЕЛЬ</b>\n"
        "══════════════════\n"
        "Выберите действие:",
        reply_markup=admin_keyboard()
    )

async def handle_admin_create_promo(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "🎫 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n"
        "══════════════════\n"
        "Введите данные промокода в формате:\n"
        "<code>тип:значение:лимит</code>\n\n"
        "Доступные типы:\n"
        "• <code>stars</code> - звёзды (например: stars:100:10)\n"
        "• <code>premium</code> - премиум (например: premium:30:5)\n\n"
        "Для вечного премиума: <code>premium:forever:0</code>\n"
        "Лимит: 0 = безлимитно",
        reply_markup=admin_cancel_keyboard()
    )

async def handle_admin_stats(callback: CallbackQuery, user: User):
    # Обновляем статистику активных пользователей
    bot_stats["active_today"] = sum(
        1 for u in users_db.values() 
        if time.time() - u.last_interaction < 86400
    )
    
    stats = format_admin_stats()
    await safe_edit_message(callback, stats, reply_markup=admin_keyboard())

async def handle_admin_broadcast(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "📣 <b>РАССЫЛКА СООБЩЕНИЙ</b>\n"
        "══════════════════\n"
        "Введите сообщение для рассылки:",
        reply_markup=admin_cancel_keyboard()
    )

async def handle_admin_promo_list(callback: CallbackQuery, user: User):
    if not promo_codes:
        await safe_edit_message(
            callback,
            "🎫 <b>СПИСОК ПРОМОКОДОВ</b>\n"
            "══════════════════\n"
            "❌ Промокоды не найдены",
            reply_markup=admin_keyboard()
        )
        return
        
    await safe_edit_message(
        callback,
        "🎫 <b>СПИСОК ПРОМОКОДОВ</b>\n"
        "══════════════════\n"
        f"Найдено промокодов: {len(promo_codes)}\n"
        "Выберите промокод для просмотра:",
        reply_markup=admin_promo_list_keyboard()
    )

async def handle_admin_promo_detail(callback: CallbackQuery, user: User, promo_code: str):
    promo_data = promo_codes.get(promo_code)
    if not promo_data:
        await callback.answer("❌ Промокод не найден", show_alert=True)
        return
        
    text = format_promo_code(promo_code, promo_data)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Активировать" if promo_data.get("active", True) else "❌ Деактивировать", 
            callback_data=f"promo_toggle_{promo_code}"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_promo_list")]
    ])
    
    await safe_edit_message(callback, text, reply_markup=keyboard)

async def handle_admin_user_management(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "👤 <b>УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ</b>\n"
        "══════════════════\n"
        "Выберите действие:",
        reply_markup=admin_user_management_keyboard()
    )

async def handle_admin_template_management(callback: CallbackQuery, user: User):
    await safe_edit_message(
        callback,
        "📋 <b>УПРАВЛЕНИЕ ШАБЛОНАМИ</b>\n"
        "══════════════════\n"
        "Выберите действие:",
        reply_markup=admin_template_management_keyboard()
    )

async def handle_admin_view_user(callback: CallbackQuery, user: User, user_id: int):
    if user_id not in users_db:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
        
    target_user = users_db[user_id]
    text = format_user_info(target_user)
    await safe_edit_message(
        callback,
        text,
        reply_markup=admin_user_options_keyboard(user_id)
    )

async def handle_template_select(callback: CallbackQuery, user: User):
    if not templates:
        await callback.answer("❌ Шаблоны не найдены", show_alert=True)
        return
        
    await safe_edit_message(
        callback,
        "📋 <b>ВЫБОР ШАБЛОНА</b>\n"
        "══════════════════\n"
        "Выберите шаблон для генерации контента:",
        reply_markup=user_template_list_keyboard()
    )

async def handle_feedback(callback: CallbackQuery, user: User):
    # Реализация будет добавлена позже
    pass

async def handle_achievements_list(callback: CallbackQuery, user: User):
    text = "🏆 <b>ВАШИ ДОСТИЖЕНИЯ</b>\n══════════════════\n"
    unlocked_count = len(user.achievements)
    total_count = len(achievements)
    text += f"🔓 Разблокировано: {unlocked_count}/{total_count}\n\n"
    
    await safe_edit_message(
        callback,
        text,
        reply_markup=achievements_list_keyboard(user)
    )

# ===================== ОБРАБОТКА КОМАНД =====================
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

@dp.callback_query(F.data == "admin_cancel")
async def admin_cancel_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.state = UserState.ADMIN_PANEL
    await show_menu(callback, user)
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

@dp.callback_query(F.data == "admin_create_promo")
async def admin_create_promo(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.ADMIN_CREATE_PROMO
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.ADMIN_STATS
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.ADMIN_BROADCAST
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "admin_promo_list")
async def admin_promo_list(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.ADMIN_PROMO_LIST
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data.startswith("promo_detail_"))
async def admin_promo_detail(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    promo_code = callback.data.split('_', 2)[2]
    await handle_admin_promo_detail(callback, user, promo_code)

@dp.callback_query(F.data.startswith("promo_toggle_"))
async def promo_toggle_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    promo_code = callback.data.split('_', 2)[2]
    promo_data = promo_codes.get(promo_code)
    if not promo_data:
        await callback.answer("❌ Промокод не найден", show_alert=True)
        return
    
    # Переключаем статус
    promo_data["active"] = not promo_data.get("active", True)
    promo_codes[promo_code] = promo_data
    
    # Сохраняем
    with open(PROMO_FILE, 'w', encoding='utf-8') as f:
        json.dump(promo_codes, f, ensure_ascii=False, indent=2)
    
    await callback.answer(f"✅ Статус изменен на {'активен' if promo_data['active'] else 'неактивен'}")
    await handle_admin_promo_detail(callback, user, promo_code)

@dp.callback_query(F.data == "broadcast_confirm")
async def broadcast_confirm(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    await callback.message.delete()
    await execute_broadcast(user.user_id)

@dp.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    admin_broadcast_data[user.user_id] = "CANCEL"
    await callback.answer("⏹️ Рассылка отменена")
    await callback.message.delete()
    await bot.send_message(user.user_id, "❌ Рассылка отменена", reply_markup=admin_keyboard())

@dp.callback_query(F.data == "admin_user_management")
async def admin_user_management(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.ADMIN_USER_MANAGEMENT
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "admin_search_user")
async def admin_search_user(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    await safe_edit_message(
        callback,
        "🔍 <b>ПОИСК ПОЛЬЗОВАТЕЛЯ</b>\n"
        "══════════════════\n"
        "Введите ID пользователя:",
        reply_markup=admin_cancel_keyboard()
    )

@dp.callback_query(F.data.startswith("admin_view_user_"))
async def admin_view_user(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split('_')[3])
    user.push_menu(user.state, {})
    user.state = UserState.ADMIN_VIEW_USER
    user.mark_modified()
    await handle_admin_view_user(callback, user, user_id)

@dp.callback_query(F.data.startswith("admin_edit_user_"))
async def admin_edit_user(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split('_')[3])
    if user_id not in users_db:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    target_user = users_db[user_id]
    await safe_edit_message(
        callback,
        f"✏️ <b>РЕДАКТИРОВАНИЕ ПОЛЬЗОВАТЕЛЯ {user_id}</b>\n"
        "══════════════════\n"
        "Введите данные в формате:\n"
        "<code>поле:значение</code>\n\n"
        "Доступные поля:\n"
        "• stars - количество звезд\n"
        "• premium - срок премиума в днях (0 для снятия)\n"
        "Пример: <code>stars:500</code> или <code>premium:30</code>",
        reply_markup=admin_cancel_keyboard()
    )

@dp.callback_query(F.data == "admin_template_management")
async def admin_template_management(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.ADMIN_TEMPLATE_MANAGEMENT
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data == "admin_create_template")
async def admin_create_template(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    await safe_edit_message(
        callback,
        "📋 <b>СОЗДАНИЕ ШАБЛОНА</b>\n"
        "══════════════════\n"
        "Введите данные шаблона в формате JSON:\n"
        "<code>{'name': 'Название', 'description': 'Описание', 'prompt': 'Промпт', 'example': 'Пример', 'category': 'Категория'}</code>\n\n"
        "Категории: Текст, Изображение",
        reply_markup=admin_cancel_keyboard()
    )

@dp.callback_query(F.data == "template_list")
async def template_list(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    if not templates:
        await callback.answer("❌ Шаблоны не найдены", show_alert=True)
        return
        
    await safe_edit_message(
        callback,
        "📋 <b>СПИСОК ШАБЛОНОВ</b>\n"
        "══════════════════\n"
        f"Найдено шаблонов: {len(templates)}\n"
        "Выберите шаблон для управления:",
        reply_markup=template_list_keyboard()
    )

@dp.callback_query(F.data.startswith("template_select_"))
async def template_select(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    template_id = callback.data.split('_', 2)[2]
    template = templates.get(template_id)
    if not template:
        await callback.answer("❌ Шаблон не найден", show_alert=True)
        return
        
    text = format_template(template)
    await safe_edit_message(
        callback,
        text,
        reply_markup=template_detail_keyboard(template_id)
    )

@dp.callback_query(F.data.startswith("edit_template_"))
async def edit_template(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    template_id = callback.data.split('_', 2)[2]
    template = templates.get(template_id)
    if not template:
        await callback.answer("❌ Шаблон не найден", show_alert=True)
        return
        
    await safe_edit_message(
        callback,
        f"✏️ <b>РЕДАКТИРОВАНИЕ ШАБЛОНА {template.name}</b>\n"
        "══════════════════\n"
        "Введите новые данные в формате JSON:",
        reply_markup=admin_cancel_keyboard()
    )

@dp.callback_query(F.data.startswith("delete_template_"))
async def delete_template(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    template_id = callback.data.split('_', 2)[2]
    if template_id in templates:
        del templates[template_id]
        await save_db()
        await callback.answer("✅ Шаблон удален", show_alert=True)
        await template_list(callback)
    else:
        await callback.answer("❌ Шаблон не найден", show_alert=True)

@dp.callback_query(F.data == "template_select")
async def user_template_select(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    if not templates:
        await callback.answer("❌ Шаблоны не найдены", show_alert=True)
        return
        
    user.push_menu(user.state, {})
    user.state = UserState.TEMPLATE_SELECT
    user.mark_modified()
    await show_menu(callback, user)
    await callback.answer()

@dp.callback_query(F.data.startswith("user_template_select_"))
async def user_template_select_detail(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    template_id = callback.data.split('_', 3)[3]
    template = templates.get(template_id)
    if not template:
        await callback.answer("❌ Шаблон не найден", show_alert=True)
        return
        
    user.push_menu(user.state, {})
    user.state = UserState.TEMPLATE_GEN
    user.mark_modified()
    # Здесь будет вызов функции генерации по шаблону

@dp.callback_query(F.data.startswith("use_template_"))
async def use_template(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    template_id = callback.data.split('_', 2)[2]
    template = templates.get(template_id)
    if not template:
        await callback.answer("❌ Шаблон не найден", show_alert=True)
        return
        
    user.push_menu(user.state, {})
    user.state = UserState.TEMPLATE_GEN
    user.mark_modified()
    # Здесь будет вызов функции генерации по шаблону

@dp.callback_query(F.data == "achievements_list")
async def achievements_list(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.ACHIEVEMENTS_LIST
    user.mark_modified()
    await handle_achievements_list(callback, user)
    await callback.answer()

@dp.callback_query(F.data.startswith("achievement_detail_"))
async def achievement_detail(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    achievement_id = callback.data.split('_', 2)[2]
    achievement = achievements.get(achievement_id)
    if not achievement:
        await callback.answer("❌ Достижение не найдено", show_alert=True)
        return
        
    unlocked = achievement_id in user.achievements
    date = user.achievements.get(achievement_id)
    text = format_achievement(achievement, unlocked, date)
    
    await safe_edit_message(
        callback,
        text,
        reply_markup=achievement_detail_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "settings_menu")
async def settings_menu(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.push_menu(user.state, {})
    user.state = UserState.SETTINGS_MENU
    user.mark_modified()
    await safe_edit_message(
        callback,
        "⚙️ <b>НАСТРОЙКИ</b>\n"
        "══════════════════\n"
        "Выберите параметр для изменения:",
        reply_markup=settings_menu_keyboard(user)
    )
    await callback.answer()

@dp.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.settings["notifications"] = not user.settings["notifications"]
    user.mark_modified()
    status = "включены" if user.settings["notifications"] else "выключены"
    await callback.answer(f"🔔 Уведомления {status}", show_alert=True)
    await settings_menu(callback)

@dp.callback_query(F.data == "toggle_language")
async def toggle_language(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.settings["language"] = "en" if user.settings["language"] == "ru" else "ru"
    user.mark_modified()
    lang = "Русский" if user.settings["language"] == "ru" else "English"
    await callback.answer(f"🌐 Язык изменен на {lang}", show_alert=True)
    await settings_menu(callback)

@dp.callback_query(F.data == "toggle_auto_translate")
async def toggle_auto_translate(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    user.settings["auto_translate"] = not user.settings["auto_translate"]
    user.mark_modified()
    status = "включен" if user.settings["auto_translate"] else "выключен"
    await callback.answer(f"🔄 Автоперевод {status}", show_alert=True)
    await settings_menu(callback)

@dp.callback_query(F.data.startswith("feedback_"))
async def process_feedback(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not await ensure_subscription(callback, user):
        return
    
    parts = callback.data.split('_')
    if len(parts) < 3:
        await callback.answer("❌ Ошибка обработки", show_alert=True)
        return
        
    rating = int(parts[1])
    content_type = parts[2]
    
    user.feedback_count += 1
    user.last_feedback = datetime.datetime.now().isoformat()
    
    # Награда за фидбек
    reward = min(5, rating)
    user.stars += reward
    user.add_xp(reward)
    
    await callback.answer(f"⭐ Спасибо за оценку! +{reward} ⭐", show_alert=True)
    
    # Возвращаемся в главное меню
    user.state = UserState.MAIN_MENU
    user.menu_stack = []
    await show_menu(callback, user)
    await save_db()

# ===================== ОБРАБОТКА СООБЩЕНИЙ =====================
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
        "📋 <b>Шаблоны</b> - готовые решения для популярных задач\n"
        "💎 <b>Премиум</b> - безлимитные генерации ♾️ \n\n"
        f"🎁 <b>Стартовый бонус:</b> {START_BALANCE_STARS} ⭐\n"
        "<i>Используй для тестирования возможностей!</i>\n\n"
        f"══════════════════"
    )
    user.state = UserState.MAIN_MENU
    await message.answer(welcome_text, reply_markup=main_keyboard(user))
    await save_db()

@dp.message(Command("admin"))
async def admin_command(message: Message):
    await process_admin_command(message)

@dp.message(Command("balance"))
async def balance_command(message: Message):
    user = await get_user(message.from_user.id)
    if not await ensure_subscription(message, user):
        return
    
    user.state = UserState.BALANCE
    text = format_balance(user)
    await message.answer(text, reply_markup=balance_keyboard())

@dp.message(Command("stats"))
async def stats_command(message: Message):
    user = await get_user(message.from_user.id)
    if user.user_id != ADMIN_ID:
        return
    
    stats = format_admin_stats()
    await message.answer(stats)

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
                "last_image_prompt", "last_image_url"
            )
            
        elif user.state == UserState.TEXT_GEN:
            await generate_text(user, text, message)
            
        elif user.state == UserState.AVATAR_GEN:
            await generate_content(
                user, text, message,
                "avatar", AVATAR_COST, IMAGE_MODELS[user.image_model],
                avatar_options_keyboard(),
                "last_avatar_prompt", "last_avatar_url"
            )
            
        elif user.state == UserState.LOGO_GEN:
            await generate_content(
                user, text, message,
                "logo", LOGO_COST, IMAGE_MODELS[user.image_model],
                logo_options_keyboard(),
                "last_logo_prompt", "last_logo_url"
            )
            
        elif user.state == UserState.ACTIVATE_PROMO:
            await process_promo_code(user, text, message)
            
        elif user.state == UserState.ADMIN_CREATE_PROMO:
            await process_promo_creation(message)
            
        elif user.state == UserState.ADMIN_BROADCAST:
            await process_broadcast_message(message)
            
        elif user.state == UserState.ADMIN_SEARCH_USER:
            await process_admin_search_user(message, text)
            
        elif user.state == UserState.ADMIN_EDIT_USER:
            await process_admin_edit_user(message, text)
            
        elif user.state == UserState.ADMIN_CREATE_TEMPLATE:
            await process_admin_create_template(message, text)
            
        elif user.state == UserState.TEMPLATE_GEN:
            await process_template_generation(user, text, message)
            
    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await animate_error(message, f"⚠️ <b>Ошибка:</b> {str(e)}")
        ERROR_COUNT.inc()
    finally:
        await save_db()

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
    url_field: str
):
    start_time = time.time()
    
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
        
        processing_msg = await animate_loading(message, f"🪄 Генерирую {content_type}...")
        
        # Автоперевод при необходимости
        if user.settings["auto_translate"] and detect_language(text) != 'en':
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
            user.images_generated += count
            bot_stats["images_generated"] += count
            IMAGES_GENERATED.inc(count)
            
            # Отправляем клавиатуру отдельным сообщением
            await sent_messages[-1].answer(
                f"✅ {content_type.capitalize()} готовы!",
                reply_markup=options_keyboard
            )
        
        else:  # Одно изображение
            encoded_prompt = urllib.parse.quote(enhanced_prompt)
            image_url = f"{IMAGE_URL}{encoded_prompt}?nologo=true"
            
            if not user.is_premium:
                user.stars -= cost
                user.mark_modified()
            
            caption_text = trim_caption(
                f"{content_type.capitalize()} <b>Готово!</b>\n══════════════════\n"
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
            
            # Обновляем счетчики
            if content_type == "image":
                user.images_generated += 1
                bot_stats["images_generated"] += 1
                IMAGES_GENERATED.inc()
            elif content_type == "avatar":
                user.avatars_generated += 1
                bot_stats["avatars_generated"] += 1
                AVATARS_GENERATED.inc()
            elif content_type == "logo":
                user.logos_generated += 1
                bot_stats["logos_generated"] += 1
                LOGOS_GENERATED.inc()
                
            user.mark_modified()
            
            await animate_success(message, f"✅ {content_type.capitalize()} готов!")
        
        # Начисление опыта
        user.add_xp(3)
        
        # Проверка достижений
        unlocked = user.check_achievements()
        if unlocked:
            for achievement_id in unlocked:
                achievement = achievements[achievement_id]
                await send_notification(
                    user.user_id,
                    f"🏆 <b>НОВОЕ ДОСТИЖЕНИЕ!</b>\n"
                    f"══════════════════\n"
                    f"{achievement.icon} {achievement.name}\n"
                    f"{achievement.description}\n\n"
                    f"🎁 Награда: {achievement.reward} ⭐"
                )
        
    except aiohttp.ClientError as e:
        logger.error(f"Network error: {e}")
        await animate_error(message, "⚠️ Ошибка сети, попробуйте позже")
        ERROR_COUNT.inc()
    except asyncio.TimeoutError:
        logger.error("Timeout during generation")
        await animate_error(message, "⌛ Таймаут при генерации")
        ERROR_COUNT.inc()
    except Exception as e:
        logger.exception("Unhandled error in generation")
        await animate_error(message, f"⛔ Критическая ошибка: {str(e)}")
        ERROR_COUNT.inc()
    finally:
        duration = time.time() - start_time
        REQUEST_TIME.observe(duration)
        await save_db()

async def generate_text(user: User, text: str, message: Message):
    start_time = time.time()
    
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
        
        # Обновляем счетчики
        user.texts_generated += 1
        bot_stats["texts_generated"] += 1
        TEXTS_GENERATED.inc()
        
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
        
        # Начисление опыта
        user.add_xp(5)
        
        # Проверка достижений
        unlocked = user.check_achievements()
        if unlocked:
            for achievement_id in unlocked:
                achievement = achievements[achievement_id]
                await send_notification(
                    user.user_id,
                    f"🏆 <b>НОВОЕ ДОСТИЖЕНИЕ!</b>\n"
                    f"══════════════════\n"
                    f"{achievement.icon} {achievement.name}\n"
                    f"{achievement.description}\n\n"
                    f"🎁 Награда: {achievement.reward} ⭐"
                )
        
    except TelegramBadRequest as e:
        logger.error(f"HTML formatting error: {e}")
        # Пытаемся отправить без форматирования
        await processing_msg.delete()
        await message.answer("⚠️ Ошибка форматирования, отправляю текст без оформления:")
        await message.answer(result[:4000])
        ERROR_COUNT.inc()
    except aiohttp.ClientError as e:
        logger.error(f"Network error: {e}")
        await animate_error(message, "⚠️ Ошибка сети, попробуйте позже")
        ERROR_COUNT.inc()
    except asyncio.TimeoutError:
        logger.error("Timeout during text generation")
        await animate_error(message, "⌛ Таймаут при генерации")
        ERROR_COUNT.inc()
    except Exception as e:
        logger.exception("Unhandled error in text generation")
        await animate_error(message, f"⛔ Критическая ошибка: {str(e)}")
        ERROR_COUNT.inc()
    finally:
        duration = time.time() - start_time
        REQUEST_TIME.observe(duration)
        await save_db()

async def process_template_generation(user: User, text: str, message: Message):
    start_time = time.time()
    
    try:
        if not await ensure_subscription(message, user):
            return
            
        if len(text) > MAX_TEMPLATE_LENGTH:
            await animate_error(message, f"⚠️ Превышен лимит {MAX_TEMPLATE_LENGTH} символов")
            return
            
        # Получаем шаблон из контекста
        template_id = user.last_text
        template = templates.get(template_id)
        if not template:
            await animate_error(message, "❌ Шаблон не найден")
            return
            
        # Формируем промпт
        full_prompt = template.prompt.format(data=text)
        
        # Определяем тип генерации
        if template.category == "Изображение":
            user.last_image_prompt = full_prompt
            await generate_content(
                user, full_prompt, message,
                "image", IMAGE_COST, IMAGE_MODELS[user.image_model],
                image_options_keyboard(user),
                "last_image_prompt", "last_image_url"
            )
        else:
            user.last_text = full_prompt
            await generate_text(user, full_prompt, message)
        
        # Обновляем статистику использования шаблона
        template.usage_count += 1
        user.templates_used += 1
        bot_stats["templates_used"] += 1
        TEMPLATES_USED.inc()
        
    except KeyError as e:
        logger.error(f"Template format error: {e}")
        await animate_error(message, "⚠️ Ошибка в данных шаблона")
        ERROR_COUNT.inc()
    except Exception as e:
        logger.exception("Unhandled error in template generation")
        await animate_error(message, f"⛔ Ошибка: {str(e)}")
        ERROR_COUNT.inc()
    finally:
        duration = time.time() - start_time
        REQUEST_TIME.observe(duration)
        await save_db()

# ===================== ЗАПУСК ПРИЛОЖЕНИЯ =====================
from contextlib import asynccontextmanager

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
    
    # Фоновые задачи
    asyncio.create_task(auto_save_db())
    asyncio.create_task(self_pinger())
    
    # Очистка предыдущих обновлений
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запуск бота в фоне
    asyncio.create_task(dp.start_polling(bot, skip_updates=True))
    
    yield
    
    # Остановка при завершении
    await save_db()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

# ===================== ENDPOINT ДЛЯ ПРОВЕРКИ =====================
@app.api_route("/", methods=["GET", "HEAD", "POST"])
async def health_check(request: Request):
    # Для HEAD-запросов возвращаем только статус
    if request.method == "HEAD":
        return Response(status_code=200)
    
    # Для GET/POST возвращаем полную информацию
    return JSONResponse(content={
        "status": "active",
        "service": "AI Content Generator Bot",
        "version": "3.0",
        "bot_username": BOT_USERNAME,
        "total_users": len(users_db),
        "last_update": bot_stats.get("last_update", "unknown"),
        "endpoints": {
            "health": "/",
            "metrics": "/metrics",
            "webhook": "/webhook"
        }
    })

@app.get("/metrics")
async def metrics():
    # Обновляем значения метрик
    USERS_TOTAL.set(len(users_db))
    ACTIVE_USERS.set(bot_stats["active_today"])
    
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

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
