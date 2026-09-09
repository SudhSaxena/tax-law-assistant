# Case Study: Building a Production-Grade RAG System

**A retrieval-augmented generation assistant for US federal income tax
questions — built end-to-end, from data pipeline to a deployed, rate-limited
API, with a measured eval baseline and real, fixed production bugs.**

Live demo: [tax-law-assistant](https://tax-law-assistant.vercel.app/) · Repo: [GitHub](https://github.com/SudhSaxena/tax-law-assistant)

---

## The problem

Most "I built a RAG app" projects stop at a working demo. This project was
built to go further: a real evaluation methodology instead of eyeballing
answers, production concerns (caching, streaming, rate limiting, structured
logging) instead of a bare script, and — most importantly — a track record
of finding and fixing genuine correctness bugs rather than assuming a
plausible-looking answer is a correct one.

The domain (US federal income tax, grounded in IRS Publication 17 and
select sections of the Internal Revenue Code) was chosen deliberately: it's
dense, rule-heavy, and has real stakes if wrong, which makes problems like
grounding, citation, and data staleness matter in practice, not just in
theory.

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

**Stack:** Claude Haiku 4.5 (generation) · Voyage AI (embeddings) · ChromaDB
(vector store) · Python FastAPI (backend) · SQLite (cache + usage tracking) · React + TypeScript (frontend) · Render + Vercel (deployment)

## Three real bugs, and why they mattered

### 1. Faithful, but wrong

Early in generation testing, a question about the standard deduction
returned dollar figures directly cited from the tax code — correctly
grounded in the retrieved text, properly cited, and completely wrong in
practice. The tax code states *base* statutory amounts; the actual
usable figure comes from a separate, annually-published IRS inflation
adjustment. The model wasn't hallucinating — it was faithfully reporting
an incomplete source.

**The fix wasn't a better prompt.** It was a data/architecture change: a
separately maintained "current figures" reference, source-level metadata
flagging which excerpts require an adjustment caveat, and a system prompt
update instructing the model to defer to the current-figures block for any
dollar amount. The result: the same retrieved chunks, a structurally
different and correct answer.

**The lesson that generalizes:** grounding in a source is necessary but not
sufficient. A RAG system also has to know whether the source itself is
*complete and current*, not just relevant.

### 2. A retrieval gap semantic search can't see

The eval set includes a deliberately awkward question: *"What is 26 U.S.
Code Section 63 about?"* It failed — not because generation was wrong, but
because the retriever never surfaced Section 63 at all, returning noisy,
irrelevant chunks instead (distances 40%+ higher than a working query).

Diagnosis: a query built almost entirely around a citation/ID ("Section
63") carries very little semantic signal for an embedding model to match
against, compared to a content question like "how is taxable income
defined." A secondary finding surfaced in the same investigation: PDF index
pages had been embedded as regular searchable content — pure keyword noise
polluting the corpus.

This was deliberately **not** patched with a quick fix. It's logged as a
scoped roadmap item (hybrid search — combining keyword/exact match with
semantic search) rather than papered over, since the honest fix requires a
different retrieval strategy, not a tweak.

### 3. The eval judge had its own bugs

Building the evaluation harness surfaced a subtler problem: using an LLM to
grade another LLM's answers introduces measurable self-preference and
prior-knowledge bias. The judge inconsistently flagged a real, correct
dollar figure as "hallucinated" on some questions but accepted the identical
figure on others — because it was fact-checking against its own general
knowledge instead of only checking consistency with the provided reference
answer.

The real fix wasn't more prompt tuning. After several rounds of patching the
judge, the actual insight was that **LLM-as-judge was the wrong tool for a
subset of the eval set** — questions with a single, objectively checkable
answer (a dollar figure) don't need semantic judgment at all. The eval
harness now uses **hybrid grading**: deterministic string checks for
verifiable facts, LLM judgment reserved for genuinely open-ended questions.
Baseline result after the fix: **24/25 (96%)**, with the one remaining
failure being the known, already-diagnosed retrieval gap above — not eval
noise.

## Production engineering

Beyond correctness, the system was built with real deployment concerns in
mind:

- **Streaming responses** (Server-Sent Events) for perceived responsiveness
- **Two-layer caching** — an embedding cache and a semantic response cache
  (cosine similarity, not just exact-match), backed by SQLite
- **Cost tracking** — real token usage and estimated cost logged per
  request (current cost: roughly $0.002 per generated answer on Claude
  Haiku 4.5)
- **Guardrails** — off-topic rejection and prompt-injection resistance via
  a hardened system prompt (the actual defense), with lightweight
  heuristic logging as a secondary signal, not the primary control
- **Rate limiting** — per-IP sliding window, correctly reading
  `X-Forwarded-For` to get the real client IP through Render's reverse
  proxy (a detail that would have silently broken IP-based limiting)
- **Structured logging** — every request traced with a request ID, latency,
  sources retrieved, and outcome
- **Typed, validated configuration** (`pydantic-settings`) — required
  secrets fail fast at startup with a clear error, instead of failing
  confusingly deep inside an API call several requests later
- **Query normalization** — spell-correction preprocessing with explicit
  guards against mangling domain terms and acronyms (a naive spell-checker
  will happily "fix" "IRA" or turn "elderly" into "elder")

## API abuse prevention — the layered picture

Deploying a public LLM-backed endpoint raises a real question: what stops
someone from hitting `/ask` in a loop and running up API costs? This was
explored properly rather than adding one narrow fix:

- **What's implemented:** CORS locked down to
  specific allowed origins (not wildcard), a server-side origin check, and
  per-IP rate limiting — layered together since each covers a different
  gap (CORS restricts which *websites'* JavaScript can read a response,
  the origin check adds a server-side reject that CORS alone doesn't
  provide, and rate limiting caps damage regardless of either) — paired
  with provider-level spending caps as the safety net that holds even if
  every application-level defense is bypassed.
- **What's intentionally not implemented, and why:** full user
  authentication and a BFF proxy — the right answer for a real product with
  real users, but disproportionate scope for a portfolio demonstration of
  RAG and evaluation engineering.

## Results

- **96% eval pass rate** (24/25) on a hand-built, hybrid-graded eval set —
  the one failure is a known, documented retrieval limitation, not noise
- **~$0.002 per query** on Claude Haiku 4.5, with a working cache layer
  reducing repeat-question cost to zero
- **Deployed and live**: FastAPI backend on Render, React/TypeScript
  frontend on Vercel, communicating over a locked-down CORS + rate-limited
  API

## What I'd build next

- Hybrid (keyword + semantic) search to close the Section 63-style
  retrieval gap
- A reranking step and an expanded eval set (50–100 questions)
- Agentic tool-use for cases where fixed retrieval genuinely isn't enough —
  scoped deliberately *after* the above, since plain RAG covers most of
  this project's real question types already