import logging
import re
from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import CommandStart
from llm import ask_llm
from database import save_message, get_last_messages
from config import BOT_CREATOR, BOT_NAME, BOT_RULES

router = Router()
logger = logging.getLogger(__name__)


def get_system_prompt() -> str:
    """
    Формирует системный промпт с настройками бота.
    """
    prompt_parts = [
        f"Ты полезный AI-ассистент по имени {BOT_NAME}.",
        "Отвечай на русском языке.",
        "Будь вежливым, информативным и кратким.",
        f"Твой создатель: {BOT_CREATOR}.",
        "Если тебя спрашивают о создателе, упомяни это имя.",
    ]
    
    # Добавляем дополнительные правила, если они указаны
    if BOT_RULES:
        rules = [rule.strip() for rule in BOT_RULES.split(';') if rule.strip()]
        for rule in rules:
            prompt_parts.append(rule)
    
    return " ".join(prompt_parts)


def is_bot_mentioned(message: Message, bot_username: str, bot_id: int) -> bool:
    """
    Проверяет, упомянут ли бот в сообщении.
    Проверяет как упоминания через @username, так и через reply на сообщение бота.
    """
    if not message.text:
        return False
    
    bot_username_lower = bot_username.lower()
    
    # Проверяем упоминания через @username
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                # Извлекаем текст упоминания
                mention_text = message.text[entity.offset:entity.offset + entity.length].lower()
                # Убираем @ для сравнения
                if mention_text.lstrip('@') == bot_username_lower:
                    return True
            elif entity.type == "text_mention":
                # Прямое упоминание через user ID
                if entity.user and entity.user.id == bot_id:
                    return True
    
    # Проверяем, является ли это ответом на сообщение бота
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == bot_id:
            return True
    
    # Проверяем, упомянут ли бот в тексте (на случай, если entities не работают)
    if f"@{bot_username}" in message.text or f"@{bot_username_lower}" in message.text.lower():
        return True
    
    return False


def extract_question_text(message: Message, bot_username: str) -> str:
    """
    Извлекает текст вопроса, убирая упоминание бота.
    Если это reply на сообщение бота, возвращает весь текст.
    """
    if not message.text:
        return ""
    
    text = message.text
    bot_username_lower = bot_username.lower()
    
    # Если это reply на сообщение бота, возвращаем весь текст
    if message.reply_to_message and message.reply_to_message.from_user:
        # Это reply, просто возвращаем текст
        return text.strip()
    
    # Убираем упоминания бота из текста
    if message.entities:
        # Сортируем entities по offset в обратном порядке, чтобы удалять с конца
        entities_to_remove = []
        for entity in message.entities:
            if entity.type == "mention":
                mention_text = message.text[entity.offset:entity.offset + entity.length].lower()
                if mention_text.lstrip('@') == bot_username_lower:
                    entities_to_remove.append((entity.offset, entity.offset + entity.length))
            elif entity.type == "text_mention":
                # Для text_mention просто пропускаем, текст остаётся
                pass
        
        # Удаляем упоминания с конца к началу
        for start, end in sorted(entities_to_remove, reverse=True):
            text = text[:start] + text[end:]
    
    # Убираем лишние пробелы и переносы строк
    text = text.strip()
    # Убираем множественные пробелы
    text = re.sub(r'\s+', ' ', text)
    
    return text


@router.message(CommandStart())
async def start(message: Message, bot: Bot):
    bot_info = await bot.get_me()
    bot_username = bot_info.username or "бот"
    
    welcome_text = (
        "Привет! Я AI-бот 🤖\n\n"
        "📱 В личных сообщениях: просто задавайте вопросы\n\n"
        f"👥 В группах:\n"
        f"• Упоминайте меня: @{bot_username} ваш вопрос\n"
        f"• Или отвечайте на моё сообщение\n\n"
        f"⚠️ ВАЖНО для работы в группах:\n"
        f"1. Добавьте бота как администратора (или настройте через BotFather)\n"
        f"2. В BotFather: /setprivacy → выберите бота → Disable (чтобы видеть все сообщения)\n"
        f"3. Или используйте reply на сообщения бота"
    )
    
    await message.answer(welcome_text)


