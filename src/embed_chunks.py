import json
import voyageai
from paths import CHUNKS_PATH, CHUNKS_WITH_EMBEDDINGS_PATH
from settings import settings

vo = voyageai.Client(api_key=settings.voyage_api_key)

with open(CHUNKS_PATH, encoding="utf-8") as f:
    chunks = json.load(f)

texts = [c["text"] for c in chunks]

BATCH_SIZE = 128
all_embeddings = []

for i in range(0, len(texts), BATCH_SIZE):
    batch = texts[i : i + BATCH_SIZE]
    result = vo.embed(batch, model="voyage-4-lite", input_type="document")
    all_embeddings.extend(result.embeddings)
    print(f"Embedded {min(i + BATCH_SIZE, len(texts))}/{len(texts)}")

# Attach each embedding to its chunk and save
for chunk, embedding in zip(chunks, all_embeddings):
    chunk["embedding"] = embedding

with open(CHUNKS_WITH_EMBEDDINGS_PATH, "w", encoding="utf-8") as f:
    json.dump(chunks, f)

print(f"Done. Saved {len(chunks)} chunks with embeddings.")