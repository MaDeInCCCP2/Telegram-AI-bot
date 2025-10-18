"""
gpt4free.pro provider for AI models.

Features: Text generation (GPT-4, Claude, DeepSeek), image generation (DALL-E, Flux),
automatic model list fetching, fallback to models.json, model categorization,
ad filtering in responses.

API: https://gpt4free.pro/v1/
"""
import os
import json
from pathlib import Path
from typing import Iterable

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
MODELS_JSON_PATH = BASE_DIR / 'models.json'

load_dotenv()

API_BASE_URL = os.getenv('GPT4FREE_API_BASE', 'https://gpt4free.pro/v1')
API_KEY = os.getenv('GPT4FREE_API_KEY', '')

DEFAULT_MODEL = 'gpt-4o'
THINKING_MODELS: set[str] = set()
SEARCH_MODELS: set[str] = set()
IMAGE_MODELS: set[str] = set()
RAW_MODELS: list[str] = []


class ProviderUnavailable(Exception):
    """Raised when provider is unavailable."""
    pass


def fetch_models_from_api() -> list[str]:
    """Fetches model list from gpt4free.pro API."""
    url = f"{API_BASE_URL.rstrip('/')}/models"
    headers = {'Content-Type': 'application/json'}
    if API_KEY:
        headers['Authorization'] = f'Bearer {API_KEY}'
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Response format: {"data": [{"id": "model-name", ...}, ...]}
        if isinstance(data, dict) and 'data' in data:
            models = [item['id'] for item in data['data'] if isinstance(item, dict) and 'id' in item]
            if models:
                print(f'[gpt4freepro] Загружено {len(models)} моделей от API')
                return models
        
        print(f'[gpt4freepro] Некорректный формат ответа API: {data}')
        return []
    except Exception as error:
        print(f'[gpt4freepro] Не удалось получить модели от API: {error}')
        return []


def load_models_from_json() -> list[str]:
    """Loads model list from models.json (fallback)."""
    if not MODELS_JSON_PATH.exists():
        return []
    try:
        with MODELS_JSON_PATH.open('r', encoding='utf-8') as file:
            payload = json.load(file)
        models = payload.get('models')
        if not isinstance(models, list):
            raise ValueError('models.json имеет неверный формат')
        return [str(model) for model in models]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f'[gpt4freepro] Не удалось прочитать models.json: {error}')
        return []


def init_models() -> None:
    """Initializes model list and categories."""
    global RAW_MODELS, THINKING_MODELS, SEARCH_MODELS, IMAGE_MODELS
    
    # Try to fetch from API first
    RAW_MODELS = fetch_models_from_api()
    
    # If failed, use models.json
    if not RAW_MODELS:
        print('[gpt4freepro] Использую models.json как fallback')
        RAW_MODELS = load_models_from_json()
    
    # If that also failed, use defaults
    if not RAW_MODELS:
        print('[gpt4freepro] Использую дефолтные модели')
        RAW_MODELS = [DEFAULT_MODEL, 'gpt-4o-mini', 'claude-3-opus', 'deepseek-v3.2']
    
    THINKING_MODELS = {m for m in RAW_MODELS if 'think' in m.lower() or 'reason' in m.lower()}
    SEARCH_MODELS = {m for m in RAW_MODELS if 'search' in m.lower() or 'internet' in m.lower()}
    
    # Image generation models (by keywords)
    IMAGE_MODELS = {
        m for m in RAW_MODELS 
        if any(keyword in m.lower() for keyword in [
            'image', 'dall-e', 'dalle', 'midjourney', 'stable-diffusion', 
            'sd', 'flux', 'banana', 'gpt-image'
        ])
    }


init_models()


def list_models() -> list[str]:
    """Returns list of available models."""
    return RAW_MODELS.copy()


def supports_images() -> bool:
    """Returns True if provider supports image generation."""
    return True


def is_image_model(model: str) -> bool:
    """Checks if model is for image generation."""
    return model in IMAGE_MODELS


def get_default_image_model() -> str:
    """Returns default image generation model."""
    # Priority: dall-e > banana > flux > any image model
    for keyword in ['dall-e-3', 'dalle-3', 'banana', 'dall-e', 'dalle', 'flux', 'image']:
        for model in IMAGE_MODELS:
            if keyword in model.lower():
                print(f'[gpt4freepro] Выбрана модель для изображений: {model}')
                return model
    return 'dall-e-3'  # fallback


