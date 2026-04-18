# Technical Design Note
## 2026 Medicare NCCI Policy Assistant

**Author:** Raquel Norel, PhD  
**Date:** April 2026  
**Assignment:** AFT Innovation Take-Home — Claritev

---

## 1. Overview

This application provides AI-powered access to the 2026 CMS Medicare National Correct Coding Initiative (NCCI) Coding Policy Manual. It supports two interaction modes:

- **Chat**: RAG-grounded Q&A with inline source citations and page references
- **Policy Insights**: Structured summaries of specific policy topics, grounded in the manual

The system ingests the full 287-page PDF, builds a local vector index, and uses Claude (claude-sonnet-4-20250514) to generate answers strictly grounded in retrieved manual excerpts.

---

## 2. Architecture

```
PDF (287 pages)
     │
     ▼
[ingest.py]
  - pdfplumber extraction
  - Section detection (chapter/section headers)
  - Overlapping chunking (600 tok, 100 overlap)
  - Cosine similarity deduplication (threshold=0.90)
  - Embedding: all-MiniLM-L6-v2 (local, CPU)
  - Storage: ChromaDB (persistent, local)
     │
     ▼
[ChromaDB] ← 402 chunks with metadata
     │
     ▼
[retriever.py]
  - Query embedding (same model)
  - Fetch 15 candidates from ChromaDB
  - MMR re-ranking (diversity=0.4)
  - Per-page limit (max 2 chunks/page)
  - Minimum relevance filter (MIN_SCORE=0.44)
     │
     ▼
[llm.py]
  - Format context with [SOURCE N] labels
  - Claude API call with grounding system prompt
  - Multi-turn conversation support (Chat tab)
     │
     ▼
[app.py]
  - Streamlit UI: Chat + Policy Insights tabs
  - Source expander (only shown when LLM cites sources)
  - Download button for Insights summaries
```

---

## 3. Parsing Strategy

The manual was parsed using `pdfplumber`, which provides reliable text extraction from tagged PDFs. Text was extracted page by page and then processed to detect structural boundaries.

**Chapter detection:** Lines matching patterns like `CHAPTER I`, `Chapter II – Anesthesia Services` were used to identify chapter boundaries.

**Section detection:** Lines matching the pattern `[A-Z]. Title` (e.g., `A. Introduction`, `B. Coding Based on Standards...`) were used to identify section boundaries within chapters.

Each detected section was tagged with metadata: `chapter`, `section_letter`, `section_title`, `page_start`.

**Tradeoff:** This heuristic approach works well for the structured NCCI manual but would need adaptation for less consistently formatted documents.

---

## 4. Chunking Strategy

Sections were split into overlapping chunks with:
- **Chunk size:** ~600 tokens (2400 characters)
- **Overlap:** ~100 tokens (400 characters)

Overlap ensures that content spanning chunk boundaries is not lost. This produced 474 raw chunks from 201 detected sections.

**Known limitation:** Overlap produces chunks that start mid-sentence, which looks truncated in the UI source expander. This is a cosmetic issue and does not affect retrieval or answer quality.

---

## 5. Deduplication

A critical preprocessing step was added after discovering that the NCCI manual repeats boilerplate text verbatim across chapters. For example, the rules for E&M service reporting with modifier 25 appear nearly identically in Chapters I, III, IV, V, VI, VII, VIII, IX, X, and XI.

Without deduplication, the retriever consistently returned multiple near-identical chunks from different chapters, consuming LLM context with redundant information and producing misleading citations.

**Solution:** After embedding all chunks, a pairwise cosine similarity matrix was computed. Any chunk with cosine similarity > 0.90 to an earlier chunk was dropped, keeping the first occurrence (which tends to be from Chapter I — the authoritative general policy chapter).

**Result:** 72 near-duplicate chunks removed, from 474 to 402 unique chunks.

**Threshold choice:** 0.90 was chosen empirically. At 0.95, some duplicates survived. Below 0.85, the risk of removing legitimately similar but distinct chunks increases.

