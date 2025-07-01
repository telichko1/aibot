import time
import threading
from flask import Flask
from main import bot, logger, user_context
from datetime import datetime

app = Flask(__name__)

# Конфигурация
PORT = 8080
CHECK_INTERVAL = 60  # Проверка каждую минуту

@app.route('/')
def health_check():
    active_users = sum(1 for ctx in user_context.values() 
                     if time.time() - ctx['last_interaction'] < 3600)
    return f"Bot Status: OK | Active Users: {active_users}", 200

def run_bot():
    """Основная функция запуска бота с улучшенной обработкой ошибок"""
    while True:
        try:
            logger.info("Initializing bot...")
            
            # 1. Очистка предыдущих сессий
            bot.remove_webhook()
            time.sleep(2)
            
            # 2. Настройка поллинга
            bot.infinity_polling(
                none_stop=True,
                interval=5,
                timeout=30,
                long_polling_timeout=25,
                allowed_updates=["message", "callback_query"]
            )
            
        except Exception as e:
            logger.error(f"Critical bot error: {str(e)}")
            time.sleep(15)

def background_tasks():
    """Фоновые проверки"""
    while True:
        try:
            # Проверка активности пользователей
            now = time.time()
            for user_id, ctx in list(user_context.items()):
                if now - ctx['last_interaction'] > 86400:  # 24 часа
                    del user_context[user_id]
                    
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"Background task error: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    # Запуск фоновых задач
    threading.Thread(target=background_tasks, daemon=True).start()
    
    # Запуск Flask
    threading.Thread(
        target=app.run,
        kwargs={'host':'0.0.0.0','port':PORT},
        daemon=True
    ).start()
    
    # Основной цикл бота
    run_bot()
