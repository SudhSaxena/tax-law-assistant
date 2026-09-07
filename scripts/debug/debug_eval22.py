from retrieve import retrieve

questions = [
    "What is 26 U.S. Code Section 63 about?",       # eval_22 — failed
    "How is taxable income defined under the tax code?",  # eval_05 — passed, used section_63
]

for q in questions:
    print("=" * 60)
    print(f"Question: {q}")
    print("=" * 60)
    matches = retrieve(q, top_k=5)
    for i, (text, meta, distance) in enumerate(matches, start=1):
        print(f"{i}. source={meta['source']}, distance={distance:.4f}")
        print(f"   {text[:150]}...")
    print()