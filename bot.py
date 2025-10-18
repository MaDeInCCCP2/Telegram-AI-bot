"""
Main Telegram bot module with AI functionality.

Features: Multiple AI models, RAG for documents, web search, image generation,
function calling, group chat support, smart context management.

Architecture: aiogram 3.x, multiple providers with fallback, automatic history
optimization, AI agent tool system.
"""
import os
import json
import asyncio
import re
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

import gpt4freepro
import puterjs
# Поиск и инструменты временно отключены
# import document_processor
# import web_search
# import ai_tools

BASE_DIR = Path(__file__).resolve().parent
CHAT_DB_PATH = BASE_DIR / 'chat_memory.json'
USER_DB_PATH = BASE_DIR / 'user_data.json'
MODELS_JSON_PATH = BASE_DIR / 'models.json'

# Sticker pack
STICKER_PACK = "narizhomak"  # https://t.me/addstickers/narizhomak
sticker_cache = []  # Cache of sticker file_ids

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    print('[bot] TELEGRAM_BOT_TOKEN не найден в .env файле')
    exit(1)

TELEGRAM_MESSAGE_LIMIT = 4000
MAX_HISTORY_MESSAGES = 20
MAX_GROUP_HISTORY_MESSAGES = 3  # Only 3 messages for groups
MAX_HISTORY_TOKENS = 20000  # Max tokens for private chats
MAX_GROUP_HISTORY_TOKENS = 5000  # Max tokens for group chats
SUMMARIZE_THRESHOLD = 10  # Summarize if more messages
MODEL_PAGE_SIZE = 8
DEFAULT_MODEL = 'gpt-5-chat'

CODE_BLOCK_PATTERN = re.compile(r"```(\w+)?\n([\s\S]*?)```", re.MULTILINE)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# User state
user_models: dict[int, str] = {}
user_modes: dict[int, str] = {}
user_model_pages: dict[int, int] = {}
user_search_query: dict[int, str] = {}
# Technical messages for deletion in groups (chat_id -> [message_ids])
group_technical_messages: dict[int, list[int]] = {}
# User settings
user_settings: dict[int, dict] = {}  # user_id -> {temperature, max_tokens, system_prompt}

# Bot admins (replace with your Telegram ID)
ADMIN_IDS = []  # Replace with your ID

# Statistics  
bot_stats = {
    'total_messages': 0,
    'total_users': set(),
    'total_errors': 0,
    'start_time': None
}

# Model lists
RAW_MODELS: list[str] = []
AVAILABLE_MODELS: list[tuple[str, str]] = []
MODEL_PROVIDERS: dict[str, str] = {}  # model -> provider


def ensure_file(path: Path) -> None:
    """Creates file if it doesn't exist."""
    if not path.exists():
        path.touch()


def load_json(path: Path, default: Any) -> Any:
    """Loads JSON from file."""
    if not path.exists():
        return default
    try:
        with path.open('r', encoding='utf-8') as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, data: Any) -> None:
    """Saves data to JSON file."""
    with path.open('w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def normalize_model_label(model: str, provider: str = '') -> str:
    """Normalizes model name for display."""
    alias = model.split('/')[-1]
    
    # Check if it's an image model
    is_image = False
    if provider == 'gpt4freepro':
        try:
            is_image = gpt4freepro.is_image_model(model)
        except:
            pass
    
    # Choose emoji
    if is_image:
        provider_emoji = '🖼 '
    elif provider == 'gpt4freepro':
        provider_emoji = '🔷 '
    elif provider == 'puterjs':
        provider_emoji = '🟣 '
    else:
        provider_emoji = ''
    
    return f"{provider_emoji}{alias}"


def init_models() -> None:
    """Initializes model list from all providers."""
    global RAW_MODELS, AVAILABLE_MODELS, MODEL_PROVIDERS
    
    all_models = []
    
    # Load models from gpt4freepro
    gpt4free_models = gpt4freepro.list_models()
    print(f'[bot] Загружено {len(gpt4free_models)} моделей от gpt4freepro')
    for model in gpt4free_models:
        all_models.append(model)
        MODEL_PROVIDERS[model] = 'gpt4freepro'
    
    # Load models from puterjs
    puter_models = puterjs.list_models()
    print(f'[bot] Loaded {len(puter_models)} models from puterjs')
    for model in puter_models:
        # Avoid duplicates - skip if model already from gpt4freepro
        if model not in MODEL_PROVIDERS:
            all_models.append(model)
            MODEL_PROVIDERS[model] = 'puterjs'
        else:
            # gpt4freepro has priority if model exists in both
            print(f'[bot] Model {model} available in both providers, using gpt4freepro')
    
    # Sort and create labeled list
    all_models.sort()
    AVAILABLE_MODELS = [
        (normalize_model_label(model, MODEL_PROVIDERS.get(model, '')), model)
        for model in all_models
    ]
    
    print(f'[bot] Всего доступно {len(AVAILABLE_MODELS)} моделей')
    
    if not all_models:
        print('[bot] Не удалось загрузить модели, использую дефолтные')
        RAW_MODELS = [DEFAULT_MODEL, 'gpt-4o-mini', 'claude-3-opus']
        MODEL_PROVIDERS[DEFAULT_MODEL] = 'gpt4freepro'
    else:
        RAW_MODELS = all_models


init_models()


def load_db() -> dict[str, list[dict[str, str]]]:
    """Loads chat history database."""
    if not CHAT_DB_PATH.exists():
        return {}
    try:
        with CHAT_DB_PATH.open('r', encoding='utf-8') as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError('Некорректный формат базы чата')
        return data
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f'[bot] Не удалось прочитать базу чата: {error}')
        return {}


def save_db(data: dict[str, list[dict[str, str]]]) -> None:
    """Saves chat history database."""
    with CHAT_DB_PATH.open('w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def save_message(chat_id: int, role: str, content: str, is_group: bool = False) -> None:
    """Saves message to chat history."""
    db = load_db()
    history = db.setdefault(str(chat_id), [])
    history.append({"role": role, "content": content})
    
    # Groups: max 3 messages, private: 20
    max_messages = MAX_GROUP_HISTORY_MESSAGES if is_group else MAX_HISTORY_MESSAGES
    if len(history) > max_messages:
        del history[:-max_messages]
    save_db(db)


def estimate_tokens(text: str) -> int:
    """Estimates token count (heuristic)."""
    # Simple heuristic: ~2.5 chars = 1 token
    return len(text) // 2


def compress_message(content: str) -> str:
    """Compresses message: removes code blocks and extras."""
    # Replace code blocks with short labels
    content = re.sub(r'```[\w]*\n[\s\S]*?```', '[code]', content)
    
    # Replace long whitespace sequences
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r' {3,}', ' ', content)
    
    return content.strip()


def is_technical_message(content: str) -> bool:
    """Checks if message is technical (can be removed from history)."""
    technical_phrases = [
        'история очищена',
        'модель переключена',
        'токен добавлен',
        'выберите модель',
        'команды:',
        'профиль',
        'статус токенов'
    ]
    content_lower = content.lower()
    return any(phrase in content_lower for phrase in technical_phrases)


