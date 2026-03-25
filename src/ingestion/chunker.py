"""
RegulatorAI - Document Chunker
================================
Splits parsed documents into chunks optimized for RAG retrieval.

Key design decisions:
- Section-aware chunking: respects document structure instead of blind splitting
- Rich metadata per chunk: enables filtering by regulator, topic, date, section
- Overlap between chunks: prevents losing context at chunk boundaries
- Token-aware sizing: uses tiktoken to ensure chunks fit embedding model limits

Usage:
    from src.ingestion.chunker import chunk_all_documents
    chunks = chunk_all_documents()
"""

import json
import hashlib
from pathlib import Path

import tiktoken
from loguru import logger

from src.config import settings, PROCESSED_DATA_DIR, ROOT_DIR


# ── Token Counter ──────────────────────────────────────

_encoder = tiktoken.encoding_for_model("gpt-4o-mini")


def count_tokens(text: str) -> int:
    """Count tokens using the tiktoken encoder."""
    return len(_encoder.encode(text))


# ── Chunk ID Generator ─────────────────────────────────

def generate_chunk_id(doc_id: str, chunk_index: int, text: str) -> str:
    """Generate a deterministic, unique chunk ID."""
    content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
    return f"{doc_id}__chunk_{chunk_index:03d}_{content_hash}"


# ── Text Splitter ──────────────────────────────────────

