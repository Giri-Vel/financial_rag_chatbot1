"""
RegulatorAI - Document Parser
==============================
Extracts text from raw PDFs and HTML files downloaded by the scraper.
Outputs structured JSON with text content + metadata for each document.

Handles:
- PDF extraction via PyMuPDF (fast, handles most RBI PDFs well)
- HTML extraction via BeautifulSoup (for RBI web pages)
- Metadata preservation (title, regulator, topic, date, sections)

Usage:
    from src.ingestion.parser import parse_all_documents
    documents = parse_all_documents()
"""

import json
import re
from pathlib import Path

import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from loguru import logger

from src.config import RAW_DATA_DIR, PROCESSED_DATA_DIR, ROOT_DIR


REGISTRY_PATH = ROOT_DIR / "data" / "document_registry.json"


# ── Registry Loader ───────────────────────────────────

def load_registry() -> list[dict]:
    with open(REGISTRY_PATH) as f:
        data = json.load(f)
    return data["documents"]


def get_registry_metadata(doc_id: str, registry: list[dict]) -> dict | None:
    """Look up metadata for a document ID from the registry."""
    for doc in registry:
        if doc["id"] == doc_id:
            return doc
    return None


# ── Text Cleaning ──────────────────────────────────────

def clean_text(text: str) -> str:
    """Clean extracted text while preserving meaningful structure."""
    # Normalize unicode whitespace
    text = text.replace("\xa0", " ")
    text = text.replace("\u200b", "")

    # Fix hyphenated line breaks (e.g., "regu-\nlation" -> "regulation")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Collapse multiple blank lines into max two
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove excessive spaces (but keep single newlines)
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Strip lines that are just whitespace
    lines = text.split("\n")
    lines = [line.rstrip() for line in lines]
    text = "\n".join(lines)

    return text.strip()


def extract_sections(text: str) -> list[dict]:
    """
    Attempt to extract section structure from regulatory documents.
    RBI docs typically use patterns like:
      - "Section 1.", "Section 2."
      - "Chapter I", "Chapter II"
      - Numbered paragraphs: "1.", "2.", "3."
      - Lettered subsections: "(a)", "(b)", "(i)", "(ii)"
    """
    sections = []

    # Pattern for major section headers in RBI documents
    section_patterns = [
        r"^(Chapter\s+[IVXLC]+[.:]\s*.+)$",
        r"^(Section\s+\d+[.:]\s*.+)$",
        r"^(CHAPTER\s+[IVXLC]+[.:]\s*.+)$",
        r"^(\d+\.\s+[A-Z][A-Za-z\s]+)$",
    ]

    combined_pattern = "|".join(f"({p})" for p in section_patterns)

    current_section = {"title": "Preamble", "content": "", "start_idx": 0}

    for i, line in enumerate(text.split("\n")):
        match = re.match(combined_pattern, line.strip(), re.MULTILINE)
        if match:
            # Save previous section
            if current_section["content"].strip():
                sections.append(current_section.copy())

            current_section = {
                "title": line.strip(),
                "content": "",
                "start_idx": i,
            }
        else:
            current_section["content"] += line + "\n"

    # Append last section
    if current_section["content"].strip():
        sections.append(current_section)

    return sections if sections else [{"title": "Full Document", "content": text, "start_idx": 0}]


# ── PDF Parser ─────────────────────────────────────────

def parse_pdf(file_path: Path) -> str:
    """Extract text from a PDF using PyMuPDF."""
    try:
        doc = fitz.open(str(file_path))
        text_parts = []

        for page_num, page in enumerate(doc):
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")

        doc.close()

        full_text = "\n\n".join(text_parts)
        return clean_text(full_text)

    except Exception as e:
        logger.error(f"Failed to parse PDF {file_path}: {e}")
        return ""


# ── HTML Parser ────────────────────────────────────────

