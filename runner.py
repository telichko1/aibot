import os
import threading
import requests
import time
from main import run_bot  # Импортируем функцию запуска бота из main.py
from flask import Flask

# Создаем Flask приложение для веб-сервера
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot runner is alive and kicking!"

# Функция для пинга самого себя
def keep_alive():
    while True:
        try:
            # Пингуем собственный URL (замените на ваш)
            requests.get("https://aibot-1-2wft.onrender.com")
            print("Successfully pinged self")
        except Exception as e:
            print(f"Ping error: {e}")
        time.sleep(300)  # Пинг каждые 5 минут (меньше 15 минут)

# Запускаем бота в отдельном потоке
def run_bot_in_thread():
    while True:
        try:
            run_bot()
        except Exception as e:
            print(f"Bot crashed: {e}. Restarting in 10 seconds...")
            time.sleep(10)

# Запускаем Flask сервер в отдельном потоке
def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    # Запускаем поток с ботом
    bot_thread = threading.Thread(target=run_bot_in_thread)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем Flask сервер
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем пинг в основном потоке
    keep_alive()
