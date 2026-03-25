"""
RegulatorAI - Document Scraper
===============================
Downloads regulatory documents from RBI/SEBI based on the document registry.
Handles PDF downloads and HTML page saves with retry logic and rate limiting.

Usage:
    python -m src.ingestion.scraper                    # Download all
    python -m src.ingestion.scraper --topic kyc_aml    # Download by topic
    python -m src.ingestion.scraper --id rbi-kyc-2016  # Download specific doc
"""

import json
import time
from pathlib import Path

import httpx
from loguru import logger
from tqdm import tqdm

from src.config import settings, RAW_DATA_DIR, ROOT_DIR


# ── Constants ──────────────────────────────────────────

REGISTRY_PATH = ROOT_DIR / "data" / "document_registry.json"
REQUEST_TIMEOUT = 60  # seconds
RETRY_COUNT = 3
RETRY_DELAY = 5  # seconds between retries
RATE_LIMIT_DELAY = 2  # seconds between downloads (be polite to gov servers)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── Registry ───────────────────────────────────────────

def load_registry() -> list[dict]:
    """Load the document registry JSON."""
    with open(REGISTRY_PATH) as f:
        data = json.load(f)
    return data["documents"]


def filter_registry(
    documents: list[dict],
    topic: str | None = None,
    doc_id: str | None = None,
    regulator: str | None = None,
) -> list[dict]:
    """Filter documents by topic, ID, or regulator."""
    filtered = documents

    if doc_id:
        filtered = [d for d in filtered if d["id"] == doc_id]
    if topic:
        filtered = [d for d in filtered if d["topic"] == topic]
    if regulator:
        filtered = [d for d in filtered if d["regulator"].upper() == regulator.upper()]

    return filtered


# ── Download Logic ─────────────────────────────────────

def get_output_path(doc: dict) -> Path:
    """Determine save path based on regulator and document ID."""
    regulator_dir = RAW_DATA_DIR / doc["regulator"].lower()
    regulator_dir.mkdir(parents=True, exist_ok=True)

    # Determine file extension from URL
    url = doc["url"].lower()
    if url.endswith(".pdf"):
        ext = ".pdf"
    elif url.endswith(".html") or url.endswith(".htm"):
        ext = ".html"
    else:
        # SEBI master circulars are HTML pages
        ext = ".html" if "sebi.gov.in" in url and ".pdf" not in url else ".pdf"

    return regulator_dir / f"{doc['id']}{ext}"


def download_document(doc: dict, client: httpx.Client) -> dict:
    """
    Download a single document with retry logic.

    Returns a status dict:
        {"id": ..., "status": "success"|"skipped"|"failed", "path": ..., "error": ...}
    """
    output_path = get_output_path(doc)

    # Skip if already downloaded
    if output_path.exists() and output_path.stat().st_size > 0:
        logger.info(f"Skipping {doc['id']} — already exists at {output_path}")
        return {"id": doc["id"], "status": "skipped", "path": str(output_path)}

    url = doc["url"]

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            logger.info(f"Downloading {doc['id']} (attempt {attempt}/{RETRY_COUNT})")
            logger.debug(f"  URL: {url}")

            response = client.get(url, follow_redirects=True, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            # Write content
            mode = "wb" if output_path.suffix == ".pdf" else "w"
            if mode == "wb":
                output_path.write_bytes(response.content)
            else:
                output_path.write_text(response.text, encoding="utf-8")

            size_kb = output_path.stat().st_size / 1024
            logger.success(f"Downloaded {doc['id']} ({size_kb:.1f} KB) → {output_path}")
            return {"id": doc["id"], "status": "success", "path": str(output_path)}

        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP {e.response.status_code} for {doc['id']} (attempt {attempt})")
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY)
        except httpx.TimeoutException:
            logger.warning(f"Timeout for {doc['id']} (attempt {attempt})")
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"Unexpected error for {doc['id']}: {e}")
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY)

    return {"id": doc["id"], "status": "failed", "error": "Max retries exceeded"}


# ── Main Pipeline ──────────────────────────────────────

def scrape_documents(
    topic: str | None = None,
    doc_id: str | None = None,
    regulator: str | None = None,
) -> list[dict]:
    """
    Download documents from the registry.

    Args:
        topic: Filter by topic (e.g., "digital_lending", "kyc_aml")
        doc_id: Download a specific document by ID
        regulator: Filter by regulator ("RBI" or "SEBI")

    Returns:
        List of status dicts for each document
    """
    documents = load_registry()
    documents = filter_registry(documents, topic=topic, doc_id=doc_id, regulator=regulator)

    if not documents:
        logger.warning("No documents matched the given filters.")
        return []

    logger.info(f"Found {len(documents)} documents to process")

    results = []
    with httpx.Client(headers=HEADERS) as client:
        for doc in tqdm(documents, desc="Downloading documents"):
            result = download_document(doc, client)
            results.append(result)
            # Rate limiting — be polite to government servers
            time.sleep(RATE_LIMIT_DELAY)

    # Summary
    success = sum(1 for r in results if r["status"] == "success")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")
    logger.info(f"Done: {success} downloaded, {skipped} skipped, {failed} failed")

    if failed > 0:
        for r in results:
            if r["status"] == "failed":
                logger.error(f"  Failed: {r['id']} — {r.get('error', 'unknown')}")

    return results


# ── CLI Entry Point ────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Download RBI/SEBI regulatory documents")
    parser.add_argument("--topic", type=str, help="Filter by topic (e.g., digital_lending)")
    parser.add_argument("--id", type=str, dest="doc_id", help="Download specific document by ID")
    parser.add_argument("--regulator", type=str, help="Filter by regulator (RBI or SEBI)")
    args = parser.parse_args()

    # Configure logging
    logger.add(ROOT_DIR / "logs" / "scraper.log", rotation="10 MB", level=settings.LOG_LEVEL)

    results = scrape_documents(
        topic=args.topic,
        doc_id=args.doc_id,
        regulator=args.regulator,
    )

    return results


if __name__ == "__main__":
    main()