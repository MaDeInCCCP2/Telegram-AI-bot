"""
Puter.js Provider for AI models.

This module provides integration with Puter.com API for:
- Text generation through multiple models
- Authorization token management
- Token rotation to bypass limits

Features:
- Token rotation system (up to 5 tokens simultaneously)
- Model list caching (TTL 1 hour)
- Blacklist for non-working models
- Automatic token validity verification
- Fallback to backup models on errors

Requires authorization on Puter.com to obtain tokens.
API: https://puter.com/
"""
import os
import json
import time
from pathlib import Path
from typing import Iterable

import requests
from dotenv import load_dotenv, set_key
from g4f.client import Client

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'
AUTH_TOKEN_PATH = BASE_DIR / 'auth_token.json'
MODELS_JSON_PATH = BASE_DIR / 'models.json'

load_dotenv()

CURRENT_AUTH_TOKEN: str | None = None
RAW_MODELS: list[str] = []
THINKING_MODELS: set[str] = set()
SEARCH_MODELS: set[str] = set()
DEFAULT_MODEL = "gpt-4o"
PUTER_API_KEY: str | None = None
CAPTCHA_API_KEY: str | None = os.getenv('TWOCAPTCHA_API_KEY')  # Optional for captcha bypass
MODELS_CACHE_FILE = BASE_DIR / 'puter_models_cache.json'
MODELS_CACHE_TTL = 3600  # Model cache for 1 hour
BLACKLIST_FILE = BASE_DIR / 'puter_models_blacklist.json'  # Non-working models list

# Token rotation settings
MIN_TOKENS = 3  # Minimum working tokens
MAX_TOKENS = 5  # Maximum tokens
TOKEN_ROTATION_INDEX = 0  # Current token index


class ProviderUnavailable(Exception):
    """Exception when provider is unavailable."""
    pass


def fetch_models_from_puter() -> list[str]:
    """Fetches model list from Puter API."""
    try:
        # Get models from Puter API
        url = "https://puter.com/puterai/chat/models"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        
        print(f'[puterjs] Request to {url}...')
        response = requests.get(url, headers=headers, timeout=10)
        print(f'[puterjs] Response status: {response.status_code}')
        print(f'[puterjs] Content-Type: {response.headers.get("Content-Type")}')
        print(f'[puterjs] First 300 chars of response: {response.text[:300]}')
        if response.status_code == 200:
            data = response.json()
            
            # Log for debugging
            print(f'[puterjs] API response format: {type(data).__name__}')
            if isinstance(data, dict):
                print(f'[puterjs] Response keys: {list(data.keys())[:5]}')
            
            # Extract model IDs from response
            models = []
            
            if isinstance(data, list):
                # Format: [{"id": "model1"}, {"id": "model2"}]
                for item in data:
                    if isinstance(item, dict):
                        model_id = item.get('id') or item.get('name') or item.get('model')
                        if model_id:
                            models.append(model_id)
            
            elif isinstance(data, dict):
                # Try different structure variants
                if 'models' in data:
                    # Format: {"models": [...]}
                    for item in data['models']:
                        if isinstance(item, dict):
                            model_id = item.get('id') or item.get('name') or item.get('model')
                            if model_id:
                                models.append(model_id)
                        elif isinstance(item, str):
                            models.append(item)
                
                elif 'data' in data:
                    # Format: {"data": [...]}
                    for item in data['data']:
                        if isinstance(item, dict):
                            model_id = item.get('id') or item.get('name') or item.get('model')
                            if model_id:
                                models.append(model_id)
                        elif isinstance(item, str):
                            models.append(item)
            
            if models:
                print(f'[puterjs] Loaded {len(models)} models from API: {models[:3]}...')
                return models
            else:
                print(f'[puterjs] Failed to extract models from response. First 200 chars: {str(data)[:200]}')
                raise ValueError('No models found in API response')
        
        print(f'[puterjs] Failed to get models from API (HTTP {response.status_code})')
        raise Exception(f'HTTP {response.status_code}')
        
    except Exception as error:
        print(f'[puterjs] Error loading models from API: {error}')
        # Fallback to known models
        fallback_models = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-3.5-turbo",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ]
        print(f'[puterjs] Using fallback list ({len(fallback_models)} models)')
        return fallback_models


