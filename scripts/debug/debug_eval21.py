from retrieve import retrieve

question = "Can I claim the standard deduction if I'm filing as married filing separately?"

matches = retrieve(question, top_k=5)
for i, (text, meta, distance) in enumerate(matches, start=1):
    print(f"{i}. source={meta['source']}, distance={distance:.4f}")
    print(f"   {text[:400]}")
    print()