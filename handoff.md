# RegulatorAI — Session Handoff (March 29, 2026)

## What Was Done This Session

### FastAPI Backend (src/api/)
Built a clean API layer between the Streamlit frontend and the RAG chain. Four files:

- main.py — FastAPI app with lifespan that initializes RAGChain once at startup. CORS configured for Streamlit on port 8501. All routes under /api/v1/.
- routes.py — Four endpoints: POST /query (main RAG endpoint), GET /health (collection stats for monitoring/AWS health checks), GET /topics (topic list with chunk counts), GET /documents (full knowledge base inventory with per-document chunk counts).
- models.py — Pydantic request/response schemas for all endpoints.
- __init__.py — empty.

All four endpoints tested and returning 200. The RAG chain initializes once and is shared across requests via a module-level reference set during startup.

### Streamlit Frontend (ui/app.py)
Went through multiple iterations fighting Streamlit 1.55.0 rendering quirks. Final version:

- WhatsApp-style chat bubbles — user messages right-aligned (green-tinted), assistant messages left-aligned (darker background). No avatars at all.
- All messages rendered as custom HTML divs, not st.chat_message() — this was necessary because Streamlit 1.55.0 has broken avatar rendering (garbled "rt" and "ac" text instead of icons).
- Sources displayed using HTML details/summary tags instead of st.expander() — the expander was also rendering garbled icons in 1.55.0.
- Two-phase message flow: user types -> message appears immediately + "Querying regulatory documents..." loading bubble -> API response replaces loading bubble. Uses st.session_state.pending_query flag and st.rerun() to manage the two-phase render.
- Topic dropdown shows document counts ("Digital Lending (3 docs)") not chunk counts.
- top_k hardcoded to 5 — conscious decision to simplify UI, can be exposed later.
- layout="wide" with max-width: 900px CSS so it's responsive but bounded.
- API base URL reads from API_BASE_URL env var (for Docker), falls back to localhost:8000 for local dev.
- Green terminal aesthetic with Share Tech Mono + IBM Plex Mono fonts. Minimal CSS — only custom classes for headers/labels/bubbles, no aggressive Streamlit override hacks.

### Docker Setup
Two-container architecture via docker-compose:

- Dockerfile.api — Python 3.11-slim, copies full src/ before pip install (important: copying just src/__init__.py first causes exit code 2 because setuptools needs the full package). Runs uvicorn on port 8000.
- Dockerfile.ui — Python 3.11-slim, only installs streamlit + requests (not the full RAG stack). Runs streamlit on port 8501. Streamlit config baked in (headless, dark theme, no telemetry).
- docker-compose.yml — API container has health check (curl /api/v1/health), UI container depends_on api with condition: service_healthy. ChromaDB data mounted as volume (./data/chromadb:/app/data/chromadb). .env passed via env_file (never baked into image). UI gets API_BASE_URL=http://api:8000/api/v1 for Docker internal DNS.
- .dockerignore — excludes .git, .venv, data dirs, .env, markdown files.
- Docker Desktop must be manually launched on Mac before docker compose up --build.

### Git
Pushed to GitHub: .gitignore updated with Docker and env file patterns, .env.example created with placeholder key, all new files committed and pushed to main.


## Caveats and Known Issues

- Streamlit 1.55.0 has broken rendering for st.chat_message() avatars and st.expander() icons. We work around both with custom HTML. If Streamlit updates and fixes these, the workarounds can be simplified.
- The sidebar was completely removed because it kept disappearing and couldn't be reliably toggled back. All controls are inline above the chat now.
- Markdown-to-HTML conversion in the assistant bubbles is basic (bold, code, unordered lists only). Numbered lists, headers, tables from LLM responses may not render perfectly. Could improve the converter or use a library like markdown2.
- The loading bubble ("Querying regulatory documents...") renders but doesn't animate. It's a static HTML div, not a Streamlit spinner. Works fine functionally.
- SEBI documents still not ingested — only RBI covered.
- 2 of the 10 RBI HTML documents failed parsing (JavaScript-rendered pages: rbi-kyc-master-direction-html, rbi-ppi-master-direction-html). Content is covered by their PDF versions so not critical.


## What's Next (Priority Order)

### 1. AWS EC2 Deployment
- Region: ap-south-1 (Mumbai)
- IAM user: giriiam1 (has AdministratorAccess)
- Plan: EC2 instance (t2.micro or t3.small), run docker compose on it
- Need to handle: security groups (open 8501 for UI, 8000 for API or keep internal), .env file on the instance, pulling code from GitHub, SSL/domain if we want it polished
- S3 for raw document storage (optional, docs are small)

### 2. README and Portfolio Polish
- Architecture diagram showing the full pipeline: docs -> scraper -> parser -> chunker -> embedder -> ChromaDB -> FastAPI -> Streamlit
- Screenshots of the working UI with a real query
- Demo GIF
- Clear setup instructions (clone, .env, docker compose up)
- Tech stack badges

### 3. Evaluation Pipeline
- 20-30 manual Q&A pairs in data/eval/
- Metrics: retrieval accuracy (are the right chunks coming back?), answer quality (is the LLM using the context correctly?), citation accuracy
- Could use LLM-as-judge for automated eval

### 4. More Documents
- SEBI documents (not started)
- More RBI topics beyond digital_lending, kyc_aml, payment_systems

### 5. UI Polish (Lower Priority)
- Better markdown rendering in assistant bubbles
- Auto-scroll to bottom on new messages (JavaScript snippet)
- Mobile responsiveness
- Possibly bring back a sidebar or settings panel once Streamlit fixes their rendering bugs


## Project Structure (Current)
```
financial_rag_chatbot1/
├── data/
│   └── document_registry.json
├── scripts/
│   └── ingest.py
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── routes.py
│   │   └── models.py
│   ├── ingestion/
│   │   ├── scraper.py
│   │   ├── parser.py
│   │   ├── chunker.py
│   │   └── embedder.py
│   ├── retrieval/
│   │   └── vector_store.py
│   └── generation/
│       └── chain.py
├── ui/
│   └── app.py
├── Dockerfile.api
├── Dockerfile.ui
├── docker-compose.yml
├── .dockerignore
├── .env              (not in git)
├── .env.example
├── pyproject.toml
├── .gitignore
├── LICENSE
└── README.md
```

## Key Technical Decisions Log
- OpenAI gpt-4o-mini for generation, text-embedding-3-small for embeddings — cost negligible at this scale
- ChromaDB over Pinecone — local, free, no external dependency
- LangChain over LlamaIndex — more flexible for the RAG chain
- top_k=5 hardcoded in UI — removed from user controls to simplify, can revisit
- Two Docker containers over one — cleaner architecture, better for portfolio
- Custom HTML chat bubbles over st.chat_message() — forced by Streamlit 1.55.0 rendering bugs
- HTML details/summary over st.expander() — same reason
- No sidebar — kept disappearing, moved controls inline
- API_RELOAD=false in Docker, true for local dev