def load_models_from_json() -> list[str]:
    """Loads model list from models.json (fallback)."""
    if not MODELS_JSON_PATH.exists():
        return []
    try:
        with MODELS_JSON_PATH.open('r', encoding='utf-8') as file:
            payload = json.load(file)
        models = payload.get('models')
        if not isinstance(models, list):
            raise ValueError('models.json has invalid format')
        return [str(model) for model in models]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f'[puterjs] Failed to read models.json: {error}')
        return []


def load_cached_models() -> tuple[list[str], bool]:
    """Loads models from cache. Returns (models, is_valid)."""
    if not MODELS_CACHE_FILE.exists():
        return [], False
    
    try:
        with MODELS_CACHE_FILE.open('r', encoding='utf-8') as f:
            cache = json.load(f)
        
        cached_time = cache.get('timestamp', 0)
        models = cache.get('models', [])
        
        # Check if cache is not stale
        if time.time() - cached_time < MODELS_CACHE_TTL and models:
            print(f'[puterjs] Loaded {len(models)} models from cache')
            return models, True
    except Exception as e:
        print(f'[puterjs] Cache read error: {e}')
    
    return [], False


def save_models_cache(models: list[str]) -> None:
    """Saves models to cache."""
    try:
        cache = {
            'timestamp': time.time(),
            'models': models
        }
        with MODELS_CACHE_FILE.open('w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
        print(f'[puterjs] Models saved to cache')
    except Exception as e:
        print(f'[puterjs] Cache save error: {e}')


def load_blacklist() -> set[str]:
    """Loads list of non-working models."""
    if not BLACKLIST_FILE.exists():
        return set()
    
    try:
        with BLACKLIST_FILE.open('r', encoding='utf-8') as f:
            data = json.load(f)
        blacklist = set(data.get('models', []))
        if blacklist:
            print(f'[puterjs] Loaded {len(blacklist)} models in blacklist')
        return blacklist
    except Exception as e:
        print(f'[puterjs] Blacklist read error: {e}')
        return set()


def save_blacklist(blacklist: set[str]) -> None:
    """Saves list of non-working models."""
    try:
        data = {
            'timestamp': time.time(),
            'models': sorted(list(blacklist))
        }
        with BLACKLIST_FILE.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f'[puterjs] Blacklist updated ({len(blacklist)} models)')
    except Exception as e:
        print(f'[puterjs] Blacklist save error: {e}')


def add_to_blacklist(model: str) -> None:
    """Adds model to blacklist."""
    blacklist = load_blacklist()
    if model not in blacklist:
        blacklist.add(model)
        save_blacklist(blacklist)
        print(f'[puterjs] Model {model} added to blacklist')
        
        # Update global model list
        global RAW_MODELS
        if model in RAW_MODELS:
            RAW_MODELS.remove(model)
            print(f'[puterjs] Model {model} removed from available list')


def verify_token(token: str) -> bool:
    """Verifies token validity via simple API request."""
    try:
        url = "https://api.puter.com/drivers/call"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        # Simple request to verify token
        response = requests.post(url, headers=headers, json={
            "interface": "puter-chat-completion",
            "driver": "openai",
            "method": "models"
        }, timeout=5)
        
        return response.status_code == 200
    except Exception as e:
        print(f'[puterjs] Token verification error: {e}')
        return False


