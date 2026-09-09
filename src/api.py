from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import json
import uuid
import time
from collections import defaultdict

from generate_answer import generate_answer, generate_answer_stream, format_citations_for_display, ensure_disclaimer
from retrieve import get_query_embedding
from cache import find_similar_response, set_cached_response
from usage_tracker import log_usage
from query_normalizer import normalize_query
from guardrails import flag_possible_injection
from request_logger import log_event
from settings import settings

app = FastAPI(title="Tax Law Assistant API")

# ALLOWED_ORIGINS itself lives in settings.py (env-driven, comma-separated
# string parsed into a list) — same pattern as the API keys. Means changing
# a frontend URL (e.g. after renaming the Vercel app) is a config change in
# Render's dashboard, not a code change + redeploy.
ALLOWED_ORIGINS = settings.allowed_origins_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

RATE_LIMIT_MAX_REQUESTS = 5
RATE_LIMIT_WINDOW_SECONDS = 60
request_timestamps: dict = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Simple in-memory sliding-window limiter, per client IP. Known
    # limitations, worth being explicit about: resets on server restart, and
    # wouldn't coordinate across multiple server instances if this app ever
    # scaled horizontally — a real limit for this simple approach, not
    # relevant yet at this project's scale (single Render instance).
    if request.url.path in ("/ask", "/ask/stream"):
        # Render (and most hosts) sit behind a reverse proxy, so
        # request.client.host would show the PROXY's IP for every request,
        # not the real visitor — that would make IP-based limiting useless.
        # X-Forwarded-For carries the real client IP in that setup.
        forwarded_for = request.headers.get("x-forwarded-for")
        client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
            request.client.host if request.client else "unknown"
        )

        now = time.time()
        timestamps = request_timestamps[client_ip]
        timestamps[:] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW_SECONDS]

        if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
            log_event(
                "rate_limit_exceeded",
                level="warning",
                client_ip=client_ip,
                path=request.url.path,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded: max {RATE_LIMIT_MAX_REQUESTS} "
                    f"requests per {RATE_LIMIT_WINDOW_SECONDS} seconds. Try again shortly."
                },
            )

        timestamps.append(now)

    return await call_next(request)


@app.middleware("http")
async def origin_check_middleware(request: Request, call_next):
    # Server-side origin check, separate from CORS. CORS headers only tell
    # a BROWSER whether it's allowed to read a response — the server still
    # fully processes the request either way. This middleware actually
    # rejects the request server-side if the Origin doesn't match, which
    # CORS alone never does.
    #
    # Real limitation: Origin/Referer are just request headers, trivially
    # set to anything by a non-browser client (curl -H "Origin: ..."). This
    # blocks casual/accidental direct access, not a deliberate attacker who
    # can simply forge the header. It's a much weaker protection than actual
    # rate limiting or API-key auth, kept simple here on request.
    if request.url.path in ("/ask", "/ask/stream"):
        origin = request.headers.get("origin") or request.headers.get("referer", "")
        if not any(origin.startswith(allowed) for allowed in ALLOWED_ORIGINS):
            return JSONResponse(
                status_code=403,
                content={"detail": "Requests must originate from an allowed origin."},
            )
    return await call_next(request)


@app.middleware("http")
async def tracing_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.time()

    try:
        response = await call_next(request)
    except Exception as exc:
        latency_ms = round((time.time() - start_time) * 1000, 1)
        log_event(
            "request_failed",
            level="error",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            latency_ms=latency_ms,
            error=str(exc),
        )
        raise  # re-raise so FastAPI's normal error handling still applies

    latency_ms = round((time.time() - start_time) * 1000, 1)
    log_event(
        "request_completed",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        status_code=response.status_code,
        latency_ms=latency_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


class QuestionRequest(BaseModel):
    question: str


class SourceInfo(BaseModel):
    source: str
    distance: float


class AnswerResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]


SIMILARITY_THRESHOLD = 0.95  # cosine similarity — high bar, so only genuinely
                              # near-duplicate questions get served from cache


