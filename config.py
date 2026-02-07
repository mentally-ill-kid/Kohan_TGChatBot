import os
import logging
from dotenv import load_dotenv
from pathlib import Path

# Ищем .env файл в текущей директории или на уровень выше
env_path = Path(__file__).parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
HF_API_KEY = os.getenv("HF_API_KEY")

MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")

BOT_CREATOR = os.getenv("BOT_CREATOR", "Тимофей Т")
BOT_NAME = os.getenv("BOT_NAME", "Хуесос")
BOT_RULES = os.getenv("BOT_RULES", "")

logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.warning("BOT_TOKEN не найден в переменных окружения!")

if not HF_API_KEY:
    logger.warning("HF_API_KEY не найден в переменных окружения!")
