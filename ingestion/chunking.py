"""Token-based chunking utilities."""
import os
from typing import List

import tiktoken

from shared.cache import clear_cache, get_cache_value, set_cache_value

# Initialize tokenizer (using cl100k_base for GPT models, good general purpose)
_TOKENIZER_CACHE_KEY = "ingestion_tokenizer"


class _DummyTokenizer:
    def encode(self, text: str):
        return text.split()

    def decode(self, tokens: list[str]) -> str:
        return " ".join(tokens)


def get_tokenizer():
    """Get or create tokenizer instance."""
    cached = get_cache_value(_TOKENIZER_CACHE_KEY, lambda: None)
    if cached is not None:
        return cached
    if os.environ.get("STORYTELLER_DUMMY_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes"):
        return set_cache_value(_TOKENIZER_CACHE_KEY, _DummyTokenizer())
    return set_cache_value(_TOKENIZER_CACHE_KEY, tiktoken.get_encoding("cl100k_base"))


def count_tokens(text: str) -> int:
    """Count tokens in text."""
    return len(get_tokenizer().encode(text))


def chunk_text_by_tokens(text: str, target_tokens: int = 600, overlap_percent: float = 0.1) -> List[str]:
    """Chunk text by token count with overlap.
    
    Args:
        text: Text to chunk
        target_tokens: Target number of tokens per chunk
        overlap_percent: Percentage of overlap between chunks (0.0 to 1.0)
    
    Returns:
        List of text chunks
    """
    tokenizer = get_tokenizer()
    tokens = tokenizer.encode(text)
    
    if len(tokens) <= target_tokens:
        return [text]
    
    overlap_tokens = int(target_tokens * overlap_percent)
    chunks = []
    start = 0
    
    while start < len(tokens):
        end = start + target_tokens
        chunk_tokens = tokens[start:end]
        chunk_text = tokenizer.decode(chunk_tokens)
        chunks.append(chunk_text)
        
        # Move start forward by (target - overlap) to create overlap
        start += target_tokens - overlap_tokens
        
        # Prevent infinite loop
        if start >= len(tokens):
            break
    
    return chunks


def chunk_text_smart(text: str, target_tokens: int = 600, overlap_percent: float = 0.1) -> List[str]:
    """Chunk text intelligently, trying to break at paragraph boundaries.
    
    Args:
        text: Text to chunk
        target_tokens: Target number of tokens per chunk
        overlap_percent: Percentage of overlap between chunks
    
    Returns:
        List of text chunks
    """
    # First, try to chunk by paragraphs
    paragraphs = text.split("\n\n")
    
    if not paragraphs:
        return chunk_text_by_tokens(text, target_tokens, overlap_percent)
    
    chunks = []
    current_chunk = ""
    current_tokens = 0
    target = target_tokens
    overlap = int(target_tokens * overlap_percent)
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        para_tokens = count_tokens(para)
        
        # If paragraph itself is too large, chunk it directly
        if para_tokens > target:
            # Finalize current chunk if any
            if current_chunk:
                chunks.append(current_chunk.strip())
                # Start new chunk with overlap
                if overlap > 0:
                    # Get last overlap_tokens from current chunk
                    overlap_text = get_overlap_text(current_chunk, overlap)
                    current_chunk = overlap_text + "\n\n" + para
                    current_tokens = count_tokens(current_chunk)
                else:
                    current_chunk = para
                    current_tokens = para_tokens
            else:
                # Chunk the large paragraph directly
                sub_chunks = chunk_text_by_tokens(para, target, overlap_percent)
                chunks.extend(sub_chunks[:-1])  # Add all but last
                current_chunk = sub_chunks[-1]  # Keep last as start of next
                current_tokens = count_tokens(current_chunk)
            continue
        
        # Check if adding this paragraph would exceed target
        new_tokens = current_tokens + para_tokens + 2  # +2 for "\n\n"
        
        if new_tokens > target and current_chunk:
            # Finalize current chunk
            chunks.append(current_chunk.strip())
            # Start new chunk with overlap
            if overlap > 0:
                overlap_text = get_overlap_text(current_chunk, overlap)
                current_chunk = overlap_text + "\n\n" + para
            else:
                current_chunk = para
            current_tokens = count_tokens(current_chunk)
        else:
            # Add paragraph to current chunk
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
            current_tokens = count_tokens(current_chunk)
    
    # Add final chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [text]


def get_overlap_text(text: str, overlap_tokens: int) -> str:
    """Get the last N tokens of text as overlap."""
    tokenizer = get_tokenizer()
    tokens = tokenizer.encode(text)
    if len(tokens) <= overlap_tokens:
        return text
    overlap_tokens_list = tokens[-overlap_tokens:]
    return tokenizer.decode(overlap_tokens_list)


def clear_tokenizer_cache() -> None:
    """Clear cached tokenizer (useful for tests)."""
    clear_cache(_TOKENIZER_CACHE_KEY)
