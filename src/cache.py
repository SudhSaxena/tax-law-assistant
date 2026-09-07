import sqlite3
import json
import time
import os
from contextlib import contextmanager

from paths import CACHE_DB_PATH

DB_PATH = str(CACHE_DB_PATH)
print(f"[cache.py] Using cache.db at: {DB_PATH}")


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_cache():
    """Creates the cache tables if they don't exist yet. Safe to call every
    startup — CREATE TABLE IF NOT EXISTS is a no-op if already set up."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                question TEXT PRIMARY KEY,
                embedding TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS response_cache (
                question TEXT PRIMARY KEY,
                embedding TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()


# --- Embedding cache: exact question-text match --------------------------

def get_cached_embedding(question):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT embedding FROM embedding_cache WHERE question = ?",
            (question,),
        ).fetchone()
    return json.loads(row[0]) if row else None


def set_cached_embedding(question, embedding):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO embedding_cache (question, embedding, created_at) VALUES (?, ?, ?)",
            (question, json.dumps(embedding), time.time()),
        )
        conn.commit()


# --- Response cache: semantic (embedding similarity) match ----------------

def cosine_similarity(vec_a, vec_b):
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_similar_response(question_embedding, threshold=0.95):
    """Loads all cached responses and checks similarity in Python. Fine at
    small scale (tens to low hundreds of cached entries) — at real scale
    this would move to a proper vector index (the same Chroma collection
    pattern already used for document retrieval), not a linear scan.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT question, embedding, answer, sources FROM response_cache"
        ).fetchall()

    best_match = None
    best_score = threshold  # only accept matches at or above threshold

    for cached_question, embedding_json, answer, sources_json in rows:
        cached_embedding = json.loads(embedding_json)
        score = cosine_similarity(question_embedding, cached_embedding)
        if score >= best_score:
            best_score = score
            best_match = {
                "matched_question": cached_question,
                "answer": answer,
                "sources": json.loads(sources_json),
                "similarity": score,
            }

    return best_match


def set_cached_response(question, embedding, answer, sources):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO response_cache (question, embedding, answer, sources, created_at) VALUES (?, ?, ?, ?, ?)",
            (question, json.dumps(embedding), answer, json.dumps(sources), time.time()),
        )
        conn.commit()


init_cache()