import re
from spellchecker import SpellChecker

spell = SpellChecker()

# Tax/domain-specific terms that might not be in a general English dictionary
# but are correct as-is — prevents the spell-checker from "fixing" jargon.
spell.word_frequency.load_words([
    "deductible", "itemize", "itemized", "taxpayer", "filers", "withholding",
    "dependents", "audit", "efile", "amortization", "elderly",
])

# Explicit overrides for known typos where the general spell-checker's
# frequency-based tie-breaking picks the wrong word (e.g. "eldery" is
# exactly one edit away from both "elder" and "elderly" — a common general
# word can easily out-rank the domain-specific one we actually care about).
# Checked before the general checker, so these are deterministic rather than
# dependent on corpus frequency statistics.
KNOWN_CORRECTIONS = {
    "eldery": "elderly",
}


def normalize_query(text):
    """Corrects likely misspellings in a user's question before it's used
    for embedding, retrieval, or caching. Deliberately conservative:
    - Checks KNOWN_CORRECTIONS first for terms where general spell-checking
      is known to pick the wrong word
    - Skips short words (<=3 chars) — too easy to "correct" wrongly
    - Skips all-caps words (acronyms like IRA, PIN, MFS, IRS)
    - Skips words containing digits (1040, 2025, etc.)
    - Only replaces a word if the checker considers it unknown AND has a
      confident correction — otherwise leaves it untouched rather than
      guessing
    Preserves original capitalization pattern and all punctuation/spacing.
    """
    tokens = re.findall(r"\w+|\W+", text)
    corrected_tokens = []

    for token in tokens:
        if not token.isalpha() or len(token) <= 3 or token.isupper():
            corrected_tokens.append(token)
            continue

        lower_token = token.lower()

        if lower_token in KNOWN_CORRECTIONS:
            correction = KNOWN_CORRECTIONS[lower_token]
            if token[0].isupper():
                correction = correction.capitalize()
            corrected_tokens.append(correction)
            continue

        if lower_token not in spell.unknown([lower_token]):
            corrected_tokens.append(token)
            continue

        correction = spell.correction(lower_token)
        if not correction or correction == lower_token:
            corrected_tokens.append(token)
            continue

        # Preserve capitalization: if original started with a capital letter,
        # capitalize the correction too.
        if token[0].isupper():
            correction = correction.capitalize()
        corrected_tokens.append(correction)

    return "".join(corrected_tokens)


if __name__ == "__main__":
    test_cases = [
        "What is the stnadard deduction?",
        "Can I claim the eldery credit?",
        "Am I eligible for an IRA contribution in 2025?",
        "What is a Self-Select PIN?",
    ]
    for q in test_cases:
        print(f"{q!r} -> {normalize_query(q)!r}")