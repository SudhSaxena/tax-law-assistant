from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import uuid
import time

from generate_answer import generate_answer, generate_answer_stream, format_citations_for_display, ensure_disclaimer
from retrieve import get_query_embedding
from cache import find_similar_response, set_cached_response
from usage_tracker import log_usage
from query_normalizer import normalize_query
from guardrails import flag_possible_injection
from request_logger import log_event

app = FastAPI(title="Tax Law Assistant API")

# Allows a local frontend (running on a different port, e.g. a dev server on
# :5500 or :3000) to call this API from the browser. Locked down to specific
# origins later when this actually deploys — wide open here is fine for
# local-only testing, not something to carry into production as-is.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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