def summarize_old_messages(history: list[dict[str, str]], keep_last: int = 10) -> list[dict[str, str]]:
    """Summarizes old messages if too many."""
    if len(history) <= SUMMARIZE_THRESHOLD:
        return history
    
    # Split into old and recent
    old_messages = history[:-keep_last]
    recent_messages = history[-keep_last:]
    
    # Create brief summary of old messages
    summary_parts = []
    for msg in old_messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')[:100]  # First 100 chars
        summary_parts.append(f"{role}: {content}...")
    
    summary = "Previously discussed:\n" + "\n".join(summary_parts[:5])  # Max 5 old messages
    
    # Add summary as system message
    summarized_history = [{"role": "system", "content": summary}]
    summarized_history.extend(recent_messages)
    
    print(f'[bot] Суммаризация: {len(history)} → {len(summarized_history)} сообщений')
    
    return summarized_history


def trim_history_by_tokens(history: list[dict[str, str]], max_tokens: int) -> list[dict[str, str]]:
    """Trims history by token limit, keeping recent messages."""
    if not history:
        return history
    
    total_tokens = 0
    trimmed_history = []
    
    # Iterate from end (newest messages)
    for message in reversed(history):
        message_tokens = estimate_tokens(message.get('content', ''))
        
        if total_tokens + message_tokens > max_tokens:
            break
        
        total_tokens += message_tokens
        trimmed_history.insert(0, message)
    
    return trimmed_history


def load_history(chat_id: int, is_group: bool = False) -> list[dict[str, str]]:
    """Loads chat history with optimization and token limit."""
    db = load_db()
    history = db.get(str(chat_id), [])
    
    if not history:
        return history
    
    # Step 1: Remove technical messages
    history = [msg for msg in history if not is_technical_message(msg.get('content', ''))]
    
    # Step 2: Compress messages (remove code blocks)
    for msg in history:
        msg['content'] = compress_message(msg.get('content', ''))
    
    # Step 3: Trim by message count
    limit = MAX_GROUP_HISTORY_MESSAGES if is_group else MAX_HISTORY_MESSAGES
    history = history[-limit:]
    
    # Step 4: Summarize old messages (private chats only)
    if not is_group and len(history) > SUMMARIZE_THRESHOLD:
        history = summarize_old_messages(history, keep_last=10)
    
    # Step 5: Trim by tokens
    max_tokens = MAX_GROUP_HISTORY_TOKENS if is_group else MAX_HISTORY_TOKENS
    history_before = len(history)
    history = trim_history_by_tokens(history, max_tokens)
    
    # Log if trimmed
    if history_before > len(history):
        total_tokens = sum(estimate_tokens(msg.get('content', '')) for msg in history)
        print(f'[bot] История обрезана: {history_before} → {len(history)} сообщений (~{total_tokens} токенов)')
    
    return history


def clear_history(chat_id: int) -> None:
    """Clears chat history."""
    db = load_db()
    if str(chat_id) in db:
        del db[str(chat_id)]
        save_db(db)


async def track_technical_message(chat_id: int, message_id: int, is_group: bool) -> None:
    """Tracks technical message for later deletion in groups."""
    if is_group:
        if chat_id not in group_technical_messages:
            group_technical_messages[chat_id] = []
        group_technical_messages[chat_id].append(message_id)
        # Limit to last 20 messages
        if len(group_technical_messages[chat_id]) > 20:
            group_technical_messages[chat_id] = group_technical_messages[chat_id][-20:]


async def delete_technical_messages(chat_id: int, is_group: bool) -> None:
    """Deletes all technical messages in group."""
    if not is_group or chat_id not in group_technical_messages:
        return
    
    message_ids = group_technical_messages[chat_id]
    if not message_ids:
        return
    
    # Delete messages
    for msg_id in message_ids:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception as e:
            print(f'[bot] Не удалось удалить сообщение {msg_id}: {e}')
    
    # Clear list
    group_technical_messages[chat_id] = []
    print(f'[bot] Удалено {len(message_ids)} технических сообщений из группы {chat_id}')


async def load_stickers() -> None:
    """Loads stickers from sticker pack."""
    global sticker_cache
    try:
        sticker_set = await bot.get_sticker_set(STICKER_PACK)
        sticker_cache = [sticker.file_id for sticker in sticker_set.stickers]
        print(f'[bot] Загружено {len(sticker_cache)} стикеров из {STICKER_PACK}')
    except Exception as e:
        print(f'[bot] Ошибка загрузки стикеров: {e}')
        sticker_cache = []


async def send_random_sticker(chat_id: int) -> bool:
    """Sends random sticker from pack."""
    if not sticker_cache:
        await load_stickers()
    
    if not sticker_cache:
        return False
    
    import random
    sticker_id = random.choice(sticker_cache)
    try:
        await bot.send_sticker(chat_id, sticker_id)
        return True
    except Exception as e:
        print(f'[bot] Ошибка отправки стикера: {e}')
        return False


def is_admin(user_id: int) -> bool:
    """Checks if user is admin."""
    return user_id in ADMIN_IDS


def update_stats(user_id: int, is_error: bool = False):
    """Updates bot statistics."""
    bot_stats['total_messages'] += 1
    bot_stats['total_users'].add(user_id)
    if is_error:
        bot_stats['total_errors'] += 1


def get_user_settings(user_id: int) -> dict:
    """Gets user settings."""
    if user_id not in user_settings:
        user_settings[user_id] = {
            'temperature': 0.7,
            'max_tokens': 2000,
            'system_prompt': None
        }
    return user_settings[user_id]


def set_user_setting(user_id: int, key: str, value):
    """Sets user setting."""
    settings = get_user_settings(user_id)
    settings[key] = value


