# Build Journal
## 2026 Medicare NCCI Policy Assistant

**Author:** Raquel Norel, PhD  
**Date:** April 2026  
**Total build time:** ~8 hours  
**AI tools used:** Claude (claude.ai) as primary coding assistant

---

## Overview

This journal documents how I used AI tools during development, where they helped, where they made mistakes, and how I validated or corrected them.

The entire development session was conducted as a conversation with Claude on claude.ai. Claude generated initial code for all modules, which I then tested, debugged, and iteratively refined. The workflow was highly collaborative — I drove the architectural decisions and validated every output against actual behavior, while Claude accelerated implementation.

---

## Session Log

### Phase 1 — Project setup and PDF exploration (30 min)

Before writing any code, I used Claude to analyze the PDF structure. We ran `pdftotext` on the first 20 pages to understand how the manual was organized — chapter headers, section letter patterns (A., B., C...), footer noise, and boilerplate text.

**AI helped with:** Identifying regex patterns for chapter and section detection from raw text samples I pasted into the conversation.

**My contribution:** Recognizing that the manual had a very consistent structure that would support heuristic parsing without needing an LLM-based approach.

---

### Phase 2 — ingest.py (1.5 hrs)

Claude generated the initial `ingest.py` with page extraction, section splitting, chunking, embedding, and ChromaDB indexing.

**First error — duplicate IDs:**  
On the first run, ChromaDB raised a `DuplicateIDError`. The issue was that multiple sections with no section letter (e.g., intro sections) on the same page generated identical IDs. Claude's fix: add a global section index (`sec_idx`) as a prefix to the ID. I applied the fix and re-ran successfully.

**Discovery — boilerplate duplication:**  
During sanity checking, I noticed that queries were returning near-identical chunks from different chapters. Investigation revealed that the NCCI manual repeats E&M rules verbatim across all surgery chapters. This was a real retrieval quality problem.

**First approach — fingerprint deduplication:**  
Claude proposed deduplication by matching the first 200 characters of each chunk. I pushed back — this felt too brittle and wouldn't catch near-duplicates with slightly different starts.

**Better approach — cosine similarity deduplication:**  
I suggested using cosine similarity instead. Claude implemented it: embed all chunks, compute the full similarity matrix, drop any chunk with similarity > 0.90 to an earlier chunk. Result: 72 duplicates removed, from 474 to 402 chunks. The sanity check confirmed retrieval quality was preserved.

**Key lesson:** AI-generated code works, but domain understanding (knowing *why* the duplicates existed) came from me examining the actual PDF content.

---

### Phase 3 — retriever.py (1.5 hrs)

Claude generated a basic retriever that fetched top-5 chunks by cosine similarity. During testing I observed that retrieved sources were still sometimes redundant — the same E&M boilerplate appearing from 4 different chapters despite deduplication (because some near-duplicates had similarity just below 0.90).

**MMR implementation:**  
I asked Claude to implement Maximal Marginal Relevance (MMR). Claude generated a clean numpy-based implementation that fetches 15 candidates and re-ranks them to balance relevance and diversity. No additional libraries needed.

**Per-page limit:**  
Even after MMR, I observed 3 chunks from the same page (p.30, the Modifiers section) appearing in one query. I proposed a simple fix: limit to max 2 chunks per page. Claude implemented it in a few lines.

**Minimum score filter:**  
For some queries, the 5th retrieved chunk was clearly irrelevant. I added debug prints to inspect cosine similarity scores of all retrieved chunks, identified that irrelevant chunks had scores around 0.40, and set `MIN_SCORE = 0.44` as a cutoff. This was determined empirically from observed score distributions.

**AI mistake caught:** Claude initially wrote `any(f"[SOURCE" in response)` to check if the LLM cited any sources — this is a Python bug (`any()` on a string iterates characters, not words, and returns a bool, not a bool of bools). The error appeared as `TypeError: 'bool' object is not iterable` at runtime. Fix: `"[SOURCE" in response`.

---

### Phase 4 — llm.py (45 min)

Claude generated both system prompts (Chat and Insights) and the API wrapper functions.

**Iteration on the grounding prompt:**  
The initial system prompt instructed the model to say "so clearly" when it couldn't find an answer. In testing, the model correctly declined to answer but still showed the sources expander in the UI (because sources are always retrieved regardless of the answer).

**Two-part fix:**  
1. Added to the system prompt: "do not cite any sources" when the answer is not found  
2. Modified `app.py` to only show the sources expander when `"[SOURCE" in response`

**Hallucination test results:**  
- "What are the NCCI coding rules for telehealth services in 2026?" → Correctly declined, no sources shown
- "What color is the sky?" → Declined with appropriate context: *"the manual focuses on Medicare coding policies and procedures, not meteorological or atmospheric phenomena"*

The model stayed strictly within its grounding constraints in all tests.

---

