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

    prompt_parts = [
        f"Ты полезный AI-ассистент по имени {BOT_NAME}.",
        "Отвечай на русском языке.",
        "Будь вежливым, информативным и кратким.",
        f"Твой создатель: {BOT_CREATOR}.",
        "Если тебя спрашивают о создателе, упомяни это имя.",
    ]
    
    if BOT_RULES:
        rules = [rule.strip() for rule in BOT_RULES.split(';') if rule.strip()]
        for rule in rules:
            prompt_parts.append(rule)
    
    return " ".join(prompt_parts)


def is_bot_mentioned(message: Message, bot_username: str, bot_id: int) -> bool:

    if not message.text:
        return False
    
    bot_username_lower = bot_username.lower()
    
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                mention_text = message.text[entity.offset:entity.offset + entity.length].lower()
                if mention_text.lstrip('@') == bot_username_lower:
                    return True
            elif entity.type == "text_mention":
                if entity.user and entity.user.id == bot_id:
                    return True
    
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == bot_id:
            return True
    
    if f"@{bot_username}" in message.text or f"@{bot_username_lower}" in message.text.lower():
        return True
    
    return False


def extract_question_text(message: Message, bot_username: str) -> str:

    if not message.text:
        return ""
    
    text = message.text
    bot_username_lower = bot_username.lower()
    
    if message.reply_to_message and message.reply_to_message.from_user:
        return text.strip()
    
    if message.entities:
        entities_to_remove = []
        for entity in message.entities:
            if entity.type == "mention":
                mention_text = message.text[entity.offset:entity.offset + entity.length].lower()
                if mention_text.lstrip('@') == bot_username_lower:
                    entities_to_remove.append((entity.offset, entity.offset + entity.length))
            elif entity.type == "text_mention":
                pass
        
        for start, end in sorted(entities_to_remove, reverse=True):
            text = text[:start] + text[end:]
    
    text = text.strip()
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
    if not message.text:
        return
    
    bot_info = await bot.get_me()
    bot_username = bot_info.username or ""
    bot_id = bot_info.id
    
    if not bot_username:
        logger.warning("У бота нет username, работа в группах может быть ограничена")
    
    if not message.from_user:
        logger.warning("Сообщение без from_user, пропускаем")
        return
    
    user_id = message.from_user.id
    
    is_private = message.chat.type == "private"
    is_group = message.chat.type in ("group", "supergroup")
    
    logger.debug(f"Message from chat type: {message.chat.type}, is_group: {is_group}, is_private: {is_private}")
    logger.debug(f"Message text: {message.text[:100]}")
    logger.debug(f"Message entities: {message.entities}")
    
    if is_group:
        if not is_bot_mentioned(message, bot_username, bot_id):
            logger.debug("Bot not mentioned, ignoring message")
            return
        logger.info(f"Bot mentioned in group chat {message.chat.id}")
        text = extract_question_text(message, bot_username)
    else:
        text = message.text.strip()
    
    if not text:
        if is_group:
            await message.reply("Задайте вопрос после упоминания бота.")
        else:
            await message.answer("Пожалуйста, отправьте непустое сообщение.")
        return
    
    if len(text) > 3000:
        await message.answer("Сообщение слишком длинное. Максимум 3000 символов.")
        return

    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
        
        await save_message(user_id, "user", text)

        history = await get_last_messages(user_id, limit=5)

        messages = []
        
        system_prompt = get_system_prompt()
        messages.append({"role": "system", "content": system_prompt})
        
        for msg in history:
            role = msg['role']
            content = msg['content']
            if role == "user":
                messages.append({"role": "user", "content": content})
            elif role == "assistant":
                messages.append({"role": "assistant", "content": content})
        
        user_message = text
        if any(ord(char) >= 0x0400 and ord(char) <= 0x04FF for char in text):
            user_message = f"{text}\n\nОтвечай на русском языке."
        
        if messages[-1].get("role") != "user" or messages[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})
        
        answer = await ask_llm(prompt=None, messages=messages)

        if not answer or len(answer.strip()) == 0:
            answer = "Извините, не получилось сгенерировать ответ. Попробуйте еще раз."

        await save_message(user_id, "assistant", answer)

        if len(answer) > 4096:
            chunks = [answer[i:i+4090] for i in range(0, len(answer), 4090)]
            for chunk in chunks:
                if is_group:
                    await message.reply(chunk)
                else:
                    await message.answer(chunk)
        else:
            if is_group:
                await message.reply(answer)
            else:
                await message.answer(answer)
    
    except Exception as e:
        logger.exception(f"Ошибка при обработке сообщения от пользователя {user_id}: {e}")
        await message.answer("Произошла ошибка при обработке вашего запроса. Попробуйте позже.")