async def generate_with_tools(user_id: int, history: list, text: str, model: str, message: types.Message = None) -> str:
    """
    Generates response with tool usage capability.
    AI decides when to use tools.
    """
    # Check if model supports tools
    if not ai_tools.should_use_tools(model):
        print(f'[bot] ⚠️ Модель {model} не поддерживает tools, используется обычная генерация')
        
        # If user asks for search but model doesn't support tools, notify them
        text_lower = text.lower()
        is_search_request = any(keyword in text_lower for keyword in [
            'найди', 'найти', 'поищи', 'поиск', 'погугли', 'search'
        ])
        
        if is_search_request and message:
            await message.answer(
                '⚠️ Выбранная модель не поддерживает поиск в интернете.\n\n'
                '💡 Для использования поиска переключитесь на модель с поддержкой инструментов через /model:\n'
                '• gpt-4o\n'
                '• gpt-4o-mini\n'
                '• claude-3.5-sonnet'
            )
        
        # Regular generation without tools
        if MODEL_PROVIDERS.get(model) == 'puterjs':
            return puterjs.generate_text(history, text, model)
        else:
            return gpt4freepro.generate_text(history, text, model)
    
    print(f'[bot] ✅ Модель {model} поддерживает tools, генерация с инструментами...')
    
    # Detect if user explicitly asks for search
    text_lower = text.lower()
    force_search = any(keyword in text_lower for keyword in [
        'найди', 'найти', 'поищи', 'поиск', 'погугли', 'search', 'find',
        'что нового', 'актуальн', 'последн', 'новости'
    ])
    
    if force_search:
        print(f'[bot] 🔍 Обнаружен запрос на поиск - форсируем использование search_web')
    
    # Generation with tools
    import requests
    url = f"{gpt4freepro.API_BASE_URL.rstrip('/')}/chat/completions"
    headers = {'Content-Type': 'application/json'}
    
    messages = []
    for item in history:
        messages.append({"role": item["role"], "content": item["content"]})
    
    # Add general system prompt about tools
    system_parts = []
    system_parts.append("У тебя есть доступ к инструментам. ОБЯЗАТЕЛЬНО используй их когда:")
    system_parts.append("- search_web: Когда пользователь просит найти/поискать что-то в интернете, узнать актуальную информацию")
    system_parts.append("- get_news: Когда просят новости или текущие события")
    system_parts.append("- crawl_website: Когда нужно прочитать конкретный сайт по URL")
    
    # Document search temporarily disabled
    # docs = document_processor.get_user_documents(user_id)
    # if docs:
    #     doc_names = [d['filename'] for d in docs]
    #     system_parts.append(f"- search_in_documents: У пользователя {len(docs)} документ(ов): {', '.join(doc_names)}. Используй когда спрашивают про работу, лабы, задания, документы, 'над чем поработать', 'что там'")
    
    system_msg = "\n".join(system_parts)
    messages.insert(0, {"role": "system", "content": system_msg})
    
    messages.append({"role": "user", "content": text})
    
    # If user explicitly asks for search, force tool usage
    tool_choice = 'auto'
    if force_search:
        tool_choice = {
            "type": "function",
            "function": {"name": "search_web"}
        }
        print(f'[bot] 🎯 Форсируем использование search_web вместо auto')
    
    payload = {
        'model': model,
        'messages': messages,
        'tools': ai_tools.TOOLS,
        'tool_choice': tool_choice,
        'stream': False,
    }
    
    # First request
    print(f'[bot] 📤 Отправка запроса с {len(ai_tools.TOOLS)} инструментами...')
    response = requests.post(url, headers=headers, json=payload, timeout=90)
    response.raise_for_status()
    data = response.json()
    
    message = data['choices'][0]['message']
    print(f'[bot] 📥 Получен ответ от AI: tool_calls={bool(message.get("tool_calls"))}')
    
    # Check if AI wants to use tools
    if message.get('tool_calls'):
        print(f'[bot] AI хочет использовать инструменты: {len(message["tool_calls"])}')
        
        # Add AI response with tool_calls
        messages.append(message)
        
        # Execute each tool
        for tool_call in message['tool_calls']:
            tool_name = tool_call['function']['name']
            arguments = json.loads(tool_call['function']['arguments'])
            
            # Add user_id if needed
            if tool_name == 'search_in_documents':
                arguments['user_id'] = user_id
            
            print(f'[bot] Выполняю инструмент: {tool_name}({arguments})')
            
            # Execute tool
            tool_result = ai_tools.execute_tool(tool_name, arguments)
            
            # Add result
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call['id'],
                "content": tool_result
            })
        
        # Second request - AI generates final answer with tool results
        payload['messages'] = messages
        payload.pop('tools', None)  # Убираем tools для финального ответа
        payload.pop('tool_choice', None)
        
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        
        content = data['choices'][0]['message']['content']
        
        # Убираем рекламу
        content = re.sub(r'\n*---\n*\*\*Support Pollinations\.AI:\*\*.*', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'\n*\*\*Support Pollinations\.AI:\*\*.*', '', content, flags=re.DOTALL | re.IGNORECASE)
        
        return content.strip()
    
    else:
        # AI didn't use tools
        print(f'[bot] ⚠️ AI не использовал инструменты')
        
        # If user explicitly asked for search but AI didn't use tools, force it
        if force_search:
            print(f'[bot] 🔧 Пользователь просил поиск, но AI не использовал tools - выполняю поиск напрямую')
            
            # Notify user that search is being performed
            if message:
                await message.answer('🔍 Выполняю поиск в интернете...')
            
            # Extract search query from user message
            import ai_tools
            print(f'[bot] 🔎 Выполняю search_web с запросом: {text[:100]}')
            search_result = ai_tools.execute_tool('search_web', {'query': text})
            print(f'[bot] ✅ Поиск выполнен, результатов: {len(search_result)} символов')
            
            # Ask AI to summarize the search results
            summary_messages = messages.copy()
            summary_messages.append({
                "role": "assistant",
                "content": f"Я выполнил поиск и нашел следующую информацию:\n\n{search_result}"
            })
            summary_messages.append({
                "role": "user", 
                "content": "Пожалуйста, обобщи эту информацию и ответь на мой изначальный вопрос"
            })
            
            summary_payload = {
                'model': model,
                'messages': summary_messages,
                'stream': False,
            }
            
            print(f'[bot] 📝 Запрашиваю у AI обобщение результатов поиска...')
            response = requests.post(url, headers=headers, json=summary_payload, timeout=90)
            response.raise_for_status()
            data = response.json()
            content = data['choices'][0]['message']['content']
            print(f'[bot] ✅ Получен обобщенный ответ от AI')
        else:
            # Just return AI response
            content = message['content']
        
        # Remove ads
        content = re.sub(r'\n*---\n*\*\*Support Pollinations\.AI:\*\*.*', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'\n*\*\*Support Pollinations\.AI:\*\*.*', '', content, flags=re.DOTALL | re.IGNORECASE)
        
        return content.strip()


def get_user_model(user_id: int) -> str:
    """Returns user's selected model."""
    return user_models.get(user_id, DEFAULT_MODEL)


def get_user_mode(user_id: int) -> str:
    """Returns user mode: 'text' or 'image'."""
    return user_modes.get(user_id, 'text')


def filter_models_by_search(query: str) -> list[tuple[str, str]]:
    """Filters models by search query."""
    if not query:
        return AVAILABLE_MODELS
    
    query_lower = query.lower()
    filtered = [
        (label, value) for label, value in AVAILABLE_MODELS
        if query_lower in value.lower() or query_lower in label.lower()
    ]
    return filtered


