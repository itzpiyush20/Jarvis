import logging

logger = logging.getLogger("JarvisNotify")

def notify_user(title: str, message: str):
    """
    Ultra-lightweight notification logger.
    Avoids spawning heavy external shell processes to keep voice latency near zero.
    """
    logger.info(f"[NOTIFY] {title}: {message}")

if __name__ == "__main__":
    notify_user("Jarvis Online", "Listening for 'Jarvis' or 'Hey Jarvis'")
