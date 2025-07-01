import os
import threading
import requests
from main import run_bot  # Импортируем функцию запуска бота из main.py

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
    run_bot()

if __name__ == "__main__":
    # Запускаем поток с ботом
    bot_thread = threading.Thread(target=run_bot_in_thread)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем пинг в основном потоке
    keep_alive()
