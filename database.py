import aiosqlite
import logging

DB_NAME = "bot.db"
logger = logging.getLogger(__name__)


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT
        )
        """)
        await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_id ON messages(user_id)
        """)
        await db.commit()


async def save_message(user_id, role, content):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content)
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка при сохранении сообщения: {e}")


async def get_last_messages(user_id, limit=5):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit)
            )
            rows = await cursor.fetchall()

        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    except Exception as e:
        logger.error(f"Ошибка при получении истории сообщений: {e}")
        return []
