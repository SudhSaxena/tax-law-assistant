import os
import chromadb
from dotenv import load_dotenv
import voyageai

from cache import get_cached_embedding, set_cached_embedding
from paths import CHROMA_DIR

load_dotenv()

vo = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
client = chromadb.PersistentClient(path=str(CHROMA_DIR))
collection = client.get_or_create_collection(name="tax_docs")


def get_query_embedding(question):
    """Checks the embedding cache before calling Voyage. An exact repeat of
    a question (same string) skips the embedding API call entirely — cheap
    win since embedding is billed per call regardless of whether the result
    changes.
    """
    cached = get_cached_embedding(question)
    if cached is not None:
        return cached

    # input_type="query" (not "document") — Voyage optimizes the embedding
    # differently depending on which side of the search it's used for.
    result = vo.embed([question], model="voyage-4-lite", input_type="query")
    embedding = result.embeddings[0]
    set_cached_embedding(question, embedding)
    return embedding


def retrieve(question, top_k=5):
    question_embedding = get_query_embedding(question)

    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=top_k,
    )

    # Chroma returns parallel lists (one per query) — we only sent one
    # question, so we pull out results[...][0]
    docs = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    return list(zip(docs, metadatas, distances))


if __name__ == "__main__":
    question = "What is the standard deduction?"
    matches = retrieve(question, top_k=5)

    print(f"Question: {question}\n")
    for i, (text, meta, distance) in enumerate(matches, start=1):
        print(f"--- Match {i} (source: {meta['source']}, distance: {distance:.4f}) ---")
        print(text[:300])
        print()