def init_models() -> None:
    """Initializes model list and categories."""
    global RAW_MODELS, THINKING_MODELS, SEARCH_MODELS
    
    # Check working tokens availability FIRST
    working_tokens = get_working_auth_tokens()
    
    if not working_tokens:
        print('[puterjs] ⚠️ No working tokens - PuterJS models unavailable')
        print('[puterjs] Add tokens via: /auth in bot or python add_puter_tokens.py')
        RAW_MODELS = []
        THINKING_MODELS = set()
        SEARCH_MODELS = set()
        return
    
    # Verify first token validity
    print(f'[puterjs] Verifying token validity...')
    first_token = working_tokens[0]
    if not verify_token(first_token):
        print(f'[puterjs] ⚠️ Token invalid, marking as non-working')
        update_auth_token_status(first_token, False)
        # Try next one
        working_tokens = get_working_auth_tokens()
        if not working_tokens:
            print('[puterjs] ⚠️ No valid tokens - PuterJS models unavailable')
            RAW_MODELS = []
            THINKING_MODELS = set()
            SEARCH_MODELS = set()
            return
    
    print(f'[puterjs] ✅ Token valid, loading models...')
    
    # Load blacklist
    blacklist = load_blacklist()
    
    # Try to load from cache first
    cached_models, is_valid = load_cached_models()
    if is_valid:
        RAW_MODELS = cached_models
    else:
        # Get models from Puter API
        RAW_MODELS = fetch_models_from_puter()
        
        # Save to cache if received
        if RAW_MODELS:
            save_models_cache(RAW_MODELS)
        
        # If failed, use models.json
        if not RAW_MODELS:
            print('[puterjs] Using models.json as fallback')
            RAW_MODELS = load_models_from_json()
        
        # If that failed too, use defaults
        if not RAW_MODELS:
            print('[puterjs] Using default models')
            RAW_MODELS = [DEFAULT_MODEL, "gpt-4o-mini", "gpt-3.5-turbo"]
    
    # Apply blacklist
    if blacklist:
        original_count = len(RAW_MODELS)
        RAW_MODELS = [m for m in RAW_MODELS if m not in blacklist]
        removed_count = original_count - len(RAW_MODELS)
        if removed_count > 0:
            print(f'[puterjs] Excluded {removed_count} models from blacklist')

    THINKING_MODELS = {m for m in RAW_MODELS if 'think' in m.lower() or 'reason' in m.lower()}
    SEARCH_MODELS = {m for m in RAW_MODELS if 'search' in m.lower() or 'internet' in m.lower()}


def list_models() -> list[str]:
    """Returns list of available models."""
    return RAW_MODELS.copy()


def reload_models() -> int:
    """Reloads models (e.g., after adding tokens). Returns model count."""
    print('[puterjs] Reloading models...')
    init_models()
    return len(RAW_MODELS)


def refresh_models() -> bool:
    """Force updates model list from API."""
    global RAW_MODELS, THINKING_MODELS, SEARCH_MODELS
    
    print('[puterjs] Force updating models...')
    new_models = fetch_models_from_puter()
    
    if new_models:
        RAW_MODELS = new_models
        save_models_cache(new_models)
        THINKING_MODELS = {m for m in RAW_MODELS if 'think' in m.lower() or 'reason' in m.lower()}
        SEARCH_MODELS = {m for m in RAW_MODELS if 'search' in m.lower() or 'internet' in m.lower()}
        print(f'[puterjs] Models updated: {len(RAW_MODELS)} models')
        return True
    
    print('[puterjs] Failed to update models')
    return False


def supports_images() -> bool:
    """Returns False as PuterJS doesn't support image generation."""
    return False


def ensure_file(path: Path):
    """Creates file if it doesn't exist."""
    if not path.exists():
        path.touch()