def build_model_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Creates model selection keyboard."""
    current = get_user_model(user_id)
    search_query = user_search_query.get(user_id, '')
    
    # Показываем все модели с фильтрацией по поиску
    models_to_show = filter_models_by_search(search_query)
    
    page = user_model_pages.get(user_id, 0)
    start = page * MODEL_PAGE_SIZE
    end = start + MODEL_PAGE_SIZE
    sliced = models_to_show[start:end]

    keyboard: list[list[InlineKeyboardButton]] = []
    
    # Кнопка поиска
    search_text = f"🔍 Поиск: {search_query}" if search_query else "🔍 Поиск моделей"
    keyboard.append([
        InlineKeyboardButton(text=search_text, callback_data="model_search")
    ])
    
    # Если есть поиск, показываем кнопку очистки
    if search_query:
        keyboard.append([
            InlineKeyboardButton(text="❌ Очистить поиск", callback_data="model_search_clear")
        ])
    
    # Список моделей
    for label, value in sliced:
        suffix = " ✅" if value == current else ""
        keyboard.append([
            InlineKeyboardButton(text=f"{label}{suffix}", callback_data=f"model:{value}")
        ])

    # Навигация
    nav_row: list[InlineKeyboardButton] = []
    if start > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data="model_page:prev"))
    
    # Показываем счётчик страниц
    total_pages = (len(models_to_show) + MODEL_PAGE_SIZE - 1) // MODEL_PAGE_SIZE
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(
            text=f"📄 {page + 1}/{total_pages}", 
            callback_data="model_page:info"
        ))
    
    if end < len(models_to_show):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data="model_page:next"))
    
    if nav_row:
        keyboard.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_main_keyboard() -> ReplyKeyboardMarkup:
    """Creates bot's main keyboard."""
    keyboard = [
        [KeyboardButton(text="💬 Текст"), KeyboardButton(text="🖼 Изображение")],
        [KeyboardButton(text="🗑 Очистить историю"), KeyboardButton(text="⚙️ Модели")],
        [KeyboardButton(text="👤 Профиль")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def split_reply(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Splits long text into parts."""
    chunks: list[str] = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_pos = remaining.rfind('\n', 0, limit)
        if split_pos == -1:
            split_pos = remaining.rfind(' ', 0, limit)
        if split_pos == -1 or split_pos < limit // 2:
            split_pos = limit
        chunk = remaining[:split_pos].rstrip()
        if not chunk:
            chunk = remaining[:limit]
            split_pos = limit
        chunks.append(chunk)
        remaining = remaining[split_pos:].lstrip()
    return chunks


def prepare_reply_messages(text: str) -> list[dict[str, Any]]:
    """Prepares messages considering code blocks."""
    messages: list[dict[str, Any]] = []

    def add_plain(plain_text: str) -> None:
        for chunk in split_reply(plain_text):
            if chunk:
                messages.append({"text": chunk, "parse_mode": None})

    cursor = 0
    for match in CODE_BLOCK_PATTERN.finditer(text):
        start, end = match.span()
        if start > cursor:
            add_plain(text[cursor:start].strip())
        language = match.group(1) or ""
        code_body = match.group(2).rstrip()
        code_message = f"```{language}\n{code_body}\n```"
        for chunk in split_reply(code_message):
            messages.append({"text": chunk, "parse_mode": "Markdown"})
        cursor = end

    if cursor < len(text):
        add_plain(text[cursor:].strip())

    if not messages:
        add_plain(text)

    return messages


async def send_reply(message: types.Message, text: str) -> None:
    """Sends reply to user."""
    # Проверяем наличие маркера стикера
    if '[STICKER]' in text:
        # Отправляем стикер
        await send_random_sticker(message.chat.id)
        # Убираем маркер из текста
        text = text.replace('[STICKER]', '').strip()
    
    # Если после удаления маркера остался текст - отправляем его
    if text:
        for payload in prepare_reply_messages(text):
            await message.answer(payload["text"], parse_mode=payload["parse_mode"])


@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Обработчик команды /start."""
    await message.answer(
        'Привествую! Я бот, c большим количеством ИИ и все бесплатно :) хочу рассказать кое-что: Модели с 🔷 - самые стабильные, 🟣 - побольшей части резерв, если готов - Выберите режим работы:',
        reply_markup=build_main_keyboard()
    )


@dp.message(Command("models"))
async def models_command(message: types.Message):
    """Обработчик команды /models."""
    user_model_pages[message.from_user.id] = 0
    await message.answer(
        'Выберите модель для ответов:',
        reply_markup=build_model_keyboard(message.from_user.id)
    )


@dp.message(F.text == "⚙️ Модели")
async def models_button(message: types.Message):
    """Обработчик кнопки выбора моделей."""
    user_model_pages[message.from_user.id] = 0
    await message.answer(
        'Выберите модель для ответов:',
        reply_markup=build_model_keyboard(message.from_user.id)
    )


@dp.message(F.text == "💬 Текст")
async def text_mode_button(message: types.Message):
    """Показывает текстовые модели."""
    user_id = message.from_user.id
    current_model = get_user_model(user_id)
    
    # Если текущая модель для изображений, переключаем на текстовую
    if gpt4freepro.is_image_model(current_model):
        user_models[user_id] = DEFAULT_MODEL
        await message.answer(
            f'💬 Переключено на текстовую модель {DEFAULT_MODEL}.\n'
            f'Выберите другую модель через ⚙️ Модели или отправьте сообщение.'
        )
    else:
        await message.answer(
            f'💬 Текущая модель: {current_model}\n'
            f'Выберите другую модель через ⚙️ Модели или отправьте сообщение.'
        )


@dp.message(F.text == "🖼 Изображение")
async def image_mode_button(message: types.Message):
    """Показывает модели для изображений."""
    user_id = message.from_user.id
    
    if gpt4freepro.supports_images():
        image_models_count = len(gpt4freepro.list_image_models())
        current_model = get_user_model(user_id)
        
        # Если текущая модель не для изображений, переключаем на дефолтную для изображений
        if not gpt4freepro.is_image_model(current_model):
            default_img_model = gpt4freepro.get_default_image_model()
            user_models[user_id] = default_img_model
            await message.answer(
                f'🖼 Переключено на модель для изображений: {default_img_model}\n'
                f'Доступно {image_models_count} моделей.\n\n'
                f'Отправьте описание изображения или выберите модель через ⚙️ Модели.'
            )
        else:
            await message.answer(
                f'🖼 Текущая модель для изображений: {current_model}\n'
                f'Доступно {image_models_count} моделей.\n\n'
                f'Отправьте описание изображения или выберите модель через ⚙️ Модели.'
            )
    else:
        await message.answer('Генерация изображений временно недоступна.')


@dp.message(F.text == "🗑 Очистить историю")
async def clear_history_button(message: types.Message):
    """Обработчик очистки истории."""
    clear_history(message.chat.id)
    await message.answer('История чата очищена! 🗑')


async def show_profile(message: types.Message):
    """Показывает профиль пользователя."""
    user_id = message.from_user.id
    username = message.from_user.username or "Не указан"
    first_name = message.from_user.first_name or "Пользователь"
    
    # Получаем статистику
    chat_id = message.chat.id
    history = load_history(chat_id)
    message_count = len(history)
    
    # Получаем текущую модель
    current_model = user_models.get(user_id, DEFAULT_MODEL)
    provider = MODEL_PROVIDERS.get(current_model, 'неизвестно')
    provider_emoji = "🔷" if provider == "gpt4freepro" else "🟣"
    
    # Статистика токенов
    try:
        import puterjs
        working_tokens = puterjs.get_working_auth_tokens()
        all_tokens_data = puterjs.load_auth_tokens()
        all_tokens = all_tokens_data.get("auth", {}).get("tokens", [])
        token_status = f"{len(working_tokens)}/{len(all_tokens)}"
    except:
        token_status = "0/0"
    
    # Создаём клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Пожертвовать токены", callback_data="donate_tokens")],
        [InlineKeyboardButton(text="📊 Статус токенов", callback_data="show_tokens")],
        [InlineKeyboardButton(text="💬 Техподдержка", url="https://t.me/Madeincccp2")]
    ])
    
    profile_text = (
        f"👤 <b>Профиль</b>\n\n"
        f"👨‍💻 Имя: {first_name}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📱 Username: @{username}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"💬 Сообщений в истории: {message_count}\n"
        f"🤖 Текущая модель: {provider_emoji} {current_model}\n"
        f"🔑 Токенов PuterJS: {token_status}\n\n"
        f"💡 <b>Совет:</b> Пожертвуйте токены для доступа к моделям 🟣 PuterJS!"
    )
    
    return await message.answer(profile_text, parse_mode="HTML", reply_markup=keyboard)


@dp.message(Command('profile'))
async def cmd_profile(message: types.Message):
    """Команда /profile."""
    is_group = message.chat.type in ['group', 'supergroup']
    sent_msg = await show_profile(message)
    if sent_msg and is_group:
        await track_technical_message(message.chat.id, sent_msg.message_id, is_group)


@dp.message(F.text == "👤 Профиль")
async def btn_profile(message: types.Message):
    """Обработчик кнопки Профиль."""
    await show_profile(message)


@dp.callback_query(F.data == 'model_search')
async def handle_model_search(callback: types.CallbackQuery):
    """Обработчик кнопки поиска моделей."""
    await callback.answer('Отправьте название модели для поиска (например: gpt-4, claude, deepseek)')
    user_search_query[callback.from_user.id] = 'waiting'


@dp.callback_query(F.data == 'model_search_clear')
async def handle_model_search_clear(callback: types.CallbackQuery):
    """Обработчик очистки поиска."""
    user_id = callback.from_user.id
    user_search_query[user_id] = ''
    user_model_pages[user_id] = 0
    await callback.answer('Поиск очищен')
    await callback.message.edit_reply_markup(reply_markup=build_model_keyboard(user_id))


@dp.callback_query(F.data.startswith('model_page:'))
async def handle_model_page(callback: types.CallbackQuery):
    """Обработчик пагинации моделей."""
    user_id = callback.from_user.id
    
    if callback.data == 'model_page:next':
        user_model_pages[user_id] = user_model_pages.get(user_id, 0) + 1
    elif callback.data == 'model_page:prev':
        user_model_pages[user_id] = max(user_model_pages.get(user_id, 0) - 1, 0)
    elif callback.data == 'model_page:info':
        search_query = user_search_query.get(user_id, '')
        models_count = len(filter_models_by_search(search_query))
        await callback.answer(f'Всего моделей: {models_count}', show_alert=True)
        return
    
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=build_model_keyboard(user_id))


