import time
from retrieve import get_query_embedding

question = "What is the standard deduction?"

start = time.time()
get_query_embedding(question)
first_call = time.time() - start

start = time.time()
get_query_embedding(question)
second_call = time.time() - start

print(f"First call (should hit Voyage API):  {first_call:.3f}s")
print(f"Second call (should hit cache):      {second_call:.3f}s")
print(f"Speedup: {first_call / second_call:.1f}x" if second_call > 0 else "Second call was instant (0.000s)")