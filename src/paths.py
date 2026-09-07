from pathlib import Path

# Resolves to the project root regardless of what directory the process was
# launched from — this file's own location is the anchor, not os.getcwd().
# paths.py lives in src/, one level below the actual project root, so we go
# up two levels (src/ -> project root), not one.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
CHROMA_DIR = PROJECT_ROOT / "chroma_db"
CACHE_DB_PATH = PROJECT_ROOT / "cache.db"
LOGS_DIR = PROJECT_ROOT / "logs"

# Specific file paths used across modules
PUB17_PDF_PATH = DATA_DIR / "pub17.pdf"
CHUNKS_PATH = DATA_DIR / "chunks.json"
CHUNKS_WITH_EMBEDDINGS_PATH = DATA_DIR / "chunks_with_embeddings.json"
CURRENT_FIGURES_PATH = DATA_DIR / "current_figures.json"
SOURCE_METADATA_PATH = DATA_DIR / "source_metadata.json"
EVAL_QUESTIONS_PATH = DATA_DIR / "eval_questions.json"
EVAL_RESULTS_PATH = DATA_DIR / "eval_results.json"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.yaml"
LOG_FILE_PATH = LOGS_DIR / "app.jsonl"