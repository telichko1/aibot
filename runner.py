import requests
import time

def health_check():
    while True:
        try:
            # Периодическая проверка доступности API
            resp = requests.get("https://text.pollinations.ai", timeout=5)
            if resp.status_code != 200:
                logger.warning(f"API Health Check failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"Health Check Error: {str(e)}")
        time.sleep(60)

if __name__ == "__main__":
    import threading
    threading.Thread(target=health_check, daemon=True).start()
    
    from main import run_bot
    while True:
        try:
            run_bot()
        except Exception as e:
            logger.critical(f"Fatal error: {str(e)}")
            time.sleep(30)