@dp.callback_query(F.data.startswith('model:'))
async def handle_model_select(callback: types.CallbackQuery):
    """Обработчик выбора модели."""
    user_id = callback.from_user.id
    model = callback.data.split(':', 1)[1]
    
    for _, value in AVAILABLE_MODELS:
        if value == model:
            user_models[user_id] = model
            await callback.answer(f'Модель переключена на {model}')
            try:
                await callback.message.edit_reply_markup(reply_markup=build_model_keyboard(user_id))
            except Exception:
                await callback.message.answer(
                    'Выберите модель для ответов:',
                    reply_markup=build_model_keyboard(user_id)
                )
            return
    
    await callback.answer('Неизвестная модель', show_alert=True)


@dp.message(F.sticker)
async def handle_sticker(message: types.Message):
    """Обработчик стикеров - AI описывает стикер."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    is_group = message.chat.type in ['group', 'supergroup']
    
    # В группах проверяем упоминание или ответ
    if is_group:
        bot_info = await bot.me()
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == bot_info.id
        
        if not is_reply_to_bot:
            return
    
    print(f'[bot] Получен стикер от {user_id}')
    await bot.send_chat_action(chat_id, 'typing')
    
    try:
        # Получаем информацию о стикере
        sticker_emoji = message.sticker.emoji or "неизвестный эмодзи"
        is_animated = message.sticker.is_animated
        is_video = message.sticker.is_video
        
        # Для обычных статичных стикеров используем текстовое описание
        if not is_animated and not is_video:
            # Простое описание по эмодзи без Vision (т.к. API может не поддерживать)
            reply = f"Вижу стикер {sticker_emoji}! Прикольный!"
        
        elif is_animated:
            reply = f"Это анимированный стикер с эмодзи {sticker_emoji}! Классная анимация 🔥"
        
        elif is_video:
            reply = f"Это видео-стикер с эмодзи {sticker_emoji}! Круто смотрится 🎬"
        
        else:
            reply = f"Прикольный стикер {sticker_emoji}!"
        
        update_stats(user_id, is_error=False)
        await message.answer(reply)
        
    except Exception as e:
        print(f'[bot] Ошибка обработки стикера: {e}')
        await message.answer('Вижу стикер! 👀')


@dp.message(F.animation)
async def handle_animation(message: types.Message):
    """Обработчик GIF-анимаций."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    is_group = message.chat.type in ['group', 'supergroup']
    
    # В группах проверяем упоминание
    if is_group:
        caption = message.caption or ""
        bot_info = await bot.me()
        bot_username = bot_info.username
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == bot_info.id
        is_mention = f'@{bot_username}' in caption
        
        if not (is_reply_to_bot or is_mention):
            return
    
    print(f'[bot] Получена GIF-анимация от {user_id}')
    await bot.send_chat_action(chat_id, 'typing')
    
    try:
        # Простое описание GIF
        caption_text = message.caption or ""
        if caption_text:
            reply = f"Прикольная GIF! {caption_text}"
        else:
            reply = f"Классная анимация! 🎬 (размер: {message.animation.width}x{message.animation.height})"
        
        update_stats(user_id, is_error=False)
        await message.answer(reply)
        
    except Exception as e:
        print(f'[bot] Ошибка обработки GIF: {e}')
        await message.answer('Прикольная гифка! 🎬')
        update_stats(user_id, is_error=True)