def list_image_models() -> list[str]:
    """Returns list of image generation models."""
    return sorted(list(IMAGE_MODELS))


def build_messages(history: Iterable[dict[str, str]], user_text: str, model: str) -> list[dict[str, str]]:
    """Builds message list for API."""
    messages: list[dict[str, str]] = []
    messages.extend({"role": item["role"], "content": item["content"]} for item in history)

    extra = []
    if model in THINKING_MODELS:
        extra.append('Размышляй последовательно и показывай только финальный ответ пользователю.')
    if model in SEARCH_MODELS:
        extra.append('Если требуется интернет-поиск, отметь это и опиши предполагаемые шаги.')
    
    # Add sticker instructions
    extra.append('Ты можешь отправлять стикеры! Если хочешь отправить стикер в ответе, добавь маркер [STICKER] в любом месте текста. Стикер будет отправлен автоматически. Используй стикеры для эмоций, реакций или когда слов недостаточно.')
    
    if extra:
        messages.insert(0, {"role": "system", "content": " ".join(extra)})

    messages.append({"role": "user", "content": user_text})
    return messages


def generate_text(history: Iterable[dict[str, str]], text: str, model: str) -> str:
    """Generates text response via gpt4free.pro."""
    url = f"{API_BASE_URL.rstrip('/')}/chat/completions"
    headers = {'Content-Type': 'application/json'}
    if API_KEY:
        headers['Authorization'] = f'Bearer {API_KEY}'
    
    messages = build_messages(history, text, model)
    payload = {
        'model': model,
        'messages': messages,
        'stream': False,
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
    except requests.HTTPError as error:
        status = error.response.status_code
        if status in (401, 403, 429, 503):
            raise ProviderUnavailable(f'gpt4free.pro недоступен (HTTP {status})') from error
        raise RuntimeError(f'gpt4free.pro вернул ошибку {status}: {error.response.text}') from error
    except (requests.RequestException, json.JSONDecodeError) as error:
        raise ProviderUnavailable(f'Не удалось связаться с gpt4free.pro: {error}') from error

    choices = data.get('choices') if isinstance(data, dict) else None
    if not choices:
        raise RuntimeError(f'Некорректный ответ gpt4free.pro: {data}')
    message = choices[0].get('message') if isinstance(choices[0], dict) else None
    if not message or 'content' not in message:
        raise RuntimeError(f'Ответ gpt4free.pro без текста: {choices[0]}')
    
    content = message['content']
    
    # Remove Pollinations.AI ads added by API
    import re
    # Remove ad block (starts with "---" and contains "Support Pollinations")
    content = re.sub(r'\n*---\n*\*\*Support Pollinations\.AI:\*\*.*', '', content, flags=re.DOTALL | re.IGNORECASE)
    # Remove variant without separator
    content = re.sub(r'\n*\*\*Support Pollinations\.AI:\*\*.*', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    return content.strip()


def generate_image(prompt: str, model: str = 'dall-e-3', size: str = '1024x1024') -> str:
    """Generates image via gpt4free.pro and returns URL."""
    url = f"{API_BASE_URL.rstrip('/')}/images/generations"
    headers = {'Content-Type': 'application/json'}
    if API_KEY:
        headers['Authorization'] = f'Bearer {API_KEY}'
    
    payload = {
        'model': model,
        'prompt': prompt,
        'n': 1,
        'size': size,
    }
    
    print(f'[gpt4freepro] Запрос изображения: model={model}, prompt={prompt[:50]}...')
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
    except requests.Timeout as error:
        raise ProviderUnavailable('gpt4free.pro не отвечает (таймаут 60 сек)') from error
    except requests.HTTPError as error:
        status = error.response.status_code
        if status in (401, 403, 429, 503):
            raise ProviderUnavailable(f'gpt4free.pro недоступен для изображений (HTTP {status})') from error
        raise RuntimeError(f'gpt4free.pro вернул ошибку {status}: {error.response.text}') from error
    except (requests.RequestException, json.JSONDecodeError) as error:
        raise ProviderUnavailable(f'Не удалось связаться с gpt4free.pro: {error}') from error

    images = data.get('data') if isinstance(data, dict) else None
    if not images or not isinstance(images, list) or len(images) == 0:
        raise RuntimeError(f'Некорректный ответ gpt4free.pro для изображения: {data}')
    image_url = images[0].get('url')
    if not image_url:
        raise RuntimeError(f'Ответ gpt4free.pro без URL изображения: {images[0]}')
    return image_url