---

## 6. Metadata Design

Each chunk carries:

| Field | Description | Example |
|-------|-------------|---------|
| `chapter` | Chapter label | `Chapter I` |
| `section_letter` | Section letter | `E` |
| `section_title` | Section title | `Modifiers and Modifier Indicators` |
| `page_start` | PDF page number | `30` |
| `chunk_index` | Position within section | `2` |

This metadata enables meaningful citations in the UI (`Chapter I | E. Modifiers and Modifier Indicators | p.30`) and supports future filtering by chapter or section.

---

## 7. Embedding Model

**Model:** `sentence-transformers/all-MiniLM-L6-v2`  
**Dimensions:** 384  
**Runtime:** Local CPU, no API calls required  
**Rationale:** Fast, lightweight, and well-suited for semantic similarity over domain-specific text. For a production system, a domain-adapted biomedical or clinical coding model (e.g., fine-tuned on CPT/ICD terminology) would likely improve retrieval precision.

---

## 8. Retrieval Approach

Retrieval uses a three-stage pipeline:

**Stage 1 — Candidate fetch:** ChromaDB returns the top 15 candidates by cosine similarity to the query embedding.

**Stage 2 — MMR re-ranking:** Maximal Marginal Relevance (MMR) is applied to select chunks that are both relevant to the query and diverse from each other. The diversity parameter (λ=0.4) was chosen to balance relevance and diversity. Pure relevance ranking (λ=0) caused redundant chunks from different chapters to dominate the results.

**Stage 3 — Post-filtering:**
- **Per-page limit:** Maximum 2 chunks per page, to prevent over-representation of a single dense page
- **Minimum score filter:** Chunks with cosine similarity < 0.44 are discarded. This threshold was determined empirically by inspecting the scores of irrelevant chunks returned for specific queries.

**Final output:** Up to 5 diverse, relevant chunks per query.

---

## 9. Citation Approach

Each retrieved chunk is labeled `[SOURCE N]` in the context passed to the LLM. The system prompt instructs Claude to:
- Cite sources inline using `[SOURCE N]` notation
- Use only information from the provided sources
- Explicitly state when the answer is not found — and in that case, not cite any sources

Citations in the UI display chapter, section, and page number, making them directly verifiable against the original PDF.

**Source expander behavior:** The sources panel is only shown when the LLM response contains at least one `[SOURCE` reference. When the LLM indicates it cannot find the answer, no sources are shown.

---

## 10. Model Choice

**Model:** `claude-sonnet-4-20250514`  
**Rationale:** Strong instruction-following for the grounding constraint ("answer only from provided sources"), good performance on structured medical/policy text, and reliable citation behavior.

**System prompts:** Two separate system prompts were used:
- **Chat:** Emphasizes strict grounding, inline citation, and explicit acknowledgment of missing information
- **Insights:** Emphasizes structured output format (Overview, Key Rules, Exceptions, CPT Ranges)

---

## 11. Evaluation Methodology

A gold standard evaluation set of 10 queries was constructed (see `eval_set.md`). Each query includes:
- The question
- Expected answer derived directly from the PDF
- System response
- Citation verification (page number checked against PDF)
- Pass/Fail assessment

Evaluation dimensions:
1. **Factual correctness** — does the answer match the manual?
2. **Citation accuracy** — do cited pages contain the stated information?
3. **Hallucination resistance** — does the system correctly decline out-of-scope questions?
4. **Source diversity** — are citations from meaningfully different sections?

---

## 12. Key Tradeoffs

| Decision | Chosen | Alternative | Tradeoff |
|----------|--------|-------------|----------|
| Vector store | ChromaDB (local) | Pinecone, Weaviate | No infra setup vs. scalability |
| Embeddings | all-MiniLM-L6-v2 (local) | OpenAI text-embedding-3 | Free/private vs. higher quality |
| LLM | Claude Sonnet | GPT-4o, Gemini | Strong instruction-following |
| Chunking | Overlap by section | Semantic chunking | Simpler vs. more coherent chunks |
| Dedup | Cosine similarity | Exact hash | Catches near-duplicates vs. slower |

