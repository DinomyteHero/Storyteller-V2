"""EPUB file reading and parsing utilities."""
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import re
from typing import List, Tuple, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def html_to_text(html_content: str) -> str:
    """Convert HTML content to plain text, preserving structure."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Get text and normalize whitespace
    text = soup.get_text()
    
    # Normalize whitespace: multiple spaces/newlines to single, preserve paragraph breaks
    text = re.sub(r'\n\s*\n+', '\n\n', text)  # Multiple newlines to double
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single
    text = text.strip()
    
    return text


def read_epub(file_path: Path) -> Tuple[str, Optional[str], Optional[str], List[Tuple[str, str]]]:
    """Read an EPUB file and extract content, metadata, and chapters.
    
    Args:
        file_path: Path to EPUB file
        
    Returns:
        Tuple of (book_title, author, full_text, chapters)
        chapters is a list of (chapter_title, chapter_text) tuples
    """
    try:
        book = epub.read_epub(str(file_path))
    except Exception as e:
        logger.error(f"Failed to read EPUB: {e}")
        raise
    
    # Extract metadata
    book_title = None
    author = None
    
    # Try to get title from metadata
    if book.get_metadata('DC', 'title'):
        book_title = book.get_metadata('DC', 'title')[0][0]
    if book.get_metadata('DC', 'creator'):
        author = book.get_metadata('DC', 'creator')[0][0]
    
    # Fallback to filename if no title
    if not book_title:
        book_title = file_path.stem
    
    # Extract chapters using spine
    chapters = []
    full_text_parts = []
    
    # Get spine items (reading order)
    spine_items = book.spine
    
    for item_id, _ in spine_items:
        item = book.get_item_with_id(item_id)
        if item is None:
            continue
        
        # Get content
        content = item.get_content()
        if content is None:
            continue
        
        # Convert to text
        try:
            text = html_to_text(content.decode('utf-8'))
        except UnicodeDecodeError:
            try:
                text = html_to_text(content.decode('latin-1'))
            except Exception as e:
                logger.warning(f"Failed to decode item {item_id}: {e}")
                continue
        
        if not text.strip():
            continue
        
        # Try to extract chapter title from text (first line or heading)
        chapter_title = None
        lines = text.split('\n')
        if lines:
            first_line = lines[0].strip()
            # Check if first line looks like a chapter title
            if (len(first_line) < 100 and 
                (first_line.lower().startswith('chapter') or 
                 first_line.isupper() or
                 re.match(r'^(Chapter|CHAPTER)\s+\d+', first_line, re.IGNORECASE))):
                chapter_title = first_line
            else:
                # Try to find a heading in the HTML
                soup = BeautifulSoup(content, 'html.parser')
                heading = soup.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                if heading:
                    chapter_title = heading.get_text().strip()
        
        # Fallback chapter title
        if not chapter_title:
            chapter_title = f"Chapter {len(chapters) + 1}"
        
        chapters.append((chapter_title, text))
        full_text_parts.append(text)
    
    # If no chapters found via spine, try to use all items
    if not chapters:
        logger.warning(f"No chapters found via spine for {file_path}, trying all items")
        item_index = 0
        for item_id, item in book.items:
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                content = item.get_content()
                if content:
                    try:
                        text = html_to_text(content.decode('utf-8'))
                        if text.strip():
                            chapter_title = f"Chapter {item_index + 1}"
                            chapters.append((chapter_title, text))
                            full_text_parts.append(text)
                            item_index += 1
                    except Exception as e:
                        logger.warning(f"Failed to process item {item_id}: {e}")
                        continue
    
    full_text = "\n\n".join(full_text_parts)
    
    return book_title, author, full_text, chapters
