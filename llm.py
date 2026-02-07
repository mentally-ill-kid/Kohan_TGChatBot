import httpx
import logging
import re
from typing import Optional
from config import HF_API_KEY, MODEL_NAME

API_URL = "https://router.huggingface.co/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {HF_API_KEY}",
    "Content-Type": "application/json"
}

logger = logging.getLogger(__name__)


def clean_markdown(text: str) -> str:
    """
    Очищает markdown форматирование для лучшего отображения в Telegram.
    Преобразует таблицы в простой текст, убирает лишнее форматирование.
    """
    if not text:
        return text
    
    text = re.sub(r'^\*\*[^*]+\?\*\*\s*\n+', '', text, flags=re.MULTILINE)
    
    lines = text.split('\n')
    cleaned_lines = []
    in_table = False
    table_rows = []
    
    for line in lines:
        if '|' in line and line.strip().startswith('|'):
            if not in_table:
                in_table = True
                table_rows = []
            if not re.match(r'^\|[\s\-:]+\|', line.strip()):
                table_rows.append(line)
            continue
        else:
            if in_table and table_rows:
                cleaned_lines.append(_format_table_as_text(table_rows))
                table_rows = []
            in_table = False
        
        if re.match(r'^#{1,6}\s+', line):
            line = re.sub(r'^#{1,6}\s+', '', line)
            if cleaned_lines and cleaned_lines[-1].strip():
                cleaned_lines.append('')
        
        line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)
        
        line = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', line)
        
        line = re.sub(r'`([^`]+)`', r'\1', line)
        
        line = re.sub(r'^[\-\*]\s+', '• ', line)
        line = re.sub(r'^\d+\.\s+', '', line)
        
        cleaned_lines.append(line)
    
    if in_table and table_rows:
        cleaned_lines.append(_format_table_as_text(table_rows))
    
    result = '\n'.join(cleaned_lines)
    
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result.strip()


def _format_table_as_text(table_rows: list) -> str:
    """
    Преобразует markdown таблицу в простой текст.
    """
    if not table_rows:
        return ""
    
    header_line = table_rows[0]
    headers = [cell.strip() for cell in header_line.split('|') if cell.strip() and not cell.strip().startswith('-')]
    
    if len(headers) == 0:
        return ""
    
    result_lines = []
    
    for row in table_rows[1:]:
        if re.match(r'^\|[\s\-:]+\|', row.strip()):
            continue
        
        cells = [cell.strip() for cell in row.split('|') if cell.strip()]
        if len(cells) >= len(headers):
            row_items = []
            for i in range(min(len(headers), len(cells))):
                if cells[i] and headers[i]:
                    row_items.append(f"{headers[i]}: {cells[i]}")
            if row_items:
                result_lines.append(" • ".join(row_items))
    
    return "\n".join(result_lines) if result_lines else ""


async def ask_llm(prompt: Optional[str] = None, messages: Optional[list] = None) -> str:
    """
    Отправляет запрос к Hugging Face Router API для генерации текста.
    
    Args:
        prompt: Текст запроса для модели (используется только если messages не передан)
        messages: Список сообщений в формате OpenAI (предпочтительный способ)
        
    Returns:
        Сгенерированный ответ от модели или сообщение об ошибке
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if messages:
                request_data = {
                    "model": MODEL_NAME,
                    "messages": messages,
                    "max_tokens": 512,
                    "temperature": 0.7
                }
            elif prompt:
                request_data = {
                    "model": MODEL_NAME,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 512,
                    "temperature": 0.7
                }
            else:
                logger.error("Не передан ни prompt, ни messages")
                return "❌ Ошибка: не указан запрос для модели"
            
            response = await client.post(
                API_URL,
                headers=HEADERS,
                json=request_data
            )
            
            logger.info(f"HF API response status: {response.status_code}")
            logger.info(f"Request URL: {API_URL}")
            logger.info(f"Model: {MODEL_NAME}")
            logger.debug(f"Response text (first 1000 chars): {response.text[:1000] if response.text else 'Empty'}")

        if response.status_code == 404:
            error_text = response.text[:2000] if response.text else "No error message"
            logger.error(f"404 Error - Full response: {error_text}")
            logger.error(f"Request was to: {API_URL}")
            logger.error(f"Headers sent: {HEADERS}")
            try:
                error_json = response.json()
                logger.error(f"Error JSON: {error_json}")
            except:
                pass
            return f"❌ Ошибка 404: модель '{MODEL_NAME}' не найдена.\n\nПроверьте логи в консоли для деталей.\n\nВозможные причины:\n• Неправильное название модели\n• Модель недоступна через Inference API\n• Проблема с API ключом"
        
        if response.status_code == 401:
            logger.error("Неверный API ключ Hugging Face")
            return "❌ Ошибка аутентификации. Проверьте HF_API_KEY в .env файле."
        
        if response.status_code == 410:
            logger.error("Используется устаревший endpoint API")
            return "❌ Ошибка: API endpoint устарел. Обновите код."
        
        if response.status_code == 503:
            logger.warning("Модель загружается, требуется подождать")
            return "⏳ Модель загружается, попробуйте через несколько секунд..."
        
        if response.status_code != 200:
            error_text = response.text[:2000] if response.text else "No error message"
            logger.error(f"HF API error {response.status_code}")
            logger.error(f"Full error response: {error_text}")
            try:
                error_json = response.json()
                logger.error(f"Error as JSON: {error_json}")
                if isinstance(error_json, dict) and "error" in error_json:
                    return f"❌ Ошибка API ({response.status_code}): {error_json['error']}"
            except:
                pass
            return f"❌ Ошибка API ({response.status_code}): {error_text[:200]}"

        result = response.json()

        if isinstance(result, dict):
            if "error" in result:
                error_msg = result["error"]
                logger.error(f"HF API error in response: {error_msg}")
                return f"❌ Ошибка: {error_msg}"
            
            if "choices" in result and len(result["choices"]) > 0:
                message = result["choices"][0].get("message", {})
                content = message.get("content", "")
                if content:
                    return clean_markdown(content.strip())
            
            if "generated_text" in result:
                generated_text = result["generated_text"]
                if prompt and generated_text.startswith(prompt):
                    generated_text = generated_text[len(prompt):].strip()
                return clean_markdown(generated_text)
        
        if isinstance(result, list) and len(result) > 0:
            generated_text = result[0].get("generated_text", "")
            if generated_text:
                if prompt and generated_text.startswith(prompt):
                    generated_text = generated_text[len(prompt):].strip()
                return clean_markdown(generated_text)
        
        logger.warning(f"Неожиданный формат ответа: {type(result)}")
        logger.warning(f"Response structure: {result}")
        return "Извините, я сейчас не могу ответить 😅"

    except httpx.TimeoutException:
        logger.error("Таймаут при обращении к HF API")
        return "⏱️ Превышено время ожидания ответа. Попробуйте позже."
    
    except httpx.RequestError as e:
        logger.error(f"Ошибка сети при обращении к HF API: {e}")
        return "🌐 Ошибка сети. Проверьте подключение к интернету."
    
    except Exception as e:
        logger.exception(f"Неожиданная ошибка при обращении к HF API: {e}")
        return "Произошла ошибка при генерации ответа 😢"