@router.message()
async def chat(message: Message, bot: Bot):
    # Обрабатываем только текстовые сообщения
    if not message.text:
        return
    
    # Получаем информацию о боте
    bot_info = await bot.get_me()
    bot_username = bot_info.username or ""
    bot_id = bot_info.id
    
    # Проверка на наличие username (должен быть всегда, но на всякий случай)
    if not bot_username:
        logger.warning("У бота нет username, работа в группах может быть ограничена")
    
    # Проверка на наличие from_user
    if not message.from_user:
        logger.warning("Сообщение без from_user, пропускаем")
        return
    
    user_id = message.from_user.id
    
    # Определяем тип чата
    is_private = message.chat.type == "private"
    is_group = message.chat.type in ("group", "supergroup")
    
    # Логируем для отладки
    logger.debug(f"Message from chat type: {message.chat.type}, is_group: {is_group}, is_private: {is_private}")
    logger.debug(f"Message text: {message.text[:100]}")
    logger.debug(f"Message entities: {message.entities}")
    
    # В групповых чатах отвечаем только при упоминании
    if is_group:
        if not is_bot_mentioned(message, bot_username, bot_id):
            logger.debug("Bot not mentioned, ignoring message")
            return  # Игнорируем сообщения без упоминания бота
        logger.info(f"Bot mentioned in group chat {message.chat.id}")
        # Извлекаем текст вопроса без упоминания
        text = extract_question_text(message, bot_username)
    else:
        # В личных сообщениях обрабатываем все текстовые сообщения
        text = message.text.strip()
    
    # Проверка на пустое сообщение после извлечения вопроса
    if not text:
        if is_group:
            await message.reply("Задайте вопрос после упоминания бота.")
        else:
            await message.answer("Пожалуйста, отправьте непустое сообщение.")
        return
    
    # Ограничение длины сообщения (Telegram лимит 4096 символов)
    if len(text) > 3000:
        await message.answer("Сообщение слишком длинное. Максимум 3000 символов.")
        return

    try:
        # Показываем индикатор "печатает"
        await message.bot.send_chat_action(message.chat.id, "typing")
        
        # Сохраняем сообщение пользователя
        await save_message(user_id, "user", text)

        # Берём последние 5 сообщений пользователя для контекста
        history = await get_last_messages(user_id, limit=5)

        # Формируем prompt в формате для OpenAI-совместимого API
        # Используем формат messages вместо простого текста
        messages = []
        
        # Всегда добавляем системный промпт с настройками бота
        # Это гарантирует, что бот будет помнить о создателе и правилах
        system_prompt = get_system_prompt()
        messages.append({"role": "system", "content": system_prompt})
        
        # Добавляем историю сообщений
        for msg in history:
            role = msg['role']
            content = msg['content']
            # Преобразуем role в формат OpenAI (user/assistant)
            if role == "user":
                messages.append({"role": "user", "content": content})
            elif role == "assistant":
                messages.append({"role": "assistant", "content": content})
        
        # Добавляем текущий запрос с явным указанием языка
        user_message = text
        # Если вопрос на русском, добавляем напоминание о языке ответа
        if any(ord(char) >= 0x0400 and ord(char) <= 0x04FF for char in text):
            # В тексте есть кириллица, явно просим ответ на русском
            user_message = f"{text}\n\nОтвечай на русском языке."
        
        # Проверяем, что это не дубликат последнего сообщения
        # messages всегда содержит системный промпт, поэтому проверяем последний элемент
        if messages[-1].get("role") != "user" or messages[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})
        
        # Запрос к LLM с использованием формата messages
        # Это позволяет передать системный промпт и явно указать язык ответа
        answer = await ask_llm(prompt=None, messages=messages)

        # Проверка на пустой ответ
        if not answer or len(answer.strip()) == 0:
            answer = "Извините, не получилось сгенерировать ответ. Попробуйте еще раз."

        # Сохраняем ответ
        await save_message(user_id, "assistant", answer)

        # Отправляем пользователю (Telegram лимит 4096 символов)
        if len(answer) > 4096:
            # Разбиваем длинный ответ на части
            chunks = [answer[i:i+4090] for i in range(0, len(answer), 4090)]
            for chunk in chunks:
                if is_group:
                    await message.reply(chunk)
                else:
                    await message.answer(chunk)
        else:
            if is_group:
                # В групповых чатах отвечаем как reply на сообщение
                await message.reply(answer)
            else:
                # В личных сообщениях просто отправляем ответ
                await message.answer(answer)
    
    except Exception as e:
        logger.exception(f"Ошибка при обработке сообщения от пользователя {user_id}: {e}")
        await message.answer("Произошла ошибка при обработке вашего запроса. Попробуйте позже.")
