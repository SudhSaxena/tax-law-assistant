import os
import json
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
from anthropic import Anthropic

from generate_answer import generate_answer, format_citations_for_display, PROMPT_VERSION
from paths import EVAL_QUESTIONS_PATH, EVAL_RESULTS_PATH

load_dotenv()
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

JUDGE_PROMPT = """You are grading a RAG system's answer against a reference \
answer for an evaluation set.

IMPORTANT: Do not use your own general knowledge of tax law to fact-check the \
generated answer. Your only job is to check consistency between the generated \
answer and the provided reference answer — nothing else. The reference answer \
is the sole source of truth for this grading task, even if it differs from \
what you believe you know about tax law. If the generated answer states a fact \
that isn't in the reference answer, treat it as UNVERIFIED, not as false — do \
not fail it on that basis alone.

Grading rules:
- If the reference answer begins with "NOT ANSWERABLE FROM CORPUS", the \
question is intentionally outside the system's knowledge base. PASS only if \
the generated answer declines to answer or clearly states it doesn't have \
enough information, rather than confidently guessing. FAIL if it hallucinates \
an answer.
- Otherwise, PASS if the generated answer includes the reference answer's key \
facts (numbers, definitions, rules) without contradicting them, even if worded \
differently or more detailed.
- The generated answer is allowed to include additional information beyond \
what's in the reference answer — the reference answer is a minimum bar, not an \
exhaustive list of every fact the system is allowed to state. Only FAIL for \
extra information if it directly contradicts a specific fact stated in the \
reference answer. Do NOT fail an answer just because it contains a fact the \
reference answer doesn't mention — that is unverified, not wrong.
- A contradiction means the generated answer states a DIFFERENT VALUE FOR THE \
SAME FACT the reference answer specifies (e.g., reference says the additional \
deduction is $1,600, generated answer says it's $1,000 — same fact, different \
number, THAT is a contradiction). Mentioning a separate, different provision \
or figure alongside the correct answer is NOT a contradiction, even if it's \
also a dollar amount related to the same general topic (e.g., reference \
answer states the age-65 additional standard deduction is $1,600; generated \
answer correctly states $1,600 AND also mentions a separate $6,000 enhanced \
senior deduction — these are two different provisions, not competing answers \
to the same question, so this is NOT a contradiction).
- FAIL if the generated answer contradicts the reference answer, omits the key \
fact entirely, states figures that conflict with the reference answer's \
figures, or declines to answer a question that the reference answer shows is \
answerable.
- Ignore stylistic differences, formatting, and extra citations — judge only \
factual consistency with the reference answer.

Respond with EXACTLY two lines, nothing else, no markdown, no extra text:
VERDICT: pass or fail
REASONING: one short sentence, under 25 words
"""


def judge_answer(question, reference_answer, generated_answer):
    user_message = f"""Question: {question}

Reference answer: {reference_answer}

Generated answer: {generated_answer}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        extra_body={"temperature": 0},  # SDK v1.0+ moved sampling params out of
                                         # the typed method signature; the
                                         # underlying API still accepts them for
                                         # Haiku 4.5, just via extra_body now
        system=JUDGE_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()

    # Plain delimited-line format instead of JSON — avoids an entire class of
    # parsing failures (unescaped quotes, stray braces) that JSON is prone to
    # when the content itself contains quote marks.
    verdict_match = re.search(r"VERDICT:\s*(pass|fail)", raw, re.IGNORECASE)
    reasoning_match = re.search(r"REASONING:\s*(.+)", raw, re.IGNORECASE | re.DOTALL)

    if verdict_match and reasoning_match:
        return {
            "verdict": verdict_match.group(1).lower(),
            "reasoning": reasoning_match.group(1).strip(),
        }
    else:
        return {"verdict": "judge_error", "reasoning": f"Could not parse judge output: {raw[:200]}"}


def deterministic_check(generated_answer, expected_values):
    """Fast, free, bug-immune grading for questions with a checkable answer:
    pass if any acceptable representation of the expected value appears in
    the generated answer. No LLM call, no judge bugs possible.
    """
    answer_lower = generated_answer.lower()
    for value in expected_values:
        if value.lower() in answer_lower:
            return {"verdict": "pass", "reasoning": f"Found expected value '{value}' in generated answer."}
    return {
        "verdict": "fail",
        "reasoning": f"None of the expected values {expected_values} found in generated answer.",
    }


def run_eval(eval_path=None, output_path=None):
    eval_path = eval_path or str(EVAL_QUESTIONS_PATH)
    output_path = output_path or str(EVAL_RESULTS_PATH)
    with open(eval_path, encoding="utf-8") as f:
        eval_questions = json.load(f)

    results = []
    for i, item in enumerate(eval_questions, start=1):
        print(f"[{i}/{len(eval_questions)}] {item['id']}: {item['question']}")

        raw_answer, matches = generate_answer(item["question"])
        display_answer = format_citations_for_display(raw_answer)

        grading_type = item.get("grading_type", "llm_judge")
        if grading_type == "deterministic":
            verdict = deterministic_check(raw_answer, item["expected_value"])
        else:
            verdict = judge_answer(item["question"], item["reference_answer"], raw_answer)

        results.append({
            "id": item["id"],
            "question": item["question"],
            "reference_answer": item["reference_answer"],
            "generated_answer": display_answer,
            "sources_retrieved": [meta["source"] for _text, meta, _dist in matches],
            "grading_type": grading_type,
            "verdict": verdict["verdict"],
            "judge_reasoning": verdict["reasoning"],
        })

        print(f"    -> {verdict['verdict']}: {verdict['reasoning']}")

    passed = sum(1 for r in results if r["verdict"] == "pass")
    failed = sum(1 for r in results if r["verdict"] == "fail")
    judge_errors = sum(1 for r in results if r["verdict"] == "judge_error")
    total = len(results)

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "prompt_version": PROMPT_VERSION,
        "total": total,
        "passed": passed,
        "failed": failed,
        "judge_errors": judge_errors,
        "pass_rate": round(passed / total, 3) if total else 0,
        "results": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 50)
    print(f"Eval run complete — prompt version {PROMPT_VERSION}")
    print(f"Passed: {passed}/{total} ({report['pass_rate'] * 100:.1f}%)")
    if judge_errors:
        print(f"Judge errors (unparseable, check manually): {judge_errors}")
    print(f"Full report saved to {output_path}")

    if failed:
        print("\nFailed questions:")
        for r in results:
            if r["verdict"] == "fail":
                print(f"  - {r['id']}: {r['question']}")
                print(f"    reason: {r['judge_reasoning']}")


if __name__ == "__main__":
    run_eval()