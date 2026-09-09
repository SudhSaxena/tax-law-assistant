# Tax Law Assistant

A RAG (retrieval-augmented generation) system that answers US federal income
tax questions using IRS Publication 17 and select sections of the Internal
Revenue Code (Title 26), with grounded, cited answers — built as a hands-on
project to demonstrate RAG, evals, and production-engineering skills.

**Note:** this is a learning/portfolio project, not a tax advice product.
Every answer includes a disclaimer that it's general information only.

## What it does

- Answers tax questions by retrieving relevant excerpts from real source
  documents, then generating a grounded answer that cites its sources
- Prefers current-year figures over base statutory text for dollar amounts
  (statutes state pre-inflation-adjustment base amounts, which this system
  accounts for separately)
- Streams responses token-by-token
- Caches repeated/similar questions (embedding cache + semantic response cache)
- Tracks token usage and estimated cost per request
- Guards against off-topic questions and prompt injection attempts
- Logs structured, traceable request data

## Architecture

```
Ingestion (offline):
PDF/statute text -> chunking -> embeddings -> vector DB (Chroma)

Query (per request):
question -> normalize -> guardrail check
                              |
                    [cache hit?] --yes--> return cached answer
                              |
                              no
                              |
                          retrieve -> generate (Claude) -> ensure disclaimer -> cite -> answer
                                                                                    |
                                                                              store in cache
```

This is designed to scale to a much larger knowledge base with automated
ingestion and quality gating — see the roadmap below.

## Tech stack

- **LLM:** Claude Haiku 4.5 (Anthropic API)
- **Embeddings:** Voyage AI (`voyage-4-lite`)
- **Vector DB:** ChromaDB (local, persistent)
- **Backend:** FastAPI
- **Cache/usage tracking:** SQLite
- **Frontend:** React app (`web/`, primary UI — requires `npm install`),
  plus a plain HTML/JS fallback demo (`static-demo/`, no build step)

## Running it locally

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Create a `.env` file (see `.env.example`) with your API keys, then run the
data pipeline once to build the knowledge base (run from the project root):

```bash
python src/chunk_documents.py
python src/embed_chunks.py
python src/load_vector_db.py
```

Then start the API and open the frontend:

```bash
uvicorn api:app --reload --app-dir src
```

Open `static-demo/index.html` in a browser for the simple fallback UI, or run
the React app in `web/` (see its own setup instructions).

## Evaluation

25 hand-built eval questions, hybrid grading (deterministic checks for
numeric facts, LLM-judge for open-ended questions). Current baseline: **24/25
(96%)** — the one known failure is a documented, deliberately-deferred
retrieval gap (semantic search struggles with ID-style queries like "what is
Section 63 about"), a known limitation left as a deliberately-scoped roadmap item.

## Project structure

```
├── src/
│   ├── chunk_documents.py, embed_chunks.py, load_vector_db.py   # data pipeline
│   ├── retrieve.py, generate_answer.py                          # RAG core
│   ├── api.py                                                   # FastAPI backend
│   ├── cache.py, usage_tracker.py, guardrails.py,
│   │   query_normalizer.py, request_logger.py                   # production concerns
│   ├── eval_harness.py                                          # evaluation
│   └── paths.py                                                 # central path resolution
├── data/                                                        # source docs + derived data
├── prompts/system_prompt.yaml                                   # versioned prompt config
├── web/                                                         # React app (primary UI)
├── static-demo/index.html                                       # simple HTML/JS fallback (no build step)
└── scripts/debug/                                               # one-off debugging tools
```