### Phase 5 — app.py (1.5 hrs)

Claude generated the full Streamlit app with two tabs. The structure was correct on the first attempt.

**Observations during testing:**

1. The Chat tab correctly maintained multi-turn context — follow-up questions referenced previous answers appropriately.

2. The Policy Insights tab generated well-structured summaries with the Overview / Key Rules / Exceptions / CPT Ranges format.

3. The download button for Insights summaries worked correctly on first test.

**UI refinement:**  
The sources expander initially always appeared, even for "I don't know" responses. Fixed as described above.

---

### Phase 6 — Debugging and parameter tuning (1 hr)

Most of this phase involved running queries, observing retrieved sources, printing scores, and adjusting parameters:

| Parameter | Initial | Final | Reason |
|-----------|---------|-------|--------|
| Cosine dedup threshold | 0.95 | 0.90 | 0.95 left some near-duplicates |
| MMR diversity | — | 0.40 | Balance relevance and diversity |
| FETCH_K | 5 | 15 | Need more candidates for MMR + page filter |
| MAX_PER_PAGE | — | 2 | Prevent 3+ chunks from same dense page |
| MIN_SCORE | — | 0.44 | Empirically determined from score inspection |

---

## Where AI Helped Most

- **Boilerplate generation:** All file skeletons, argument parsers, ChromaDB setup, Streamlit structure
- **Algorithm implementation:** MMR, cosine similarity matrix, deduplication logic — correct on first attempt
- **Error diagnosis:** Fast identification of the duplicate ID error and the `any()` bug
- **Documentation:** Draft generation of design note, build journal, and eval set

## Where AI Made Mistakes or Needed Correction

- **Fingerprint deduplication:** Claude's first dedup approach (first 200 chars) was too brittle. I proposed cosine similarity instead.
- **`any()` bug:** `any(f"[SOURCE" in response)` — subtle Python error that only appeared at runtime
- **File naming typo:** Claude saved `retriever.py` as `retriever.pl` (Perl extension) in one iteration — caught immediately on import

## What I Validated Manually

- Every retrieved source was checked against the actual PDF page to verify citations
- Score distributions were inspected empirically to set thresholds
- Hallucination resistance was tested with out-of-scope queries
- Multi-turn conversation behavior was tested with follow-up questions
- The Policy Insights tab was tested across multiple topic categories

## Reflection

AI-assisted development significantly accelerated implementation — the full working pipeline was built in ~8 hours, which would have taken 2-3x longer coding from scratch. However, the quality of the final system depended critically on domain understanding, empirical testing, and iterative refinement that required human judgment throughout. AI tools are most effective as an accelerator, not a replacement for engineering rigor.

---

## Session 2 — Saturday, April 19, 2026 (~3 hours)

### Phase 7 — CPT Analyzer tab (45 min)

Added a third tab to the app: CPT Analyzer. Two modes: single code policy lookup and code pair compatibility check.

**Design decision:** Two new functions in `llm.py` — `analyze_single_cpt()` and `analyze_cpt_pair()` — with separate system prompts tailored to each use case. The pair analysis prompt instructs Claude to assess compatibility, identify edit types (mutually exclusive, bundling, MUE), recommend modifiers, and specify documentation requirements.

**Compatibility badge:** The pair mode shows a visual 🟢/🟡/🔴 badge based on parsing the first 500 characters of the LLM response for keywords ("yes", "conditional", "no"). Simple heuristic, works reliably in testing.

**AI contribution:** Claude generated both system prompts and the Streamlit tab structure on first attempt. The badge logic was my suggestion — Claude implemented it.

**Tested with:** CPT pair 99213 + 20610. Response correctly identified modifier 25 as the appropriate modifier, explained bundling considerations, and noted documentation requirements. Cited Chapter I, E (Modifiers, p.30) and Chapter I, J (Separate Procedure, p.39).

---

### Phase 8 — Conflict Detector tab (1 hr)

Added a fourth tab: multi-code conflict detector. User enters up to 4 CPT codes; system analyzes all pairs in parallel and produces a conflict summary grid.

**Key technical decision — parallel execution:** With 4 codes there are 6 pairs, each requiring a retrieve + LLM call. Sequential execution would take ~60 seconds. Used `concurrent.futures.ThreadPoolExecutor` (standard library, no extra dependencies) to run all pairs simultaneously. Execution time reduced to ~10-15 seconds.

**Threading issue encountered:** ChromaDB raised `ValueError: Could not connect to tenant default_tenant` when multiple threads tried to initialize the client simultaneously. Root cause: the `_get_collection()` singleton was not yet initialized when threads started, causing a race condition.

**Fix:** Added a `warmup()` function to `retriever.py` that pre-initializes both the embedding model and ChromaDB collection at app startup, before any parallel calls. Called `warmup()` once at the top of `app.py`. This eliminated the race condition.