def load_auth_tokens() -> dict:
    if AUTH_TOKEN_PATH.exists():
        try:
            with AUTH_TOKEN_PATH.open('r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"auth": {"tokens": []}}


def save_auth_tokens(data: dict) -> None:
    ensure_file(AUTH_TOKEN_PATH)
    with AUTH_TOKEN_PATH.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def get_working_auth_tokens() -> list[str]:
    """Returns list of all working tokens."""
    data = load_auth_tokens()
    working_tokens = []
    for token in data.get("auth", {}).get("tokens", []):
        if token.get("working"):
            working_tokens.append(token.get("token"))
    return working_tokens


def get_working_auth_token() -> str | None:
    """Returns one working token (for backwards compatibility)."""
    tokens = get_working_auth_tokens()
    return tokens[0] if tokens else None


def get_next_working_token() -> str | None:
    """Returns next working token by rotation."""
    global TOKEN_ROTATION_INDEX
    tokens = get_working_auth_tokens()
    
    if not tokens:
        return None
    
    # Circular rotation
    TOKEN_ROTATION_INDEX = TOKEN_ROTATION_INDEX % len(tokens)
    token = tokens[TOKEN_ROTATION_INDEX]
    TOKEN_ROTATION_INDEX += 1
    
    return token


def update_auth_token_status(token: str, working: bool) -> None:
    if not token:
        return
    data = load_auth_tokens()
    auth = data.setdefault("auth", {})
    tokens = auth.setdefault("tokens", [])
    for entry in tokens:
        if entry.get("token") == token:
            entry["working"] = working
            save_auth_tokens(data)
            return
    tokens.append({"token": token, "working": working})
    save_auth_tokens(data)


def solve_captcha_if_needed(response_data: dict) -> dict:
    """
    Solves captcha via 2captcha if required.
    Requires TWOCAPTCHA_API_KEY in .env
    """
    if not CAPTCHA_API_KEY:
        return response_data
    
    # Check if captcha is required
    if response_data.get('captcha_required'):
        print('[puterjs] Captcha detected, attempting solution via 2captcha...')
        try:
            import requests as req
            # Send captcha for solving (example for reCAPTCHA)
            captcha_url = "http://2captcha.com/in.php"
            params = {
                'key': CAPTCHA_API_KEY,
                'method': 'userrecaptcha',
                'googlekey': response_data.get('captcha_sitekey', ''),
                'pageurl': 'https://puter.com',
                'json': 1
            }
            resp = req.get(captcha_url, params=params, timeout=30)
            if resp.json().get('status') == 1:
                captcha_id = resp.json().get('request')
                # Wait for solution
                for _ in range(30):
                    time.sleep(5)
                    result_url = f"http://2captcha.com/res.php?key={CAPTCHA_API_KEY}&action=get&id={captcha_id}&json=1"
                    result = req.get(result_url, timeout=10).json()
                    if result.get('status') == 1:
                        print('[puterjs] Captcha solved!')
                        return {'captcha_solution': result.get('request')}
                print('[puterjs] Failed to solve captcha within time limit')
        except Exception as e:
            print(f'[puterjs] Captcha solving error: {e}')
    
    return response_data


def signup_user(retry_count: int = 3) -> str | None:
    """Registers temporary user in Puter with retry logic."""
    endpoints = [
        "https://api.puter.com/signup",
        "https://puter.com/signup",
    ]
    
    for attempt in range(retry_count):
        headers = {
            "Content-Type": "application/json",
            "host": "api.puter.com",
            "connection": "keep-alive",
            "sec-ch-ua-platform": "macOS",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "sec-ch-ua-mobile": "?0",
            "accept": "*/*",
            "origin": "https://puter.com",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://puter.com/",
            "accept-encoding": "gzip",
            "accept-language": "en-US,en;q=0.9",
        }
        
        session = requests.Session()
        for url in endpoints:
            try:
                print(f'[puterjs] Registration attempt {attempt + 1}/{retry_count} on {url}...')
                response = session.post(url, headers=headers, json={"is_temp": True}, timeout=30)
                
                if response.status_code == 200:
                    token = response.json().get("token")
                    if token:
                        print(f'[puterjs] Successfully obtained new token')
                        update_auth_token_status(token, True)
                        return token
                elif response.status_code == 429:
                    print(f'[puterjs] Rate limit (429), waiting {(attempt + 1) * 5} seconds...')
                    time.sleep((attempt + 1) * 5)
                    continue
                else:
                    print(f'[puterjs] Registration error {response.status_code}: {response.text[:200]}')
                    
            except requests.RequestException as error:
                print(f'[puterjs] Request error on {url}: {error}')
        
        if attempt < retry_count - 1:
            wait_time = (attempt + 1) * 3
            print(f'[puterjs] Waiting {wait_time} seconds before next attempt...')
            time.sleep(wait_time)
    
    print('[puterjs] Failed to obtain token after all attempts')
    return None


def get_user_app_token(auth_token: str) -> str | None:
    url = "https://api.puter.com/auth/get-user-app-token"
    headers = {
        "host": "api.puter.com",
        "connection": "keep-alive",
        "authorization": f"Bearer {auth_token}",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "accept": "*/*",
        "origin": "https://puter.com",
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "referer": "https://puter.com/",
        "accept-encoding": "gzip",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
    }
    try:
        response = requests.post(url, headers=headers, json={"origin": "http://localhost"}, timeout=30)
        response.raise_for_status()
        return response.json().get("token")
    except requests.RequestException as error:
        print(f'Failed to obtain Puter user token: {error}')
        return None


def save_puter_api_key(token: str) -> None:
    ensure_file(ENV_PATH)
    set_key(str(ENV_PATH), 'PUTER_API_KEY', token)
    os.environ['PUTER_API_KEY'] = token
    print('Updated PUTER_API_KEY')


def ensure_token_pool() -> None:
    """Checks token availability."""
    working_tokens = get_working_auth_tokens()
    current_count = len(working_tokens)
    
    if current_count >= MIN_TOKENS:
        print(f'[puterjs] Token pool: {current_count}/{MIN_TOKENS} ✓')
    elif current_count > 0:
        print(f'[puterjs] ⚠️ Token pool: {current_count}/{MIN_TOKENS} (recommended to add more)')
    else:
        print(f'[puterjs] ⚠️ No tokens! Add tokens via: python add_puter_tokens.py')


def acquire_puter_api_key(force: bool = False) -> str | None:
    """Gets or updates PUTER_API_KEY with token rotation."""
    global CURRENT_AUTH_TOKEN, PUTER_API_KEY

    api_key = os.getenv('PUTER_API_KEY')
    if api_key and not force:
        PUTER_API_KEY = api_key
        ensure_token_pool()
        return api_key

    ensure_token_pool()

    # Use token rotation (auth tokens directly)
    auth_token = get_next_working_token()
    
    if not auth_token:
        print('[puterjs] ⚠️ No available tokens!')
        print('[puterjs] Add tokens via: python add_puter_tokens.py')
        return None

    # Use auth token directly (Puter blocked get-user-app-token)
    CURRENT_AUTH_TOKEN = auth_token
    PUTER_API_KEY = auth_token
    save_puter_api_key(auth_token)
    
    print(f'[puterjs] Switched to token #{TOKEN_ROTATION_INDEX}, pool: {len(get_working_auth_tokens())} tokens')
    return auth_token


def prompt_manual_token() -> str | None:
    """Prompts for PUTER_API_KEY manually."""
    print('[puterjs] Enter PUTER_API_KEY manually. You can get token at https://docs.puter.com/playground via localStorage.')
    manual = input('PUTER_API_KEY: ').strip()
    if manual:
        save_puter_api_key(manual)
        global PUTER_API_KEY
        PUTER_API_KEY = manual
        return manual
    return None


# Initialize PUTER_API_KEY on import
try:
    PUTER_API_KEY = acquire_puter_api_key(force=False)
except KeyboardInterrupt:
    print('[puterjs] ⚠️ Interrupted by user')
    PUTER_API_KEY = None
except Exception as e:
    print(f'[puterjs] ⚠️ Failed to obtain token: {e}')
    print('[puterjs] PuterJS will be unavailable, use only gpt4freepro models')
    PUTER_API_KEY = None

client = Client()


def build_messages(history: Iterable[dict[str, str]], user_text: str, model: str) -> list[dict[str, str]]:
    """Builds message list for API."""
    messages = []
    for item in history:
        messages.append({"role": item["role"], "content": item["content"]})

    extra_instructions = []
    if model in THINKING_MODELS:
        extra_instructions.append('Use detailed step-by-step reasoning, but return only the final answer to user.')
    if model in SEARCH_MODELS:
        extra_instructions.append('If information is insufficient, inform user that search is needed and suggest appropriate steps.')
    
    # Add sticker instructions
    extra_instructions.append('You can send stickers! If you want to send a sticker in response, add [STICKER] marker anywhere in text. Sticker will be sent automatically. Use stickers for emotions, reactions or when words are not enough.')
    
    if extra_instructions:
        messages.insert(0, {"role": "system", "content": " ".join(extra_instructions)})

    messages.append({"role": "user", "content": user_text})
    return messages


def generate_text(history: Iterable[dict[str, str]], text: str, model: str) -> str:
    """Generates text response via PuterJS."""
    global PUTER_API_KEY, CURRENT_AUTH_TOKEN
    
    if not PUTER_API_KEY:
        raise ProviderUnavailable('PUTER_API_KEY not obtained')
    
    working_count = len(get_working_auth_tokens())
    print(f'[puterjs] Available tokens: {working_count}')
    
    # Save current token for tracking
    current_token = PUTER_API_KEY
    
    try:
        response = client.chat.completions.create(
            model=model,
            provider="PuterJS",
            api_key=PUTER_API_KEY,
            messages=build_messages(history, text, model)
        )
        return response.choices[0].message.content
    except Exception as e:
        error_text = str(e)
        
        # Check if error is "model not found"
        if 'model' in error_text.lower() and ('not found' in error_text.lower() or 'invalid' in error_text.lower() or 'field_invalid' in error_text.lower()):
            print(f'[puterjs] Model {model} not supported, adding to blacklist')
            add_to_blacklist(model)
            raise ProviderUnavailable(f'PuterJS unavailable: {e}') from e
        
        # Check usage limit
        if 'usage-limited-chat' in error_text or 'Permission denied' in error_text:
            print(f'[puterjs] Token reached usage limit, marking as non-working...')
            # Mark current token as non-working
            update_auth_token_status(current_token, False)
            
            # Get next token
            print(f'[puterjs] Switching to next token...')
            PUTER_API_KEY = acquire_puter_api_key(force=True)
            if not PUTER_API_KEY:
                raise ProviderUnavailable('No available tokens') from e
            
            print(f'[puterjs] Retrying with new token...')
            # Retry with new token
            new_token = PUTER_API_KEY
            try:
                response = client.chat.completions.create(
                    model=model,
                    provider="PuterJS",
                    api_key=PUTER_API_KEY,
                    messages=build_messages(history, text, model)
                )
                print(f'[puterjs] ✅ Successfully switched to new token')
                return response.choices[0].message.content
            except Exception as retry_error:
                retry_error_text = str(retry_error)
                
                # Check limit on retry attempt too
                if 'usage-limited-chat' in retry_error_text or 'Permission denied' in retry_error_text:
                    print(f'[puterjs] ⚠️ New token also reached limit, marking as non-working')
                    update_auth_token_status(new_token, False)
                
                # Check model error on retry attempt
                if 'model' in retry_error_text.lower() and ('not found' in retry_error_text.lower() or 'invalid' in retry_error_text.lower() or 'field_invalid' in retry_error_text.lower()):
                    print(f'[puterjs] Model {model} not supported (retry), adding to blacklist')
                    add_to_blacklist(model)
                raise ProviderUnavailable(f'PuterJS unavailable: {retry_error}') from retry_error
        
        # Check authorization error
        if '401' in error_text or 'Authentication failed' in error_text:
            print(f'[puterjs] Authorization error, marking token as non-working...')
            update_auth_token_status(current_token, False)
            
            print(f'[puterjs] Switching to next token...')
            PUTER_API_KEY = acquire_puter_api_key(force=True)
            if not PUTER_API_KEY:
                raise ProviderUnavailable('Failed to update PUTER_API_KEY') from e
            
            # Retry attempt
            new_token = PUTER_API_KEY
            try:
                response = client.chat.completions.create(
                    model=model,
                    provider="PuterJS",
                    api_key=PUTER_API_KEY,
                    messages=build_messages(history, text, model)
                )
                print(f'[puterjs] ✅ Successfully switched to new token')
                return response.choices[0].message.content
            except Exception as retry_error:
                retry_error_text = str(retry_error)
                
                # Check limit on retry attempt too
                if 'usage-limited-chat' in retry_error_text or 'Permission denied' in retry_error_text:
                    print(f'[puterjs] ⚠️ New token also reached limit, marking as non-working')
                    update_auth_token_status(new_token, False)
                
                # Check model error on retry too
                if 'model' in retry_error_text.lower() and ('not found' in retry_error_text.lower() or 'invalid' in retry_error_text.lower() or 'field_invalid' in retry_error_text.lower()):
                    print(f'[puterjs] Model {model} not supported (retry), adding to blacklist')
                    add_to_blacklist(model)
                raise ProviderUnavailable(f'PuterJS unavailable: {retry_error}') from retry_error
        
        raise ProviderUnavailable(f'PuterJS unavailable: {e}') from e


# Initialize models when module loads
init_models()
