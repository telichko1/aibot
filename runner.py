# В runner.py добавьте постоянные пинги
import requests
import threading

def keep_alive():
    while True:
        requests.get("https://aibot-1-2wft.onrender.com")
        time.sleep(300)  # Пинг каждые 5 минут

threading.Thread(target=keep_alive, daemon=True).start()