def check_response_cache(question):
    """Returns a cached (answer, sources) tuple if a sufficiently similar
    question was answered before, else None. Also returns the question's own
    embedding, so the caller can reuse it for caching the new response
    without embedding the question twice.
    """
    question_embedding = get_query_embedding(question)
    match = find_similar_response(question_embedding, threshold=SIMILARITY_THRESHOLD)
    return match, question_embedding


@app.post("/ask", response_model=AnswerResponse)
def ask_question(payload: QuestionRequest, request: Request):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    question = normalize_query(question)
    injection_flagged = flag_possible_injection(question)
    request_id = request.state.request_id

    cached_match, question_embedding = check_response_cache(question)
    if cached_match:
        log_usage(question, endpoint="ask", cache_hit=True, flagged_injection=injection_flagged)
        log_event(
            "ask_answered",
            request_id=request_id,
            question=question,
            cache_hit=True,
            flagged_injection=injection_flagged,
            sources=[s["source"] for s in cached_match["sources"]],
        )
        sources = [SourceInfo(**s) for s in cached_match["sources"]]
        return AnswerResponse(answer=cached_match["answer"], sources=sources)

    raw_answer, matches = generate_answer(question, flagged_injection=injection_flagged)
    display_answer = format_citations_for_display(raw_answer)

    sources = [
        SourceInfo(source=meta["source"], distance=distance)
        for _text, meta, distance in matches
    ]

    set_cached_response(
        question,
        question_embedding,
        display_answer,
        [s.model_dump() for s in sources],
    )

    log_event(
        "ask_answered",
        request_id=request_id,
        question=question,
        cache_hit=False,
        flagged_injection=injection_flagged,
        sources=[s.source for s in sources],
    )

    return AnswerResponse(answer=display_answer, sources=sources)


@app.post("/ask/stream")
def ask_question_stream(payload: QuestionRequest, request: Request):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    question = normalize_query(question)
    injection_flagged = flag_possible_injection(question)
    request_id = request.state.request_id

    def event_generator():
        cached_match, question_embedding = check_response_cache(question)
        if cached_match:
            log_usage(question, endpoint="ask_stream", cache_hit=True, flagged_injection=injection_flagged)
            log_event(
                "ask_stream_answered",
                request_id=request_id,
                question=question,
                cache_hit=True,
                flagged_injection=injection_flagged,
                sources=[s["source"] for s in cached_match["sources"]],
            )
            # Nothing to actually stream — a cache hit already has the full
            # answer, so it's sent as one delta followed immediately by done.
            yield f"data: {json.dumps({'delta': cached_match['answer']})}\n\n"
            yield f"data: {json.dumps({'done': True, 'formatted_answer': cached_match['answer'], 'sources': cached_match['sources']})}\n\n"
            return

        full_raw_answer = ""
        matches = None

        for chunk_text, chunk_matches in generate_answer_stream(question, flagged_injection=injection_flagged):
            full_raw_answer += chunk_text
            matches = chunk_matches
            # Raw delta — not yet citation-formatted, per the streaming
            # tradeoff noted in generate_answer.py
            yield f"data: {json.dumps({'delta': chunk_text})}\n\n"

        # Final event: fully formatted answer + sources, sent once
        full_raw_answer = ensure_disclaimer(full_raw_answer)
        display_answer = format_citations_for_display(full_raw_answer)
        sources = [
            {"source": meta["source"], "distance": distance}
            for _text, meta, distance in matches
        ]

        set_cached_response(question, question_embedding, display_answer, sources)

        log_event(
            "ask_stream_answered",
            request_id=request_id,
            question=question,
            cache_hit=False,
            flagged_injection=injection_flagged,
            sources=[s["source"] for s in sources],
        )

        yield f"data: {json.dumps({'done': True, 'formatted_answer': display_answer, 'sources': sources})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/health")
def health_check():
    return {"status": "ok"}