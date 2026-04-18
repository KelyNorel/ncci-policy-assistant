"""
ingest.py
Parses the 2026 NCCI Medicare Policy Manual PDF, chunks it by section,
embeds with sentence-transformers, and indexes into a local ChromaDB.

Run once:
    python ingest.py --pdf data/2026_ncci_manual.pdf

Re-run with --reset to wipe and rebuild the index.
"""

import argparse
import re
import sys
from pathlib import Path
import numpy as np

import chromadb
import pdfplumber
from sentence_transformers import SentenceTransformer

# ── Config ──────────────────────────────────────────────────────────────────
CHROMA_DIR   = "chroma_db"
COLLECTION   = "ncci_2026"
EMBED_MODEL  = "all-MiniLM-L6-v2"   # fast, 384-dim, runs locally
CHUNK_SIZE   = 600    # target tokens (approx chars / 4)
CHUNK_OVERLAP = 100   # token overlap between adjacent chunks

# Patterns that mark the start of a new section in the manual
# e.g. "A. Introduction", "B. Coding Based on...", "CHAPTER I", "Intro-3"
CHAPTER_RE = re.compile(
    r"^(CHAPTER\s+[IVXLC]+|Chapter\s+[IVXLC]+.*|Introduction)\s*$",
    re.IGNORECASE,
)
SECTION_RE = re.compile(
    r"^([A-Z])\.\s+(.+)$"   # "A. Introduction", "B. Coding..."
)
REVISION_RE = re.compile(r"Revision Date.*?1/1/2026")  # footer noise
PAGE_FOOTER_RE = re.compile(r"^(January 1, 2026\s*Page \d+|[IVXLC]+-\d+|Intro-\d+)\s*$")


# ── Helpers ──────────────────────────────────────────────────────────────────

def clean_line(line: str) -> str:
    line = line.strip()
    line = REVISION_RE.sub("", line)
    return line


def extract_pages(pdf_path: str) -> list[dict]:
    """Return list of {page_num, text} dicts."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            pages.append({"page_num": i + 1, "text": text})
    return pages


def detect_chapter(line: str) -> str | None:
    """Return chapter label if line is a chapter header, else None."""
    # e.g. "CHAPTER I", "Chapter II – Anesthesia Services"
    m = re.match(r"^(?:CHAPTER\s+|Chapter\s+)([IVXLC]+)(.*)?$", line, re.IGNORECASE)
    if m:
        return f"Chapter {m.group(1).upper()}"
    if re.match(r"^Introduction\s*$", line, re.IGNORECASE):
        return "Introduction"
    return None


def detect_section(line: str) -> tuple[str, str] | None:
    """Return (letter, title) if line is a section header like 'A. Introduction'."""
    m = SECTION_RE.match(line)
    if m:
        return m.group(1), m.group(2).strip()
    return None


def split_into_sections(pages: list[dict]) -> list[dict]:
    """
    Walk every line of every page and emit a record per section:
      {chapter, section_letter, section_title, page_start, text}
    """
    sections = []
    current_chapter = "Introduction"
    current_section_letter = ""
    current_section_title = "General"
    current_page = 1
    buffer = []

    def flush():
        text = " ".join(buffer).strip()
        if text:
            sections.append({
                "chapter":         current_chapter,
                "section_letter":  current_section_letter,
                "section_title":   current_section_title,
                "page_start":      current_page,
                "text":            text,
            })

    for page in pages:
        lines = page["text"].split("\n")
        for line in lines:
            line = clean_line(line)
            if not line:
                continue
            if PAGE_FOOTER_RE.match(line):
                continue

            # Chapter boundary
            chap = detect_chapter(line)
            if chap:
                flush()
                buffer = []
                current_chapter = chap
                current_section_letter = ""
                current_section_title = "General"
                current_page = page["page_num"]
                continue

            # Section boundary (A. / B. / ...)
            sec = detect_section(line)
            if sec:
                flush()
                buffer = []
                current_section_letter, current_section_title = sec
                current_page = page["page_num"]
                continue

            buffer.append(line)

    flush()  # last section
    return sections


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping char-based chunks.
    size and overlap are in approximate tokens (1 token ≈ 4 chars).
    """
    char_size    = size * 4
    char_overlap = overlap * 4

    chunks = []
    start = 0
    while start < len(text):
        end = start + char_size
        chunks.append(text[start:end].strip())
        start += char_size - char_overlap
    return [c for c in chunks if len(c) > 50]   # drop tiny tail fragments