---

## 13. Failure Modes and Future Improvements

**Known failure modes:**

1. **Overlap artifacts:** Chunks start mid-sentence due to overlap, appearing truncated in the source expander. Does not affect answer quality but reduces UI polish.

2. **Low-relevance 5th source:** For some queries, the 5th retrieved chunk is tangentially related rather than directly relevant (e.g., MUE chunk appearing in an E&M query). The minimum score filter (0.44) mitigates this but does not eliminate it.

3. **Table of contents chunks:** Some chunks contain only table of contents text with page references and no policy content. These occasionally appear as retrieved sources with low but passing scores.

4. **Section detection misses:** The heuristic section parser may miss some headers if formatting is inconsistent, causing two logical sections to be merged into one large chunk.

**Improvements with more time:**

1. **Semantic chunking:** Use an LLM to identify natural semantic boundaries rather than regex-based header detection.

2. **Domain-adapted embeddings:** Fine-tune embeddings on CPT/ICD/NCCI terminology for improved retrieval precision.

3. **Hybrid retrieval:** Combine dense vector search with BM25 keyword search (sparse retrieval) for better handling of specific code numbers (e.g., "CPT 45385").

4. **Re-ranking with a cross-encoder:** Use a cross-encoder model to re-rank retrieved chunks based on full query-document relevance, rather than embedding similarity alone.

5. **Table extraction:** The manual contains structured tables (e.g., Add-on Code Edit Tables) that pdfplumber does not extract well. A dedicated table extraction step would improve coverage of tabular content.

6. **Evaluation automation:** Automate the eval set with LLM-as-judge scoring to enable rapid iteration.

---

## 14. Additional Features (Session 2)

### CPT Analyzer Tab

A third tab was added to support two use cases relevant to Claritev's core business:

**Single code analysis:** Given a CPT code, the system retrieves relevant policy chunks and generates a structured analysis covering: applicable NCCI policies, global surgery indicator, bundling considerations, modifier guidance, and important notes. The retrieval query is enriched with domain terms ("billing rules modifiers bundling global period") to improve recall for code-specific content.

**Code pair compatibility check:** Given two CPT codes, the system analyzes whether they can be reported together. The LLM is prompted to assess: compatibility (Yes/Conditional/No), applicable edit types (mutually exclusive, bundling, MUE), modifier options with specific circumstances, and documentation requirements. A visual compatibility badge (✅/⚠️/❌) is derived by parsing the first 500 characters of the response for keywords.

**Limitation:** The CPT Analyzer provides policy-based analysis grounded in the manual's general coding principles. It does not have access to the actual NCCI PTP edit tables (separate CMS files containing millions of specific code pairs). A production system would combine this policy analysis with a lookup against the actual edit tables.

---

### Conflict Detector Tab

A fourth tab enables multi-code conflict detection — given up to 4 CPT codes, the system analyzes all pair combinations in parallel and produces a conflict summary grid.

**Parallel execution:** With 4 codes there are 6 pairs. Sequential execution would require ~60 seconds (6 × ~10s per pair). All pairs are analyzed concurrently using `concurrent.futures.ThreadPoolExecutor` from the Python standard library, reducing total time to ~10-15 seconds.

**Threading and ChromaDB:** ChromaDB's `PersistentClient` is not thread-safe during initialization. A `warmup()` function was added to `retriever.py` to pre-initialize the embedding model and ChromaDB collection at app startup, before any parallel calls are made. This eliminates the initialization race condition.

**Output:** Summary grid with 🔴/🟡/🟢 per pair, expandable detailed analysis per pair, and a downloadable consolidated .md report.

**Input validation:** CPT codes are validated as exactly 5 numeric digits before analysis is triggered. Invalid codes show a warning and disable the analysis button.

---

## 15. Evaluation Findings and Implications

Formal evaluation against a 10-query gold standard (see `eval_set.md`) revealed the following implications for system design:

