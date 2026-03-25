"""
RegulatorAI - Ingestion Pipeline Runner
=========================================
One command to run the full ingestion pipeline.

Usage:
    python scripts/ingest.py                        # Full pipeline, all docs
    python scripts/ingest.py --topic kyc_aml        # Specific topic
    python scripts/ingest.py --step scrape          # Only scrape
    python scripts/ingest.py --step scrape --topic digital_lending
"""

import argparse
from loguru import logger

from src.config import settings, ROOT_DIR
from src.ingestion.scraper import scrape_documents
from src.ingestion.parser import parse_all_documents
from src.ingestion.chunker import chunk_all_documents
from src.ingestion.embedder import embed_all_chunks


def run_pipeline(step: str | None = None, topic: str | None = None):
    """Run the ingestion pipeline (or a specific step)."""

    steps_to_run = ["scrape", "parse", "chunk", "embed"] if step is None else [step]

    logger.info(f"Starting ingestion pipeline: steps={steps_to_run}, topic={topic or 'all'}")

    # ── Step 1: Scrape ──
    if "scrape" in steps_to_run:
        logger.info("=" * 50)
        logger.info("STEP 1: Scraping documents")
        logger.info("=" * 50)
        results = scrape_documents(topic=topic)

        failed = [r for r in results if r["status"] == "failed"]
        if failed:
            logger.warning(f"{len(failed)} documents failed to download. Check logs.")

    # ── Step 2: Parse (coming next) ──
    if "parse" in steps_to_run:
        logger.info("=" * 50)
        logger.info("STEP 2: Parsing documents")
        logger.info("=" * 50)
        parsed_docs = parse_all_documents(topic=topic)
        logger.info(f"Parsed {len(parsed_docs)} documents")

    # ── Step 3: Chunk (coming next) ──
    if "chunk" in steps_to_run:
        logger.info("=" * 50)
        logger.info("STEP 3: Chunking documents")
        logger.info("=" * 50)
        chunks = chunk_all_documents(topic=topic)
        logger.info(f"Generated {len(chunks)} chunks")

    # ── Step 4: Embed (coming next) ──
    if "embed" in steps_to_run:
        logger.info("=" * 50)
        logger.info("STEP 4: Embedding and storing in vector DB")
        logger.info("=" * 50)
        total = embed_all_chunks(topic=topic)
        logger.info(f"Embedded {total} chunks into ChromaDB")

    logger.success("Pipeline complete.")


def main():
    parser = argparse.ArgumentParser(description="Run the RegulatorAI ingestion pipeline")
    parser.add_argument(
        "--step",
        type=str,
        choices=["scrape", "parse", "chunk", "embed"],
        help="Run a specific step only",
    )
    parser.add_argument("--topic", type=str, help="Filter by topic")
    args = parser.parse_args()

    # Logging
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(log_dir / "ingestion.log", rotation="10 MB", level=settings.LOG_LEVEL)

    run_pipeline(step=args.step, topic=args.topic)


if __name__ == "__main__":
    main()