def split_text_with_overlap(
    text: str,
    chunk_size: int = settings.CHUNK_SIZE,
    chunk_overlap: int = settings.CHUNK_OVERLAP,
) -> list[str]:
    """
    Split text into chunks at paragraph/sentence boundaries with overlap.

    Prefers splitting at:
    1. Double newlines (paragraph boundaries)
    2. Single newlines (line breaks)
    3. Sentence endings (. followed by space)
    4. Hard cut at chunk_size (last resort)
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            # Last chunk - take everything remaining
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        # Find the best split point before `end`
        chunk_text = text[start:end]

        # Priority 1: paragraph break
        split_pos = chunk_text.rfind("\n\n")

        # Priority 2: line break
        if split_pos == -1 or split_pos < chunk_size * 0.3:
            alt_pos = chunk_text.rfind("\n")
            if alt_pos > chunk_size * 0.3:
                split_pos = alt_pos

        # Priority 3: sentence boundary
        if split_pos == -1 or split_pos < chunk_size * 0.3:
            alt_pos = chunk_text.rfind(". ")
            if alt_pos > chunk_size * 0.3:
                split_pos = alt_pos + 1  # include the period

        # Priority 4: hard cut
        if split_pos == -1 or split_pos < chunk_size * 0.3:
            split_pos = chunk_size

        chunk = text[start : start + split_pos].strip()
        if chunk:
            chunks.append(chunk)

        # Move start with overlap
        start = start + split_pos - chunk_overlap

        # Ensure we make progress
        if start <= (start - split_pos + chunk_overlap):
            start = start + split_pos

    return chunks


# ── Section-Aware Chunker ──────────────────────────────

def chunk_document(parsed_doc: dict) -> list[dict]:
    """
    Chunk a single parsed document into retrieval-ready pieces.

    Strategy:
    - If document has meaningful sections, chunk within each section
    - Each chunk gets rich metadata for filtering
    - Small sections are kept whole (no splitting if under chunk_size)
    - Large sections are split with overlap

    Returns list of chunk dicts:
        {
            "chunk_id": "rbi-kyc-2016__chunk_001_a1b2c3d4",
            "doc_id": "rbi-kyc-master-direction-2016",
            "title": "Master Direction - KYC Direction, 2016",
            "regulator": "RBI",
            "topic": "kyc_aml",
            "doc_type": "master_direction",
            "date": "2016-02-25",
            "section_title": "Chapter III: CDD Procedure",
            "chunk_index": 3,
            "total_chunks": 45,
            "text": "...",
            "char_count": 980,
            "token_count": 245,
        }
    """
    doc_id = parsed_doc["id"]
    sections = parsed_doc.get("sections", [])

    # Base metadata shared by all chunks from this document
    base_metadata = {
        "doc_id": doc_id,
        "title": parsed_doc["title"],
        "regulator": parsed_doc["regulator"],
        "topic": parsed_doc["topic"],
        "doc_type": parsed_doc["doc_type"],
        "date": parsed_doc["date"],
    }

    all_chunks = []
    chunk_index = 0

    for section in sections:
        section_title = section.get("title", "Untitled Section")
        section_text = section.get("content", "").strip()

        if not section_text:
            continue

        # Add section title as context prefix
        contextualized_text = f"[{parsed_doc['title']} | {section_title}]\n\n{section_text}"

        # Split if section is too large, otherwise keep whole
        if len(section_text) <= settings.CHUNK_SIZE:
            text_chunks = [contextualized_text]
        else:
            raw_chunks = split_text_with_overlap(section_text)
            # Add context prefix to each sub-chunk
            text_chunks = [
                f"[{parsed_doc['title']} | {section_title} (Part {i + 1})]\n\n{chunk}"
                for i, chunk in enumerate(raw_chunks)
            ]

        for text in text_chunks:
            chunk = {
                **base_metadata,
                "chunk_id": generate_chunk_id(doc_id, chunk_index, text),
                "section_title": section_title,
                "chunk_index": chunk_index,
                "text": text,
                "char_count": len(text),
                "token_count": count_tokens(text),
            }
            all_chunks.append(chunk)
            chunk_index += 1

    # Add total_chunks count to each chunk
    for chunk in all_chunks:
        chunk["total_chunks"] = len(all_chunks)

    logger.info(
        f"Chunked {doc_id}: {len(all_chunks)} chunks, "
        f"avg {sum(c['token_count'] for c in all_chunks) // max(len(all_chunks), 1)} tokens/chunk"
    )

    return all_chunks


# ── Batch Chunker ──────────────────────────────────────

def chunk_all_documents(topic: str | None = None) -> list[dict]:
    """
    Chunk all parsed documents in data/processed/.

    Args:
        topic: Optional filter by topic

    Returns:
        List of all chunks across all documents
    """
    # Load parsed documents
    parsed_files = list(PROCESSED_DATA_DIR.glob("*.json"))
    parsed_files = [f for f in parsed_files if not f.name.startswith("_")]

    logger.info(f"Found {len(parsed_files)} parsed documents in {PROCESSED_DATA_DIR}")

    all_chunks = []

    for parsed_file in sorted(parsed_files):
        with open(parsed_file) as f:
            parsed_doc = json.load(f)

        # Filter by topic if specified
        if topic and parsed_doc.get("topic") != topic:
            continue

        chunks = chunk_document(parsed_doc)
        all_chunks.extend(chunks)

    # Save all chunks to a single file for the embedder
    chunks_output_path = PROCESSED_DATA_DIR / "_all_chunks.json"
    with open(chunks_output_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)

    # Save chunk summary
    summary = {
        "total_chunks": len(all_chunks),
        "total_tokens": sum(c["token_count"] for c in all_chunks),
        "avg_tokens_per_chunk": sum(c["token_count"] for c in all_chunks) // max(len(all_chunks), 1),
        "by_topic": {},
        "by_regulator": {},
        "by_doc": {},
    }

    for chunk in all_chunks:
        topic_key = chunk["topic"]
        reg_key = chunk["regulator"]
        doc_key = chunk["doc_id"]

        summary["by_topic"][topic_key] = summary["by_topic"].get(topic_key, 0) + 1
        summary["by_regulator"][reg_key] = summary["by_regulator"].get(reg_key, 0) + 1
        summary["by_doc"][doc_key] = summary["by_doc"].get(doc_key, 0) + 1

    summary_path = PROCESSED_DATA_DIR / "_chunk_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(
        f"Chunking complete: {summary['total_chunks']} chunks, "
        f"{summary['total_tokens']} total tokens, "
        f"{summary['avg_tokens_per_chunk']} avg tokens/chunk"
    )
    logger.info(f"Chunks by topic: {summary['by_topic']}")
    logger.info(f"All chunks saved to {chunks_output_path}")

    return all_chunks


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Chunk parsed regulatory documents")
    parser.add_argument("--topic", type=str, help="Filter by topic")
    args = parser.parse_args()

    logger.add(ROOT_DIR / "logs" / "chunker.log", rotation="10 MB", level=settings.LOG_LEVEL)
    chunk_all_documents(topic=args.topic)