def parse_html(file_path: Path) -> str:
    """Extract text from an HTML file, focusing on main content."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(content, "lxml")

        # Remove script, style, nav, footer elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try to find the main content area
        # RBI pages typically use specific div IDs/classes
        main_content = None
        for selector in [
            "#divContent",           # Common RBI content div
            "#ctl00_ContentPlaceHolder1_lblContent",  # RBI notification pages
            ".tablebg",              # RBI master direction pages
            "#maincontent",
            "article",
            "main",
            ".content",
        ]:
            main_content = soup.select_one(selector)
            if main_content:
                break

        if main_content:
            text = main_content.get_text(separator="\n")
        else:
            # Fallback: use body text
            body = soup.find("body")
            text = body.get_text(separator="\n") if body else soup.get_text(separator="\n")

        return clean_text(text)

    except Exception as e:
        logger.error(f"Failed to parse HTML {file_path}: {e}")
        return ""


# ── Main Parse Function ───────────────────────────────

def parse_document(file_path: Path, metadata: dict) -> dict | None:
    """
    Parse a single document and return structured output.

    Returns:
        {
            "id": "rbi-kyc-master-direction-2016",
            "title": "Master Direction - KYC Direction, 2016",
            "regulator": "RBI",
            "topic": "kyc_aml",
            "doc_type": "master_direction",
            "date": "2016-02-25",
            "source_file": "data/raw/rbi/rbi-kyc-master-direction-2016.pdf",
            "full_text": "...",
            "sections": [...],
            "char_count": 45230,
            "word_count": 7105,
        }
    """
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        text = parse_pdf(file_path)
    elif suffix in (".html", ".htm"):
        text = parse_html(file_path)
    else:
        logger.warning(f"Unsupported file type: {suffix} for {file_path}")
        return None

    if not text or len(text) < 100:
        logger.warning(f"Extracted text too short ({len(text)} chars) for {file_path}")
        return None

    sections = extract_sections(text)

    parsed = {
        "id": metadata.get("id", file_path.stem),
        "title": metadata.get("title", file_path.stem),
        "regulator": metadata.get("regulator", "unknown"),
        "topic": metadata.get("topic", "unknown"),
        "doc_type": metadata.get("doc_type", "unknown"),
        "date": metadata.get("date", "unknown"),
        "source_file": str(file_path.relative_to(ROOT_DIR)),
        "full_text": text,
        "sections": sections,
        "char_count": len(text),
        "word_count": len(text.split()),
    }

    logger.info(
        f"Parsed {parsed['id']}: {parsed['char_count']} chars, "
        f"{parsed['word_count']} words, {len(sections)} sections"
    )

    return parsed


# ── Batch Parse ────────────────────────────────────────

def parse_all_documents(topic: str | None = None) -> list[dict]:
    """
    Parse all downloaded documents in data/raw/.

    Args:
        topic: Optional filter by topic

    Returns:
        List of parsed document dicts
    """
    registry = load_registry()
    parsed_docs = []

    # Find all files in raw directory
    raw_files = list(RAW_DATA_DIR.rglob("*.*"))
    raw_files = [f for f in raw_files if f.suffix.lower() in (".pdf", ".html", ".htm")]

    logger.info(f"Found {len(raw_files)} files in {RAW_DATA_DIR}")

    for file_path in sorted(raw_files):
        # Match file to registry entry by stem (filename without extension)
        doc_id = file_path.stem
        metadata = get_registry_metadata(doc_id, registry)

        if metadata is None:
            logger.warning(f"No registry entry for {doc_id}, using filename as metadata")
            metadata = {"id": doc_id}

        # Filter by topic if specified
        if topic and metadata.get("topic") != topic:
            continue

        parsed = parse_document(file_path, metadata)
        if parsed:
            parsed_docs.append(parsed)

            # Save individual parsed doc to processed/
            output_path = PROCESSED_DATA_DIR / f"{parsed['id']}.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved parsed doc to {output_path}")

    logger.info(f"Successfully parsed {len(parsed_docs)}/{len(raw_files)} documents")

    # Save summary
    summary = {
        "total_documents": len(parsed_docs),
        "total_chars": sum(d["char_count"] for d in parsed_docs),
        "total_words": sum(d["word_count"] for d in parsed_docs),
        "documents": [
            {
                "id": d["id"],
                "title": d["title"],
                "topic": d["topic"],
                "chars": d["char_count"],
                "words": d["word_count"],
                "sections": len(d["sections"]),
            }
            for d in parsed_docs
        ],
    }
    summary_path = PROCESSED_DATA_DIR / "_parse_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Parse summary saved to {summary_path}")

    return parsed_docs


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse downloaded regulatory documents")
    parser.add_argument("--topic", type=str, help="Filter by topic")
    args = parser.parse_args()

    from src.config import settings

    logger.add(ROOT_DIR / "logs" / "parser.log", rotation="10 MB", level=settings.LOG_LEVEL)
    parse_all_documents(topic=args.topic)