# Обработка документов временно отключена
# @dp.message(F.document)
# async def handle_document(message: types.Message):
#     """Обработчик документов для RAG."""
#     pass


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    """Обработчик фотографий с Vision."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    is_group = message.chat.type in ['group', 'supergroup']
    
    # В группах проверяем упоминание
    if is_group:
        caption = message.caption or ""
        bot_info = await bot.me()
        bot_username = bot_info.username
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == bot_info.id
        is_mention = f'@{bot_username}' in caption
        
        if not (is_reply_to_bot or is_mention):
            return
    
    print(f'[bot] Получено изображение от {user_id}')
    await bot.send_chat_action(chat_id, 'typing')
    
    try:
        # Формируем ответ
        caption_text = message.caption or ""
        
        if caption_text:
            reply = f"Вижу фото! {caption_text} 📷\n\n(Примечание: Vision API временно недоступен, но я вижу что вы отправили изображение)"
        else:
            reply = "Вижу фотографию! 📷\n\n(Примечание: Vision API временно недоступен для анализа изображений)"
        
        # Сохраняем в историю
        save_message(chat_id, 'user', f'[Изображение] {caption_text if caption_text else "без подписи"}', is_group=is_group)
        save_message(chat_id, 'assistant', reply, is_group=is_group)
        
        update_stats(user_id, is_error=False)
        
        await message.answer(reply)
        
        # Удаляем технические сообщения в группах
        await delete_technical_messages(chat_id, is_group)
        
    except Exception as e:
        print(f'[bot] Ошибка обработки изображения: {e}')
        await message.answer(f'❌ Ошибка анализа изображения: {str(e)[:100]}')
        update_stats(user_id, is_error=True)


@dp.message(F.text & ~F.text.startswith('/'))
async def handle_message(message: types.Message):
    """Обработчик текстовых сообщений."""
    if not message.text:
        return
    
    text = message.text
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    print(f'[bot] Получено сообщение: chat_type={message.chat.type}, user={user_id}, text={text[:50]}...')
    
    # Проверка на групповой чат
    is_group = message.chat.type in ['group', 'supergroup']
    
    if is_group:
        # В группах работаем только по упоминанию или ответу на сообщение бота
        bot_info = await bot.me()
        bot_username = bot_info.username
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == bot_info.id
        is_mention = f'@{bot_username}' in text
        
        if not (is_reply_to_bot or is_mention):
            print(f'[bot] Группа: игнорирую сообщение без упоминания от {user_id}')
            return  # Игнорируем сообщения без упоминания
        
        print(f'[bot] Группа: обрабатываю сообщение (mention={is_mention}, reply={is_reply_to_bot})')
        
        # Убираем упоминание из текста
        if is_mention:
            text = text.replace(f'@{bot_username}', '').strip()
    
    # Проверяем, ждём ли мы поисковый запрос
    if user_search_query.get(user_id) == 'waiting':
        user_search_query[user_id] = text
        user_model_pages[user_id] = 0
        filtered = filter_models_by_search(text)
        await message.answer(
            f'Найдено моделей: {len(filtered)}\nВыберите модель:',
            reply_markup=build_model_keyboard(user_id)
        )
        return
    
    model = get_user_model(user_id)
    provider = MODEL_PROVIDERS.get(model, 'gpt4freepro')
    
    # Автоопределение режима по модели
    if gpt4freepro.is_image_model(model):
        mode = 'image'
        user_modes[user_id] = 'image'
    else:
        mode = 'text'
        user_modes[user_id] = 'text'
    
    print(f'[bot] Получено сообщение от {user_id}: {text[:50]}...')
    print(f'[bot] Модель: {model}, Провайдер: {provider}, Режим: {mode} (авто)')
    
    await bot.send_chat_action(chat_id, 'typing')
    
    # Режим генерации изображений
    if mode == 'image':
        try:
            # Используем выбранную модель если она для изображений, иначе дефолтную
            if gpt4freepro.is_image_model(model):
                image_model = model
                print(f'[bot] Используется выбранная модель для изображений: {image_model}')
            else:
                image_model = gpt4freepro.get_default_image_model()
                print(f'[bot] Используется дефолтная модель для изображений: {image_model}')
            
            print(f'[bot] Генерация изображения через gpt4freepro (модель: {image_model})...')
            
            # Запускаем в отдельном потоке чтобы не блокировать event loop
            try:
                image_url = await asyncio.to_thread(gpt4freepro.generate_image, text, model=image_model)
            except (gpt4freepro.ProviderUnavailable, RuntimeError) as e:
                # Если модель не работает, пробуем dall-e-3
                if image_model != 'dall-e-3':
                    print(f'[bot] Модель {image_model} не работает, пробую dall-e-3: {e}')
                    image_url = await asyncio.to_thread(gpt4freepro.generate_image, text, model='dall-e-3')
                    image_model = 'dall-e-3'
                else:
                    raise
            
            await message.answer_photo(image_url, caption=f'Изображение: {text[:100]}\nМодель: {image_model}')
            print(f'[bot] Изображение отправлено')
            return
        except gpt4freepro.ProviderUnavailable as e:
            print(f'[bot] gpt4freepro недоступен для изображений: {e}')
            await message.answer(
                '⚠️ Генерация изображений временно недоступна\n\n'
                f'Причина: {str(e)[:100]}\n\n'
                '💡 Попробуйте:\n'
                '• Переключиться на текстовый режим (💬 Текст)\n'
                '• Попробовать позже\n'
                '• Обратиться в техподдержку: @Madeincccp2'
            )
            return
        except Exception as e:
            print(f'[bot] Ошибка генерации изображения: {e}')
            await message.answer(
                '⚠️ Ошибка при генерации изображения.\n'
                'Попробуйте другой запрос или обратитесь в тех поддержку.'
            )
            return
    
    # Режим генерации текста
    history = load_history(chat_id, is_group=is_group)
    
    # Определяем порядок провайдеров на основе выбранной модели
    # 🔷 (gpt4freepro) - только gpt4freepro
    # 🟣 (puterjs) - только puterjs
    if provider == 'puterjs':
        # Модель от puterjs - используем только puterjs
        providers_to_try = [
            ('puterjs', puterjs)
        ]
    else:
        # Модель от gpt4freepro - используем только gpt4freepro
        providers_to_try = [
            ('gpt4freepro', gpt4freepro)
        ]
    
    # Простая генерация текста (поиск временно отключен)
    try:
        print(f'[bot] Генерация текста (модель: {model})...')
        
        if provider == 'puterjs':
            reply = await asyncio.to_thread(puterjs.generate_text, history, text, model)
        else:
            reply = await asyncio.to_thread(gpt4freepro.generate_text, history, text, model)
        
        print(f'[bot] Ответ получен')
        
        save_message(chat_id, 'user', text, is_group=is_group)
        save_message(chat_id, 'assistant', reply, is_group=is_group)
        
        # Обновляем статистику
        update_stats(user_id, is_error=False)
        
        await send_reply(message, reply)
        
        # Удаляем технические сообщения в группах после ответа
        await delete_technical_messages(chat_id, is_group)
        return
    except Exception as e:
        print(f'[bot] Ошибка генерации: {e}')
        update_stats(user_id, is_error=True)
    
    # Провайдер недоступен
    if provider == 'puterjs':
        await message.answer(
            f'⚠️ Модель {model} (🟣 PuterJS) временно недоступна.\n'
            f'Попробуйте:\n'
            f'• Выбрать другую модель 🟣 PuterJS через ⚙️ Модели\n'
            f'• Использовать модели 🔷 gpt4freepro (более стабильные)'
        )
    else:
        await message.answer(
            f'⚠️ Модель {model} (🔷 gpt4freepro) временно недоступна.\n'
            f'Попробуйте:\n'
            f'• Выбрать другую модель 🔷 gpt4freepro через ⚙️ Модели\n'
            f'• Использовать модели 🟣 PuterJS'
        )


@dp.callback_query(F.data == "donate_tokens")
async def callback_donate_tokens(callback: types.CallbackQuery):
    """Обработчик кнопки пожертвования токенов."""
    await callback.answer()
    await cmd_auth(callback.message)


@dp.callback_query(F.data == "show_tokens")
async def callback_show_tokens(callback: types.CallbackQuery):
    """Обработчик кнопки показа токенов."""
    await callback.answer()
    await cmd_tokens(callback.message)


@dp.message(Command('model'))
async def cmd_model(message: types.Message):
    """Показывает меню выбора модели."""
    user_model_pages[message.from_user.id] = 0
    is_group = message.chat.type in ['group', 'supergroup']
    sent_msg = await message.answer(
        'Выберите модель для ответов:',
        reply_markup=build_model_keyboard(message.from_user.id)
    )
    if is_group:
        await track_technical_message(message.chat.id, sent_msg.message_id, is_group)


@dp.message(Command('clear'))
async def cmd_clear(message: types.Message):
    """Очищает историю диалога."""
    clear_history(message.chat.id)
    await message.answer('История чата очищена! 🗑')


@dp.message(Command('sticker'))
async def cmd_sticker(message: types.Message):
    """Отправляет случайный стикер (для теста)."""
    success = await send_random_sticker(message.chat.id)
    if not success:
        await message.answer('❌ Ошибка загрузки стикеров')


@dp.message(Command('export'))
async def cmd_export(message: types.Message):
    """Экспортирует историю диалога."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    history = load_history(chat_id, is_group=False)
    
    if not history:
        await message.answer('История диалога пуста.')
        return
    
    # Формируем текст экспорта
    import datetime
    export_text = f"📝 История диалога\n"
    export_text += f"👤 Пользователь: {message.from_user.full_name}\n"
    export_text += f"🆔 ID: {user_id}\n"
    export_text += f"📅 Экспорт: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    export_text += f"💬 Сообщений: {len(history)}\n\n"
    export_text += "=" * 50 + "\n\n"
    
    for idx, msg in enumerate(history, 1):
        role = "🙋 Пользователь" if msg['role'] == 'user' else "🤖 Бот"
        content = msg['content']
        export_text += f"{idx}. {role}:\n{content}\n\n"
        export_text += "-" * 50 + "\n\n"
    
    # Сохраняем в файл
    import time
    export_file = BASE_DIR / f'export_{user_id}_{int(time.time())}.txt'
    export_file.write_text(export_text, encoding='utf-8')
    
    # Отправляем файл
    await message.answer_document(
        types.FSInputFile(export_file),
        caption='📄 История диалога экспортирована'
    )
    
    # Удаляем файл после отправки
    export_file.unlink()


