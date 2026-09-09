import json
import yaml
from anthropic import Anthropic
from retrieve import retrieve
from usage_tracker import log_usage
from settings import settings
from paths import SYSTEM_PROMPT_PATH, CURRENT_FIGURES_PATH, SOURCE_METADATA_PATH

client = Anthropic(api_key=settings.anthropic_api_key)

with open(SYSTEM_PROMPT_PATH, encoding="utf-8") as f:
    prompt_config = yaml.safe_load(f)

SYSTEM_PROMPT = prompt_config["prompt"]
PROMPT_VERSION = prompt_config["version"]  # useful later for eval logging

with open(CURRENT_FIGURES_PATH, encoding="utf-8") as f:
    CURRENT_FIGURES = json.load(f)

with open(SOURCE_METADATA_PATH, encoding="utf-8") as f:
    SOURCE_METADATA = json.load(f)


DISCLAIMER_TEXT = "This is general information, not personalized tax advice."


def ensure_disclaimer(answer_text):
    """Programmatic safety net: the system prompt asks the model to always
    end with the disclaimer, but under adversarial input a model might skip
    it. This guarantees it's present regardless of model compliance, rather
    than relying entirely on the prompt.
    """
    if DISCLAIMER_TEXT.lower() not in answer_text.lower():
        answer_text = answer_text.rstrip() + "\n\n" + DISCLAIMER_TEXT
    return answer_text


def build_context_block(matches):
    parts = []

    # Always include the current-figures reference first, as a distinct,
    # high-authority block. This gives the model an authoritative source for
    # dollar amounts that doesn't depend on the vector search having
    # retrieved the right statutory chunk.
    figures_block = (
        f"[current_figures_reference — tax year {CURRENT_FIGURES['tax_year']}, "
        f"source: {CURRENT_FIGURES['source']}]\n"
        f"{json.dumps(CURRENT_FIGURES['figures'], indent=2)}"
    )
    parts.append(figures_block)

    # Then the retrieved chunks, each annotated with its source metadata note
    # when the source is flagged as requiring annual adjustment. This turns
    # "does this number need a caveat?" into a lookup instead of something
    # the model has to infer from the text itself.
    for i, (text, meta, _distance) in enumerate(matches, start=1):
        source = meta["source"]
        source_info = SOURCE_METADATA.get(source, {})
        annotation = ""
        if source_info.get("requires_annual_adjustment"):
            annotation = f"\n[NOTE: {source_info['note']}]"
        parts.append(f"[{source}] Excerpt {i}:\n{text}{annotation}")

    return "\n\n".join(parts)


import re


def format_citations_for_display(answer_text):
    """Translate internal source keys like [pub17] into human-readable
    citations before showing the answer to a user. The model keeps citing
    with our stable internal keys (good for prompt-following and logging);
    this is the only place that translation to a display-friendly form
    happens, so the underlying keys never need to change even if display
    names or links do.
    """

    def replace_key(match):
        key = match.group(1)
        info = SOURCE_METADATA.get(key)
        if not info:
            return match.group(0)  # unknown key, leave as-is rather than guess
        display_name = info.get("display_name", key)
        url = info.get("url")
        return f"[{display_name}]({url})" if url else f"[{display_name}]"

    return re.sub(r"\[([a-zA-Z0-9_]+)\]", replace_key, answer_text)


def generate_answer(question, top_k=5, flagged_injection=False):
    matches = retrieve(question, top_k=top_k)
    context_block = build_context_block(matches)

    user_message = f"""Context excerpts:
{context_block}

Question: {question}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    log_usage(
        question,
        endpoint="generate_answer",
        cache_hit=False,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        flagged_injection=flagged_injection,
    )

    answer_text = ensure_disclaimer(response.content[0].text)
    return answer_text, matches


def generate_answer_stream(question, top_k=5, flagged_injection=False):
    """Streaming variant: retrieves matches first (needed either way), then
    yields raw text chunks as Claude generates them. Citation formatting is
    NOT applied here — it happens once on the complete text after streaming
    finishes, since format_citations_for_display() needs the full string to
    reliably match bracket patterns. Callers should apply formatting to the
    accumulated full text once streaming is done, not to individual chunks.

    Yields: (chunk_text, matches) tuples. `matches` is the same on every
    yield (retrieval happens once, up front) — included on each tuple only
    for caller convenience.
    """
    matches = retrieve(question, top_k=top_k)
    context_block = build_context_block(matches)

    user_message = f"""Context excerpts:
{context_block}

Question: {question}"""

    with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for chunk_text in stream.text_stream:
            yield chunk_text, matches

        final_message = stream.get_final_message()

    log_usage(
        question,
        endpoint="generate_answer_stream",
        cache_hit=False,
        input_tokens=final_message.usage.input_tokens,
        output_tokens=final_message.usage.output_tokens,
        flagged_injection=flagged_injection,
    )


if __name__ == "__main__":
    question = "What is the standard deduction?"
    raw_answer, matches = generate_answer(question)
    display_answer = format_citations_for_display(raw_answer)

    print(f"Question: {question}\n")
    print("Answer (user-facing):")
    print(display_answer)
    print("\n--- Sources used (internal, for debugging/logging) ---")
    for text, meta, distance in matches:
        print(f"[{meta['source']}] distance={distance:.4f}")