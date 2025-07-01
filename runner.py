import time
import threading
import requests
from flask import Flask
from main import bot, logger, TEXT_GENERATION_URL

app = Flask(__name__)

# Конфигурация
PING_INTERVAL = 300  # 5 минут
API_RETRY_DELAY = 2  # Задержка между запросами к API

@app.route('/')
def health_check():
    return "Bot is running", 200

def keep_alive():
    """Периодический пинг для предотвращения сна"""
    while True:
        try:
            requests.get("https://text.pollinations.ai", timeout=5)
            logger.info("API health check: OK")
        except Exception as e:
            logger.warning(f"API health check failed: {str(e)}")
        time.sleep(PING_INTERVAL)

def api_available():
    """Проверка доступности API"""
    try:
        test_prompt = {"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"test"}]}
        response = requests.post(TEXT_GENERATION_URL, json=test_prompt, timeout=10)
        return response.status_code == 200
    except:
        return False

def run_bot_safely():
    """Безопасный запуск бота с обработкой ошибок"""
    while True:
        try:
            # Очистка предыдущих соединений
            bot.remove_webhook()
            time.sleep(1)
            
            # Проверка API перед запуском
            if not api_available():
                logger.error("API недоступен, задержка перед запуском")
                time.sleep(30)
                continue
                
            logger.info("Starting bot polling...")
            bot.infinity_polling(
                none_stop=True,
                interval=3,
                timeout=30,
                long_polling_timeout=20,
                restart_on_change=True
            )
            
        except Exception as e:
            logger.error(f"Bot crash: {str(e)}")
            time.sleep(15)

if __name__ == "__main__":
    # Запуск фоновых процессов
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Запуск Flask в отдельном потоке
    flask_thread = threading.Thread(
        target=app.run,
        kwargs={'host':'0.0.0.0','port':8080},
        daemon=True
    )
    flask_thread.start()
    
    # Основной цикл бота
    run_bot_safely()
