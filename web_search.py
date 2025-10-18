"""
Web search and website parsing module.

Features: DuckDuckGo search, news fetching, webpage text extraction, result formatting.
No API keys required, automatic cleanup, length limiting, User-Agent for bypass.
"""
from typing import Optional
import requests
from bs4 import BeautifulSoup


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    Searches web via DuckDuckGo.
    
    Returns:
        list of dict: [{'title': str, 'url': str, 'snippet': str}, ...]
    """
    try:
        from duckduckgo_search import DDGS
        
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    'title': r.get('title', ''),
                    'url': r.get('href', ''),
                    'snippet': r.get('body', '')
                })
        
        return results
    except Exception as e:
        print(f'[web_search] Ошибка поиска: {e}')
        return []


def get_news(max_results: int = 5) -> list[dict]:
    """
    Fetches latest news.
    
    Returns:
        list of dict: [{'title': str, 'url': str, 'snippet': str}, ...]
    """
    try:
        from duckduckgo_search import DDGS
        
        results = []
        with DDGS() as ddgs:
            for r in ddgs.news("latest news", max_results=max_results):
                results.append({
                    'title': r.get('title', ''),
                    'url': r.get('url', ''),
                    'snippet': r.get('body', ''),
                    'date': r.get('date', '')
                })
        
        return results
    except Exception as e:
        print(f'[web_search] Ошибка получения новостей: {e}')
        return []


def crawl_website(url: str, max_length: int = 5000) -> Optional[str]:
    """
    Extracts text content from webpage.
    
    Args:
        url: website URL
        max_length: max text length
        
    Returns:
        str: extracted text or None on error
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove scripts and styles
        for script in soup(['script', 'style', 'nav', 'footer', 'header']):
            script.decompose()
        
        # Extract text
        text = soup.get_text(separator='\n', strip=True)
        
        # Clean extra newlines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = '\n'.join(lines)
        
        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length] + '...'
        
        return text
    
    except Exception as e:
        print(f'[web_search] Ошибка парсинга {url}: {e}')
        return None


def format_search_results(results: list[dict]) -> str:
    """Formats search results for display."""
    if not results:
        return 'Ничего не найдено'
    
    formatted = []
    for idx, result in enumerate(results, 1):
        title = result.get('title', 'Без названия')
        url = result.get('url', '')
        snippet = result.get('snippet', '')
        
        formatted.append(
            f"{idx}. <b>{title}</b>\n"
            f"   {snippet[:200]}...\n"
            f"   🔗 {url}\n"
        )
    
    return '\n'.join(formatted)


def format_news(news: list[dict]) -> str:
    """Formats news for display."""
    if not news:
        return 'Новости не найдены'
    
    formatted = []
    for idx, item in enumerate(news, 1):
        title = item.get('title', 'Без названия')
        url = item.get('url', '')
        snippet = item.get('snippet', '')
        date = item.get('date', '')
        
        formatted.append(
            f"{idx}. <b>{title}</b>\n"
            f"   📅 {date}\n"
            f"   {snippet[:150]}...\n"
            f"   🔗 {url}\n"
        )
    
    return '\n'.join(formatted)