**AI contribution:** Claude generated the parallel execution pattern and the worker function correctly. The race condition was caught at runtime — Claude diagnosed it correctly and proposed the warmup fix.

**Tested with:** 4 codes: 99213, 20610, 97140, 27447 (6 pairs). Results:
- 99213 × 20610 → 🟢 Compatible (modifier 25 required)
- 20610 × 27447 → 🟡 Review needed (insufficient specific information)
- 99213 × 27447 → 🟢 Compatible (modifier 25 required)
- 20610 × 97140 → 🟡 Conditional (modifier 59/XS if different anatomic site)
- 99213 × 97140 → 🟡 Conditional (modifier 25 on E&M)
- 97140 × 27447 → 🟡 Conditional (modifier 59/XS if different site)

Download button generates a consolidated .md report with all 6 pair analyses.

---

### Phase 9 — Input validation (15 min)

Added CPT code validation to both CPT Analyzer and Conflict Detector tabs. A valid CPT code is exactly 5 numeric digits. Invalid codes show a warning and disable the analysis button.

**AI contribution:** One-liner validation: `code.isdigit() and len(code) == 5`. Straightforward implementation.

---

### Phase 10 — UI polish and consistency (30 min)

Several small improvements across all tabs:

- Changed "Sources used" → "Manual sections used" in Chat tab for consistency with other tabs
- Added relevance score (cosine similarity %) to Chat tab source expander, matching Insights and CPT Analyzer display
- Added `warmup()` call at app startup to pre-load model and ChromaDB
- Added `--server.fileWatcherType none` flag to suppress transformer module inspection warnings at startup
- Fixed bug: `any(f"[SOURCE" in response)` → `"[SOURCE" in response` (Python error — `any()` on a string iterates characters, not words)

---

### Phase 11 — Evaluation (1 hr)

Conducted formal evaluation against a 10-query gold standard set. Ground truth generated using Claude Sonnet 4.6 via claude.ai with the full 287-page PDF uploaded directly (no chunking, full context).

**Evaluation methodology:** Same LLM (Claude Sonnet 4.6), different retrieval — isolates retrieval quality from LLM quality. Ground truth prompt: *"I am uploading the 2026 CMS Medicare NCCI Coding Policy Manual. Please answer based strictly on the content of this document, provide the exact section name and page number for each claim, and say clearly if the information is not found in the document."*

**Results: 8 Pass / 1 Partial Pass / 1 Fail = 85% quality score**

**Key finding — telehealth failure (Q8):** The system responded "cannot find specific information" to a telehealth query. Ground truth revealed there is limited but real telehealth content in Chapter XIII (HCPCS G0406-G0408, G0425-G0427). The retriever did not surface this content. The system correctly refused to hallucinate (positive behavior) but missed existing content. This points to incomplete coverage of later chapters in the index and is documented as a known limitation.

**Key finding — partial pass on surgical package (Q1):** The retriever returned a chunk from the middle of Section C rather than the beginning. The first several items in the bundled services list were in a different chunk not retrieved. Classic chunk boundary issue.

**Key finding — MIN_SCORE threshold impact on answer quality:** During testing, changing MIN_SCORE from 0.44 to 0.42 changed a chat response from "No, modifier 59 cannot be used" (1 source) to "Yes, but only under specific criteria" (3 sources). The 3-source response was more accurate. This empirically demonstrates that retrieval depth directly affects answer quality — not just completeness.

**Observation — speed:** The RAG app responded in 3-5 seconds per query. Claude web with full PDF took 30-60 seconds. This is a key production advantage of the RAG approach.

---

## Summary of AI Tool Usage Across Both Sessions

### Where AI Helped Most
- All boilerplate code generation (Streamlit structure, ChromaDB setup, argument parsers)
- Algorithm implementation: MMR, cosine similarity matrix, deduplication, ThreadPoolExecutor pattern
- System prompt engineering for Chat, Insights, CPT Analyzer (single and pair), and Conflict Detector
- Documentation drafts (design note, build journal, eval set, README)
- Fast diagnosis of runtime errors (duplicate IDs, race condition, `any()` bug)

### Where Human Judgment Was Essential
- Identifying the boilerplate duplication problem by reading actual PDF content
- Proposing cosine similarity deduplication over Claude's initial fingerprint approach
- Deciding to use MMR after observing redundant sources in production
- Proposing the per-page limit after observing 3 chunks from the same page
- Empirically determining MIN_SCORE=0.42 by inspecting actual score distributions
- Designing the Conflict Detector feature concept (domain relevance to Claritev's business)
- Evaluating output quality against the actual PDF content

### Reflection
The two-session build demonstrates a clear pattern: AI tools excel at implementation speed and boilerplate, while domain understanding, quality judgment, and architectural decisions required human expertise throughout. The most valuable contributions came from iterative human-AI collaboration — observing behavior, diagnosing root causes, proposing fixes, and validating results against ground truth.