@dp.message(Command('admin'))
async def cmd_admin(message: types.Message):
    """Админ-панель (только для админов)."""
    if not is_admin(message.from_user.id):
        await message.answer('⛔️ У вас нет доступа к админ-панели.')
        return
    
    import datetime
    uptime = datetime.datetime.now() - bot_stats['start_time'] if bot_stats['start_time'] else datetime.timedelta(0)
    
    admin_text = (
        "👑 <b>Админ-панель</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Всего пользователей: {len(bot_stats['total_users'])}\n"
        f"💬 Всего сообщений: {bot_stats['total_messages']}\n"
        f"❌ Ошибок: {bot_stats['total_errors']}\n"
        f"⏱ Аптайм: {str(uptime).split('.')[0]}\n\n"
        f"🤖 <b>Модели:</b>\n"
        f"🔷 gpt4freepro: {len([m for m, p in MODEL_PROVIDERS.items() if p == 'gpt4freepro'])} моделей\n"
        f"🟣 puterjs: {len([m for m, p in MODEL_PROVIDERS.items() if p == 'puterjs'])} моделей\n\n"
        f"📋 <b>Команды админа:</b>\n"
        f"/admin - эта панель\n"
        f"/broadcast [текст] - рассылка всем\n"
        f"/stats - детальная статистика\n"
    )
    
    await message.answer(admin_text, parse_mode="HTML")


@dp.message(Command('stats'))
async def cmd_stats(message: types.Message):
    """Детальная статистика (только для админов)."""
    if not is_admin(message.from_user.id):
        await message.answer('⛔️ У вас нет доступа к статистике.')
        return
    
    # Статистика по моделям
    model_usage = {}
    for user_id, model in user_models.items():
        model_usage[model] = model_usage.get(model, 0) + 1
    
    top_models = sorted(model_usage.items(), key=lambda x: x[1], reverse=True)[:5]
    
    stats_text = (
        "📈 <b>Детальная статистика</b>\n\n"
        f"<b>Топ-5 моделей:</b>\n"
    )
    
    for idx, (model, count) in enumerate(top_models, 1):
        provider_emoji = "🔷" if MODEL_PROVIDERS.get(model) == 'gpt4freepro' else "🟣"
        stats_text += f"{idx}. {provider_emoji} {model}: {count} польз.\n"
    
    stats_text += f"\n<b>Активные пользователи:</b> {len(user_models)}"
    
    await message.answer(stats_text, parse_mode="HTML")


@dp.message(Command('broadcast'))
async def cmd_broadcast(message: types.Message):
    """Рассылка сообщения всем пользователям (только для админов)."""
    if not is_admin(message.from_user.id):
        await message.answer('⛔️ У вас нет доступа к рассылке.')
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer('Использование: /broadcast <текст>')
        return
    
    broadcast_text = args[1]
    success = 0
    failed = 0
    
    await message.answer(f'📤 Начинаю рассылку {len(bot_stats["total_users"])} пользователям...')
    
    for user_id in bot_stats['total_users']:
        try:
            await bot.send_message(user_id, broadcast_text)
            success += 1
        except Exception as e:
            failed += 1
            print(f'[broadcast] Ошибка отправки {user_id}: {e}')
        
        # Задержка чтобы не словить лимит
        await asyncio.sleep(0.05)
    
    await message.answer(
        f'✅ Рассылка завершена!\n'
        f'Успешно: {success}\n'
        f'Ошибок: {failed}'
    )




# ========================================
# Команды работы с документами временно отключены
# ========================================
# /askdoc, /listdocs, /deldoc - будут добавлены позже




