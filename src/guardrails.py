import re

# Heuristic patterns commonly seen in prompt injection attempts. This is a
# blunt instrument — matches don't necessarily mean malicious intent (a
# legitimate question could coincidentally contain one of these phrases),
# so this flags for logging/review rather than blocking the request. The
# real defense is the system prompt instructing the model to ignore
# embedded instructions in the question field; this is a secondary signal
# for future monitoring (ties into Step 5: tracing/logging).
INJECTION_PATTERNS = [
    r"ignore (all|the|any|previous|prior|above) instructions",
    r"disregard (all|the|any|previous|prior|above)",
    r"you are now",
    r"act as (a|an)",
    r"pretend (you are|to be)",
    r"reveal (your|the) (system prompt|instructions)",
    r"what (is|are) your (system prompt|instructions)",
    r"forget (everything|all|your instructions)",
    r"new instructions:",
    r"override (your|these|the) (rules|instructions|configuration)",
]

_compiled_patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def flag_possible_injection(text):
    """Returns True if the text matches a known injection-attempt pattern.
    Not a security guarantee — a determined attacker can phrase around
    these patterns, and the system prompt's instruction to treat the
    question as data (not commands) is the actual defense. This is a
    lightweight signal for logging/monitoring, not a gate.
    """
    return any(pattern.search(text) for pattern in _compiled_patterns)