def build_chunks(sections: list[dict]) -> list[dict]:
    """
    For each section, split into overlapping chunks and attach metadata.
    Returns list of {id, text, metadata} ready for ChromaDB.
    """
    records = []
    for sec_idx, sec in enumerate(sections):
        sub_chunks = chunk_text(sec["text"])
        for idx, chunk in enumerate(sub_chunks):
            rec_id = (
                f"{sec_idx}_{sec['chapter']}_{sec['section_letter'] or 'X'}_{sec['page_start']}_{idx}"
            ).replace(" ", "_")
            records.append({
                "id":   rec_id,
                "text": chunk,
                "metadata": {
                    "chapter":        sec["chapter"],
                    "section_letter": sec["section_letter"],
                    "section_title":  sec["section_title"],
                    "page_start":     sec["page_start"],
                    "chunk_index":    idx,
                },
            })
    return records


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf",   default="data/2026_ncci_manual.pdf")
    parser.add_argument("--reset", action="store_true", help="Wipe existing index first")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"❌  PDF not found: {pdf_path}")
        sys.exit(1)

    # ── ChromaDB ──
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    if args.reset:
        try:
            client.delete_collection(COLLECTION)
            print("🗑️  Deleted existing collection.")
        except Exception:
            pass
    collection = client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    if collection.count() > 0 and not args.reset:
        print(f"✅  Collection already has {collection.count()} chunks. Use --reset to rebuild.")
        return

    # ── Parse ──
    print(f"📄  Extracting text from {pdf_path} …")
    pages = extract_pages(str(pdf_path))
    print(f"    {len(pages)} pages extracted.")

    print("✂️   Splitting into sections …")
    sections = split_into_sections(pages)
    print(f"    {len(sections)} sections found.")

    print("🔪  Chunking sections …")
    chunks = build_chunks(sections)
    print(f"    {len(chunks)} chunks total.")

    # ── Embed ──
    print(f"🤖  Loading embedding model ({EMBED_MODEL}) …")
    model = SentenceTransformer(EMBED_MODEL)


    print("🔎  Embedding all chunks ...")
    all_embeddings = model.encode([c["text"] for c in chunks], show_progress_bar=False)

    print("🔎  Deduplicating by cosine similarity (threshold=0.95) ...")
    norms  = np.linalg.norm(all_embeddings, axis=1, keepdims=True)
    normed = all_embeddings / (norms + 1e-9)
    sim_matrix = normed @ normed.T

    keep    = []
    dropped = set()
    for i in range(len(chunks)):
        if i in dropped:
            continue
        keep.append(i)
        for j in range(i + 1, len(chunks)):
            if sim_matrix[i, j] > 0.95:
                dropped.add(j)

    chunks         = [chunks[i] for i in keep]
    all_embeddings = all_embeddings[keep]
    print(f"    {len(chunks)} chunks after dedup ({len(dropped)} removed).")

    BATCH = 128
    print(f"📥  Indexing in batches of {BATCH} ...")
    for i in range(0, len(chunks), BATCH):
        collection.add(
            ids=[c["id"]       for c in chunks[i:i+BATCH]],
            documents=[c["text"]     for c in chunks[i:i+BATCH]],
            embeddings=all_embeddings[i:i+BATCH].tolist(),
            metadatas=[c["metadata"] for c in chunks[i:i+BATCH]],
        )
        print(f"    indexed {min(i+BATCH, len(chunks))}/{len(chunks)}")



    print(f"\n✅  Done! {collection.count()} chunks indexed into '{CHROMA_DIR}/{COLLECTION}'.")

    # ── Quick sanity check ──
    print("\n🔍  Sanity check — query: 'mutually exclusive procedures'")
    test_emb = model.encode(["mutually exclusive procedures"]).tolist()
    results = collection.query(query_embeddings=test_emb, n_results=3)
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        print(f"  [{meta['chapter']} | {meta['section_letter']}. {meta['section_title']} | p.{meta['page_start']}]")
        print(f"  {doc[:120]} …\n")


if __name__ == "__main__":
    main()