**Retrieval depth affects answer quality — not just completeness.** During testing, changing MIN_SCORE from 0.44 to 0.42 for a modifier 59 query changed the response from an overly absolute "No" (1 source, 51% relevance) to a correctly nuanced "Yes, but only under specific criteria" (3 sources). This demonstrates that threshold tuning is a quality issue, not merely a coverage issue. In production, dynamic threshold adjustment based on query type or retrieved score distribution would be preferable to a fixed global threshold.

**Chapter coverage is uneven.** The retriever failed to surface telehealth content from Chapter XIII despite it existing in the manual (HCPCS G0406-G0408, G0425-G0427). Later chapters (XI-XIII) appear underrepresented relative to Chapter I, which dominates retrieval results. This may reflect the section detection heuristic performing less reliably on later chapters, or the embedding model weighting general policy language (common in Chapter I) more heavily than specialty-specific content.

**Chunk boundary placement causes retrieval gaps.** Query 1 (global surgical package) returned a chunk from the middle of Section C rather than its beginning, causing the first several items in the bundled services list to be missed. The overlap strategy ensures continuity within a section but does not guarantee that the section's opening content is retrieved when the query matches content distributed across multiple chunks.

**Hallucination resistance is robust.** Across all 10 queries, the system never fabricated information. For the telehealth query (where content existed but was not retrieved), the system correctly stated it could not find relevant information rather than generating plausible-sounding but unsupported content. For the completely out-of-scope query ("what color is the sky"), the system declined appropriately and contextualized the refusal.

---

## 16. Updated Key Tradeoffs

| Decision | Chosen | Alternative | Tradeoff |
|----------|--------|-------------|----------|
| Vector store | ChromaDB (local) | Pinecone, Weaviate | No infra setup vs. scalability |
| Embeddings | all-MiniLM-L6-v2 (local) | OpenAI text-embedding-3 | Free/private vs. higher quality |
| LLM | Claude Sonnet 4.6 | GPT-4o, Gemini | Strong instruction-following |
| Chunking | Overlap by section | Semantic chunking | Simpler vs. more coherent chunks |
| Dedup | Cosine similarity (0.90) | Exact hash | Catches near-duplicates vs. slower |
| Retrieval | MMR + page limit + score filter | Pure similarity | Diversity vs. slightly lower recall |
| Parallel pairs | ThreadPoolExecutor | Sequential | 6x faster vs. thread safety complexity |
| Score threshold | Fixed MIN_SCORE=0.42 | Dynamic per query | Simple vs. adaptive quality |

---

## 17. Updated Failure Modes and Future Improvements

**Additional known failure modes (from evaluation):**

5. **Uneven chapter coverage:** Chapter XIII content (telehealth codes) was not retrieved despite existing in the manual. Later chapters may be underrepresented due to heuristic section detection or embedding model characteristics.

6. **Fixed MIN_SCORE threshold:** A single global threshold cannot optimally balance precision and recall across all query types. High-specificity queries (rare topics, specific codes) need lower thresholds; broad policy queries may need higher thresholds to filter noise.

7. **Policy-only CPT analysis:** The CPT Analyzer and Conflict Detector provide policy-based analysis without access to the actual NCCI PTP edit tables. This is clearly disclosed in the UI but limits precision for specific code pair lookups.

**Additional improvements with more time:**

7. **Hybrid retrieval (dense + sparse):** Combining vector search with BM25 keyword search would significantly improve recall for specific CPT code numbers (e.g., "G0406", "99292") that may not be well-represented in dense embedding space.

8. **Chapter-aware indexing:** Weight or tag chunks by chapter to enable chapter-specific retrieval when the query context implies a specific specialty area.

9. **Integration with NCCI PTP edit tables:** Download and index the actual CMS edit table files to enable precise lookup of specific code pairs, complementing the policy-based analysis.

10. **Dynamic score thresholding:** Adjust MIN_SCORE based on the score distribution of retrieved candidates rather than using a fixed global value.
