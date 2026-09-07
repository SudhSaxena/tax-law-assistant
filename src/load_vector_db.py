import json
import chromadb
from paths import CHROMA_DIR, CHUNKS_WITH_EMBEDDINGS_PATH

# PersistentClient writes to disk at this path, so the DB survives between runs
client = chromadb.PersistentClient(path=str(CHROMA_DIR))

# get_or_create_collection: won't error if we run this script again later
collection = client.get_or_create_collection(name="tax_docs")

with open(CHUNKS_WITH_EMBEDDINGS_PATH, encoding="utf-8") as f:
    chunks = json.load(f)

# Chroma's add() wants parallel lists: ids, documents (raw text), embeddings,
# and metadatas — not a list of dicts. We build those lists from our chunks.
ids = [c["chunk_id"] for c in chunks]
documents = [c["text"] for c in chunks]
embeddings = [c["embedding"] for c in chunks]
metadatas = [{"source": c["source"]} for c in chunks]

# Chroma's add() has a practical batch-size limit, so we insert in chunks
# of a few hundred at a time rather than all 1531 at once.
BATCH_SIZE = 500
for i in range(0, len(ids), BATCH_SIZE):
    collection.add(
        ids=ids[i : i + BATCH_SIZE],
        documents=documents[i : i + BATCH_SIZE],
        embeddings=embeddings[i : i + BATCH_SIZE],
        metadatas=metadatas[i : i + BATCH_SIZE],
    )
    print(f"Inserted {min(i + BATCH_SIZE, len(ids))}/{len(ids)}")

print(f"Done. Collection '{collection.name}' now has {collection.count()} items.")