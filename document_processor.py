"""
Document processing and RAG (Retrieval-Augmented Generation) implementation.

Features: Text extraction from PDF/DOCX/TXT, document indexing, relevance search,
user document management.

Data stored locally in documents_index.json
"""
import os
import json
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / 'user_documents'
DOCS_INDEX_PATH = BASE_DIR / 'documents_index.json'

# Create documents directory
DOCS_DIR.mkdir(exist_ok=True)


def load_documents_index() -> dict:
    """Loads documents index."""
    if not DOCS_INDEX_PATH.exists():
        return {}
    try:
        with DOCS_INDEX_PATH.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_documents_index(index: dict) -> None:
    """Saves documents index."""
    with DOCS_INDEX_PATH.open('w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def extract_text_from_pdf(file_path: Path) -> str:
    """Extracts text from PDF."""
    try:
        import PyPDF2
        text = []
        with file_path.open('rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text.append(page.extract_text())
        return '\n'.join(text)
    except Exception as e:
        raise RuntimeError(f'Ошибка чтения PDF: {e}')


def extract_text_from_docx(file_path: Path) -> str:
    """Extracts text from DOCX."""
    try:
        from docx import Document
        doc = Document(file_path)
        text = []
        for para in doc.paragraphs:
            if para.text.strip():
                text.append(para.text)
        return '\n'.join(text)
    except Exception as e:
        raise RuntimeError(f'Ошибка чтения DOCX: {e}')


def extract_text_from_txt(file_path: Path) -> str:
    """Extracts text from TXT."""
    try:
        with file_path.open('r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # Try other encodings
        for encoding in ['cp1251', 'latin-1']:
            try:
                with file_path.open('r', encoding=encoding) as f:
                    return f.read()
            except:
                continue
        raise RuntimeError('Не удалось определить кодировку текстового файла')


def detect_file_type(filename: str) -> str:
    """Detects file type by extension."""
    ext = Path(filename).suffix.lower()
    if ext == '.pdf':
        return 'pdf'
    elif ext in ['.doc', '.docx']:
        return 'docx'
    elif ext == '.txt':
        return 'txt'
    else:
        return 'unknown'


def process_document(file_path: Path, user_id: int, filename: str) -> dict:
    """
    Processes document: detects type, extracts text, saves to index.
    
    Returns:
        dict with document info
    """
    file_type = detect_file_type(filename)
    
    if file_type == 'unknown':
        raise ValueError(f'Неподдерживаемый формат файла: {Path(filename).suffix}')
    
    # Extract text
    if file_type == 'pdf':
        text = extract_text_from_pdf(file_path)
    elif file_type == 'docx':
        text = extract_text_from_docx(file_path)
    elif file_type == 'txt':
        text = extract_text_from_txt(file_path)
    
    if not text.strip():
        raise ValueError('Документ пустой или не удалось извлечь текст')
    
    # Save to index
    index = load_documents_index()
    if str(user_id) not in index:
        index[str(user_id)] = []
    
    doc_id = f"{user_id}_{len(index[str(user_id)])}"
    doc_info = {
        'id': doc_id,
        'filename': filename,
        'type': file_type,
        'text': text,
        'size': len(text),
        'timestamp': str(Path(file_path).stat().st_mtime)
    }
    
    index[str(user_id)].append(doc_info)
    save_documents_index(index)
    
    return doc_info


def get_user_documents(user_id: int) -> list:
    """Returns user's document list."""
    index = load_documents_index()
    return index.get(str(user_id), [])


def get_document_by_id(user_id: int, doc_id: str) -> Optional[dict]:
    """Returns document by ID."""
    docs = get_user_documents(user_id)
    for doc in docs:
        if doc['id'] == doc_id:
            return doc
    return None


def delete_document(user_id: int, doc_id: str) -> bool:
    """Deletes document."""
    index = load_documents_index()
    if str(user_id) not in index:
        return False
    
    docs = index[str(user_id)]
    index[str(user_id)] = [d for d in docs if d['id'] != doc_id]
    save_documents_index(index)
    return True


def search_in_documents(user_id: int, query: str) -> list:
    """
    Searches in user's documents.
    ALWAYS returns documents if available!
    """
    docs = get_user_documents(user_id)
    
    if not docs:
        return []
    
    results = []
    query_lower = query.lower()
    
    for doc in docs:
        text = doc['text']
        text_lower = text.lower()
        
        # Try to find specific matches
        keywords = [w for w in query_lower.split() if len(w) >= 3]
        relevance = 0
        matched_parts = []
        
        for keyword in keywords:
            if keyword in text_lower:
                relevance += text_lower.count(keyword)
                # Find context
                index = text_lower.find(keyword)
                start = max(0, index - 250)
                end = min(len(text), index + 250)
                matched_parts.append(text[start:end])
        
        # If found specific matches - use them
        if relevance > 0:
            context = ' ... '.join(matched_parts[:3])
            results.append({
                'doc_id': doc['id'],
                'filename': doc['filename'],
                'context': context,
                'relevance': relevance
            })
        else:
            # No specific words found - return document start
            # (user probably asking about whole document)
            context = text[:1500] if len(text) > 1500 else text
            results.append({
                'doc_id': doc['id'],
                'filename': doc['filename'],
                'context': context,
                'relevance': 50  # Средняя релевантность
            })
    
    # Sort: specific matches first, then others
    results.sort(key=lambda x: x['relevance'], reverse=True)
    return results
