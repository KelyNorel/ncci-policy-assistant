"""
retriever.py
Queries ChromaDB and returns ranked chunks with citation metadata.
Uses MMR (Maximal Marginal Relevance) to balance relevance and diversity,
plus a per-page limit to avoid redundant chunks from the same page.
"""

import numpy as np
import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_DIR    = "chroma_db"
COLLECTION    = "ncci_2026"
EMBED_MODEL   = "all-MiniLM-L6-v2"
TOP_K         = 5     # final chunks returned
FETCH_K       = 15    # candidates fetched before MMR filtering
MMR_DIVERSITY = 0.4   # 0 = pure relevance, 1 = pure diversity
MAX_PER_PAGE  = 2     # max chunks from the same page
MIN_SCORE = 0.42  # minimum relevance score to include a chunk

# Singletons — loaded once per process
_model      = None
_collection = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client      = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = client.get_collection(COLLECTION)
    return _collection


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _mmr(
    query_emb: np.ndarray,
    candidate_embs: np.ndarray,
    candidates: list[dict],
    top_k: int,
    diversity: float,
) -> list[dict]:
    """
    Maximal Marginal Relevance — selects top_k chunks that are
    both relevant to the query AND diverse from each other.

    diversity=0  -> pure relevance ranking (same as before)
    diversity=1  -> maximize diversity, ignore relevance
    diversity=0.4 -> balanced (our default)
    """
    selected      = []
    selected_embs = []
    remaining     = list(range(len(candidates)))

    for _ in range(min(top_k, len(candidates))):
        best_idx   = None
        best_score = -float("inf")

        for i in remaining:
            relevance = _cosine_sim(query_emb, candidate_embs[i])
            if selected_embs:
                redundancy = max(_cosine_sim(candidate_embs[i], s) for s in selected_embs)
            else:
                redundancy = 0.0
            mmr_score = (1 - diversity) * relevance - diversity * redundancy
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx   = i

        selected.append(candidates[best_idx])
        selected_embs.append(candidate_embs[best_idx])
        remaining.remove(best_idx)

    return selected


def retrieve(query: str, top_k: int = TOP_K, fetch_k: int = FETCH_K) -> list[dict]:
    """
    Returns top_k diverse, relevant chunks using MMR re-ranking,
    with a limit of MAX_PER_PAGE chunks per page to avoid redundancy.

    Each chunk is a dict:
      {text, chapter, section_letter, section_title, page_start, score}
    """
    model      = _get_model()
    collection = _get_collection()

    query_emb = model.encode([query])[0]

    results = collection.query(
        query_embeddings=[query_emb.tolist()],
        n_results=min(fetch_k, collection.count()),
        include=["documents", "metadatas", "distances", "embeddings"],
    )

    candidates     = []
    candidate_embs = []

    for doc, meta, dist, emb in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
        results["embeddings"][0],
    ):
        candidates.append({
            "text":           doc,
            "chapter":        meta.get("chapter", ""),
            "section_letter": meta.get("section_letter", ""),
            "section_title":  meta.get("section_title", ""),
            "page_start":     meta.get("page_start", ""),
            "score":          round(1 - dist, 3),
        })
        candidate_embs.append(np.array(emb))

    candidate_embs = np.array(candidate_embs)

    # Get more MMR candidates than needed so page filter has room to work
    mmr_results = _mmr(query_emb, candidate_embs, candidates, top_k * 2, MMR_DIVERSITY)

    # Limit to MAX_PER_PAGE chunks per page
    page_counts = {}
    diverse     = []
    for chunk in mmr_results:
        page = chunk["page_start"]
        if page_counts.get(page, 0) < MAX_PER_PAGE:
            diverse.append(chunk)
            page_counts[page] = page_counts.get(page, 0) + 1
        if len(diverse) == top_k:
            break
    #for c in diverse:
    #    print(f"**********  score={c['score']:.3f} | {c['section_title']} | p.{c['page_start']}")
    return [c for c in diverse if c["score"] >= MIN_SCORE]        



def format_context(chunks: list[dict]) -> str:
    """
    Formats retrieved chunks into a numbered context block for the LLM prompt.
    Each chunk gets a [SOURCE N] label that the LLM can cite.
    """
    lines = []
    for i, c in enumerate(chunks, 1):
        citation = (
            f"{c['chapter']}, Section {c['section_letter']}. {c['section_title']}, "
            f"p.{c['page_start']}"
        ).strip(", ")
        lines.append(f"[SOURCE {i}] ({citation})\n{c['text']}")
    return "\n\n---\n\n".join(lines)


def format_citation(chunk: dict) -> str:
    """Short citation string for display in the UI."""
    letter = f"{chunk['section_letter']}. " if chunk["section_letter"] else ""
    return (
        f"{chunk['chapter']} | {letter}{chunk['section_title']} | p.{chunk['page_start']}"
    )

def warmup():
    """Pre-initialize singletons so parallel threads don't race on startup."""
    _get_model()
    _get_collection()