@dp.message(Command('settings'))
async def cmd_settings(message: types.Message):
    """Управление персональными настройками."""
    user_id = message.from_user.id
    args = message.text.split()
    
    # Показать текущие настройки
    if len(args) == 1:
        settings = get_user_settings(user_id)
        settings_text = (
            "⚙️ <b>Персональные настройки</b>\n\n"
            f"🌡 <b>Temperature:</b> {settings['temperature']}\n"
            f"   (креативность: 0.0 - точность, 1.0 - креатив)\n\n"
            f"📏 <b>Max tokens:</b> {settings['max_tokens']}\n"
            f"   (максимальная длина ответа)\n\n"
            f"📝 <b>System prompt:</b> "
            f"{'установлен' if settings['system_prompt'] else 'не установлен'}\n\n"
            "<b>Команды:</b>\n"
            "/settings temp <0.0-1.0> - изменить температуру\n"
            "/settings tokens <число> - максимум токенов\n"
            "/settings prompt <текст> - системный промпт\n"
            "/settings reset - сбросить настройки"
        )
        await message.answer(settings_text, parse_mode="HTML")
        return
    
    # Изменить настройку
    if len(args) < 3:
        await message.answer('Использование: /settings <параметр> <значение>')
        return
    
    param = args[1].lower()
    value = ' '.join(args[2:])
    
    if param in ['temp', 'temperature']:
        try:
            temp = float(value)
            if not 0.0 <= temp <= 1.0:
                raise ValueError
            set_user_setting(user_id, 'temperature', temp)
            await message.answer(f'✅ Temperature изменен на {temp}')
        except ValueError:
            await message.answer('❌ Укажите число от 0.0 до 1.0')
    
    elif param in ['tokens', 'max_tokens']:
        try:
            tokens = int(value)
            if tokens < 100 or tokens > 10000:
                raise ValueError
            set_user_setting(user_id, 'max_tokens', tokens)
            await message.answer(f'✅ Max tokens изменен на {tokens}')
        except ValueError:
            await message.answer('❌ Укажите число от 100 до 10000')
    
    elif param == 'prompt':
        set_user_setting(user_id, 'system_prompt', value)
        await message.answer(f'✅ System prompt установлен:\n{value[:100]}...')
    
    elif param == 'reset':
        user_settings[user_id] = {
            'temperature': 0.7,
            'max_tokens': 2000,
            'system_prompt': None
        }
        await message.answer('✅ Настройки сброшены на стандартные')
    
    else:
        await message.answer('❌ Неизвестный параметр. Используйте: temp, tokens, prompt, reset')


@dp.message(Command('help'))
async def cmd_help(message: types.Message):
    """Показывает справку по командам."""
    print(f'[bot] Команда /help от {message.from_user.id} в чате {message.chat.id}')
    help_text = (
        "🤖 <b>AI Agent - умный помощник</b>\n\n"
        "⚙️ <b>Команды:</b>\n"
        "/model - Выбрать модель AI\n"
        "/settings - Персональные настройки\n"
        "/clear - Очистить историю\n"
        "/profile - Профиль\n"
        "/export - Экспорт истории\n"
        "/help - Эта справка\n\n"
        "🎨 <b>Дополнительно:</b>\n"
        "• 📷 Фото - AI опишет изображение\n"
        "• 🎭 Стикеры - AI распознает и опишет\n"
        "• 🎬 GIF - AI увидит и расскажет что там\n"
        "• 🎨 Генерация изображений\n"
        "• 🃏 Отправка стикеров\n\n"
        "🔐 <b>Токены PuterJS:</b>\n"
        "/auth - добавить токен\n\n"
        "💡 <b>Просто общайтесь!</b>\n"
        "AI сам выберет нужные инструменты."
    )
    await message.answer(help_text, parse_mode="HTML")


@dp.message(Command('auth'))
async def cmd_auth(message: types.Message):
    """Авторизация на Puter для получения токена."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎮 Открыть Puter Playground",
            url="https://docs.puter.com/playground"
        )]
    ])
    
    await message.answer(
        "🔐 <b>Получение токена Puter</b>\n\n"
        "📝 <b>Простой способ через Playground:</b>\n\n"
        "1️. Нажмите кнопку ниже\n"
        "2. В Playground Нужно выбрать Authentification \n\n"
        "3. Нажать ▶️ Run \n"
        "️4. После пройти регистрацию или авторизацию\n"
        "5. После авторизации в консоли появится токен - eyJhbGciOiJIU...  \n\n"
        "6.️ Скопируйте токен из консоли\n"
        "7. Отправьте сюда:\n"
        "   <code>/addtoken ВАШ_ТОКЕН</code>\n\n"
        "💡 Можно добавить несколько токенов для ротации\n"
        "⚡ Токены работают с лимитом запросов к сожелению - из-за этого их нужно как можно больше чтоб получить доступ к более 400+ моделей ИИ!"
        "\n\n"
        "<b>Примечание:</b> Если у вас есть несколько токенов, вы можете добавить их для ротации, чтобы распределить нагрузку и избежать превышения лимитов.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.message(Command('addtoken'))
async def cmd_addtoken(message: types.Message):
    """Добавляет токен пользователя."""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Использование: <code>/addtoken ВАШ_ТОКЕН</code>\n\n"
            "Получите токен через /auth",
            parse_mode="HTML"
        )
        return
    
    token = args[1].strip().strip('"').strip("'")
    
    if not token or len(token) < 50:
        await message.answer("❌ Токен слишком короткий или пустой")
        return
    
    # Добавляем токен в auth_token.json
    try:
        import puterjs
        data = puterjs.load_auth_tokens()
        tokens = data.setdefault("auth", {}).setdefault("tokens", [])
        
        # Проверяем дубликаты
        for existing in tokens:
            if existing.get("token") == token:
                await message.answer("⚠️ Этот токен уже добавлен!")
                return
        
        tokens.append({"token": token, "working": True})
        puterjs.save_auth_tokens(data)
        
        # Перезагружаем модели PuterJS
        models_count = puterjs.reload_models()
        
        total = len(puterjs.get_working_auth_tokens())
        
        if models_count > 0:
            await message.answer(
                f"✅ Токен добавлен!\n\n"
                f"📊 Всего токенов: {total}\n"
                f"🟣 Загружено моделей PuterJS: {models_count}\n"
                f"💡 Рекомендуется иметь 3-5 токенов для ротации"
            )
        else:
            await message.answer(
                f"⚠️ Токен добавлен, но не прошёл проверку\n\n"
                f"📊 Всего токенов: {total}\n"
                f"Попробуйте добавить другой токен через /auth"
            )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка добавления токена: {e}")


@dp.message(Command('tokens'))
async def cmd_tokens(message: types.Message):
    """Показывает статус токенов."""
    try:
        import puterjs
        data = puterjs.load_auth_tokens()
        all_tokens = data.get("auth", {}).get("tokens", [])
        working_tokens = puterjs.get_working_auth_tokens()
        
        if not all_tokens:
            await message.answer(
                "📋 <b>Нет сохранённых токенов</b>\n\n"
                "Добавьте токены через /auth",
                parse_mode="HTML"
            )
            return
        
        status_text = "📋 <b>Статус токенов</b>\n\n"
        
        for i, token_data in enumerate(all_tokens, 1):
            token = token_data.get("token", "")
            working = token_data.get("working", False)
            status = "✅" if working else "❌"
            preview = token[:20] + "..." + token[-10:] if len(token) > 30 else token
            status_text += f"{i}. {status} <code>{preview}</code>\n"
        
        status_text += f"\n📊 Рабочих токенов: {len(working_tokens)}/{len(all_tokens)}\n"
        status_text += f"💡 Рекомендуется: 3-5 токенов"
        
        await message.answer(status_text, parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def main():
    """Запуск бота."""
    # Инициализируем время старта
    import datetime
    bot_stats['start_time'] = datetime.datetime.now()
    
    # Загружаем стикеры при запуске
    await load_stickers()
    
    print('[bot] Бот запущен!')
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
