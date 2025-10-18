"""
AI Tools - tool set for AI agent.

Implements Function Calling for AI models. AI can autonomously choose and use tools for:
web search (DuckDuckGo), news, website parsing, document search.

Supported by: GPT-4, GPT-3.5, Claude 3+
"""
import json
from typing import Optional, Callable

import web_search
import document_processor


# Available tools definition
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Ищет информацию в интернете через поисковик. Используй когда нужна актуальная информация, факты, новости.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Получает последние новости. Используй когда спрашивают про новости или текущие события.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crawl_website",
            "description": "Извлекает текст с веб-страницы по URL. Используй когда нужно прочитать содержимое конкретного сайта.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL веб-страницы"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_documents",
            "description": "Ищет информацию в загруженных пользователем документах (PDF, DOCX, TXT). ВАЖНО: Используй этот инструмент ВСЕГДА когда пользователь спрашивает про работу, лабы, документы, задания, файлы или про то 'что в документе', 'над чем поработать', 'что там', 'че там' и т.п. Даже если явно не упоминаются документы - проверь их!",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "ID пользователя"
                    },
                    "query": {
                        "type": "string",
                        "description": "Что искать в документах. Можно использовать общие запросы типа 'все', 'что там', 'над чем поработать'"
                    }
                },
                "required": ["user_id", "query"]
            }
        }
    }
]


# Tool handler functions
def execute_tool(tool_name: str, arguments: dict) -> str:
    """
    Executes tool and returns result.
    
    Args:
        tool_name: tool name
        arguments: tool arguments
        
    Returns:
        str: execution result
    """
    try:
        if tool_name == "search_web":
            query = arguments.get("query", "")
            results = web_search.search_web(query, max_results=5)
            
            if not results:
                return f"По запросу '{query}' ничего не найдено"
            
            # Format results for AI
            formatted = []
            for r in results:
                formatted.append(
                    f"Название: {r['title']}\n"
                    f"Описание: {r['snippet']}\n"
                    f"URL: {r['url']}"
                )
            
            return "Результаты поиска:\n\n" + "\n\n".join(formatted)
        
        elif tool_name == "get_news":
            news = web_search.get_news(max_results=5)
            
            if not news:
                return "Не удалось получить новости"
            
            # Format news for AI
            formatted = []
            for n in news:
                formatted.append(
                    f"Заголовок: {n['title']}\n"
                    f"Дата: {n.get('date', 'N/A')}\n"
                    f"Описание: {n['snippet']}\n"
                    f"URL: {n['url']}"
                )
            
            return "Последние новости:\n\n" + "\n\n".join(formatted)
        
        elif tool_name == "crawl_website":
            url = arguments.get("url", "")
            text = web_search.crawl_website(url)
            
            if not text:
                return f"Не удалось извлечь текст с сайта {url}"
            
            # Truncate if too long
            if len(text) > 3000:
                text = text[:3000] + "..."
            
            return f"Текст с сайта {url}:\n\n{text}"
        
        elif tool_name == "search_in_documents":
            user_id = arguments.get("user_id")
            query = arguments.get("query", "")
            
            docs = document_processor.get_user_documents(user_id)
            
            if not docs:
                return "У пользователя нет загруженных документов"
            
            results = document_processor.search_in_documents(user_id, query)
            
            if not results:
                return f"В документах не найдено информации по запросу: {query}"
            
            # Форматируем результаты
            formatted = []
            for r in results[:3]:  # Топ-3
                formatted.append(
                    f"Document: {r['filename']}\n"
                    f"Context: {r['context']}"
                )
            
            return "Информация из документов:\n\n" + "\n\n".join(formatted)
        
        else:
            return f"Неизвестный инструмент: {tool_name}"
    
    except Exception as e:
        return f"Ошибка выполнения {tool_name}: {str(e)}"


def should_use_tools(model: str) -> bool:
    """Checks if model supports function calling."""
    # Models that support tools
    supported = [
        'gpt-4o', 'gpt-4o-mini', 'gpt-4', 'gpt-4-turbo',
        'gpt-3.5-turbo', 'gpt-5', 'claude-3', 'claude-3.5',
        'deepseek', 'qwen', 'gemini'
    ]
    
    return any(m in model.lower() for m in supported)
