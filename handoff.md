# RegulatorAI — Project Handoff Document

## What This Is
A RAG-based chatbot for navigating Indian financial regulatory documents (RBI/SEBI). Portfolio project combining AI/LLM skills with AWS deployment, targeting Giri's career roadmap (Operation North Star).

## What's Been Built (Complete)

### Data Ingestion Pipeline (`scripts/ingest.py`)
All 4 steps working end-to-end:

1. **Scraper** (`src/ingestion/scraper.py`) — Downloads docs from curated registry. Uses mirror URLs to bypass RBI's bot protection (HTTP 418 on rbidocs.rbi.org.in). Sources: RBI commonman portal, DigiLocker, FIDC India, IREDA.

2. **Parser** (`src/ingestion/parser.py`) — Extracts text from PDFs (PyMuPDF) and HTML pages (BeautifulSoup). 8/10 docs parsed successfully. 2 JavaScript-rendered HTML pages failed (rbi-kyc-master-direction-html, rbi-ppi-master-direction-html) — not critical, content covered by PDF versions.

3. **Chunker** (`src/ingestion/chunker.py`) — Section-aware chunking with metadata. 600 chunks, ~229 avg tokens/chunk. Context prefix on each chunk for LLM awareness.

4. **Embedder** (`src/ingestion/embedder.py`) — OpenAI `text-embedding-3-small`, stored in ChromaDB (persistent, local). All 600 chunks embedded.

### RAG Generation Layer
- **Vector Store** (`src/retrieval/vector_store.py`) — ChromaDB wrapper with metadata filtering (topic, regulator, doc_type).
- **RAG Chain** (`src/generation/chain.py`) — Retrieval + LLM generation with citations. Uses `gpt-4o-mini`. Interactive CLI built in.

### Configuration
- `src/config.py` — pydantic-settings, all config from `.env`
- `pyproject.toml` — modern Python packaging, editable install (`pip install -e ".[dev]"`)
- `.env.example` — template for API keys
- `data/document_registry.json` — 10 curated RBI documents across 3 topics

### Document Coverage
- **Digital Lending**: 3 docs (2022 guidelines, 2025 directions, FAQ)
- **KYC/AML**: 4 docs (master direction, FAQ, V-CIP 2020, V-CIP 2021)
- **Payment Systems**: 1 doc (payment aggregator guidelines)
- All RBI. SEBI docs not yet added.

## Tech Stack
- **Framework**: LangChain + OpenAI (`gpt-4o-mini` for LLM, `text-embedding-3-small` for embeddings)
- **Vector DB**: ChromaDB (persistent, local)
- **PDF Processing**: PyMuPDF
- **HTML Processing**: BeautifulSoup + lxml
- **Config**: pydantic-settings
- **Python**: 3.11+

## Project Structure
```
financial_rag_chatbot1/
├── data/
│   └── document_registry.json    # URLs + metadata for all docs
├── scripts/
│   └── ingest.py                 # Pipeline runner (scrape/parse/chunk/embed)
├── src/
│   ├── config.py                 # Central config + prompt templates
│   ├── ingestion/
│   │   ├── scraper.py
│   │   ├── parser.py
│   │   ├── chunker.py
│   │   └── embedder.py
│   ├── retrieval/
│   │   └── vector_store.py
│   └── generation/
│       └── chain.py              # RAG chain + interactive CLI
├── pyproject.toml
├── .env                          # (not in git) OpenAI key
├── .env.example
└── .gitignore
```

## What's Next (In Priority Order)

### 1. Streamlit Frontend (`ui/app.py`)
- Chat interface with message history
- Topic filter sidebar (digital_lending, kyc_aml, payment_systems)
- Source citations displayed below answers
- Clean, professional look for portfolio demo

### 2. FastAPI Backend (`src/api/`)
- `main.py` — FastAPI app
- `routes.py` — POST /query endpoint
- `models.py` — Pydantic request/response schemas
- Separates frontend from RAG logic (shows architectural thinking)

### 3. Docker + AWS Deployment
- Dockerfile + docker-compose.yml
- Deploy on EC2 (t2.micro/t3.small, ap-south-1)
- S3 for raw document storage
- IAM roles (user: giriiam1, has AdministratorAccess)

### 4. Polish for Portfolio
- README with architecture diagram, screenshots, demo GIF
- Evaluation pipeline (20-30 manual Q&A pairs in data/eval/)
- Add more documents (SEBI, more RBI topics)
- Blog post: "Building a RAG Chatbot for Indian Financial Regulations"

## Key Decisions & Context
- OpenAI costs are negligible at this scale (~₹200-300/month total)
- Giri prefers natural conversational questions over structured prompt widgets
- Bot protection on rbidocs.rbi.org.in requires mirror URLs
- 2 HTML docs failed parsing (JS-rendered) — content already covered by PDFs
- AWS region: ap-south-1 (Mumbai) for low latency from Chennai
- Wedding: April 23, 2026. Phase 1 starts May 5, 2026.