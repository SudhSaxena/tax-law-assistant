from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import json
import re
from paths import DATA_DIR, PUB17_PDF_PATH, CHUNKS_PATH


def extract_pdf_text(path):
    reader = PdfReader(path)
    return "\n".join(page.extract_text() for page in reader.pages)


def clean_pdf_text(text):
    # Rejoin words split by a line-break hyphen: "infor-\nmation" -> "information"
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    # Fix stray mid-word spaces before a hyphen from justified-text kerning,
    # e.g. "Self -Select" -> "Self-Select"
    text = re.sub(r'(\w) -(\w)', r'\1-\2', text)

    # Fix kerning splits where a word's first letter gets separated,
    # e.g. "T o file" -> "To file", "Y our return" -> "Your return".
    # Only merges when the lone letter isn't a real single-letter word (A, I),
    # so "A dog" and "I am" are left alone.
    def _fix_split_first_letter(match):
        letter, rest = match.group(1), match.group(2)
        if letter in ("A", "I"):
            return match.group(0)
        return letter + rest

    text = re.sub(r'\b([A-Z]) ([a-z]+)\b', _fix_split_first_letter, text)
    # Collapse remaining single newlines (mid-paragraph wraps) into spaces,
    # but keep true paragraph breaks (double newlines)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # Collapse any run of multiple spaces/tabs into one
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def chunk_text(text, source_name, chunk_size=800, overlap=150):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
    )
    pieces = splitter.split_text(text)
    return [
        {"source": source_name, "chunk_id": f"{source_name}_{i}", "text": piece}
        for i, piece in enumerate(pieces)
    ]


all_chunks = []

# Chunk the PDF
pdf_text = clean_pdf_text(extract_pdf_text(PUB17_PDF_PATH))
all_chunks += chunk_text(pdf_text, "pub17")

# Chunk each Title 26 section file
for entry in DATA_DIR.iterdir():
    if entry.name.endswith(".txt"):
        with open(entry, encoding="utf-8") as f:
            text = f.read()
        all_chunks += chunk_text(text, entry.name.replace(".txt", ""), chunk_size=1500, overlap=100)

with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
    json.dump(all_chunks, f, indent=2)

print(f"Created {len(all_chunks)} chunks")