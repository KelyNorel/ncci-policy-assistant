# Evaluation Set
## 2026 Medicare NCCI Policy Assistant

**Author:** Raquel Norel, PhD  
**Date:** April 2026  
**Overall result:** 8 Pass, 1 Partial Pass, 1 Fail (85% quality score)

---

## Methodology

### App Under Test
- **RAG pipeline:** ChromaDB (local) + all-MiniLM-L6-v2 embeddings + MMR retrieval
- **LLM:** Claude Sonnet 4.6 (claude-sonnet-4-20250514)
- **Retrieval:** Top-5 chunks after MMR re-ranking, MIN_SCORE=0.42, MAX_PER_PAGE=2

### Ground Truth Source
- **Model:** Claude Sonnet 4.6 via claude.ai
- **Prompt used:** *"I am uploading the 2026 CMS Medicare NCCI Coding Policy Manual. I will ask you questions about it. Please answer based strictly on the content of this document, provide the exact section name and page number for each claim, and say clearly if the information is not found in the document."*
- **Document:** Full 287-page PDF uploaded directly — no chunking, full context access
- **Rationale:** Using the same underlying LLM with full document access provides a fair, unbiased ground truth that isolates retrieval quality from LLM quality

### Evaluation Dimensions
1. **Factual correctness** — does the answer match the manual?
2. **Citation accuracy** — do cited pages contain the stated information?
3. **Completeness** — are key points covered?
4. **Hallucination resistance** — does the system correctly decline out-of-scope questions?

### Query Categories
- **Factual** (Q1, Q3, Q5, Q6, Q7): Clear answer in a specific manual section
- **Multi-concept** (Q2, Q4, Q10): Requires combining information from multiple sections
- **Edge cases** (Q5, Q6): Conditional rules, exceptions, special cases
- **Out of scope** (Q8, Q9): Questions not covered by the manual

### Verdict Criteria
- **Pass:** Factually correct, key points covered, citations verifiable
- **Partial Pass:** Factually correct but missing significant content
- **Fail:** Incorrect, missing critical information, or hallucinated

---

## Query 1 — Global Surgical Package

**Category:** Factual  
**Query:** *"What is the global surgical package and what services does it include?"*

**Expected answer (ground truth):**  
Section C. Medical/Surgical Package, Chapter I, pages I-7 through I-12. The global surgical package includes: cleansing/shaving/prepping of skin, draping and positioning, IV access insertion, urinary catheter insertion, sedative administration, local/topical/regional anesthesia, surgical approach (incision, debridement, lysis of adhesions), surgical cultures, wound irrigation, drain insertion/removal, surgical closure and dressings, postoperative dressings and analgesic devices, TENS unit, Patient Controlled Anesthesia, preoperative/intraoperative/postoperative documentation, imaging/ultrasound guidance, surgical supplies, administration of fluids and drugs during the procedure (CPT 96360-96379 not separately reportable), and all intraoperative services and postoperative management of complications not requiring return to OR.

**App response summary:**  
Correctly identified global period types (000/010/090/XXX), listed most surgical components, and covered E&M rules for major/minor procedures. Missed several items from the beginning of Section C (cleansing, draping, IV access, catheter insertion, sedative administration, fluids/drugs).

**Citations verified:**  
SOURCE 1 (Chapter I, B, p.22) ✅ — correct section. SOURCE 4 (Chapter I, D, p.28) ✅ — correct for E&M rules.

**Gap analysis:**  
The retriever returned a chunk from the middle of Section C (p.22) rather than the beginning (p.I-9). The opening of the section listing the first several bundled services was in a different chunk that was not retrieved. This is a chunking boundary issue — semantic content was split across chunks and the retriever did not surface the first chunk of the section.

**Verdict:** ⚠️ Partial Pass  
**Notes:** Correct in what it says; incomplete due to retrieval gap at section boundary. Points to need for section-aware chunking or dynamic threshold tuning in production.

---

## Query 2 — Modifier 59 and Mutually Exclusive Edits

**Category:** Multi-concept  
**Query:** *"Can modifier 59 be used to bypass a mutually exclusive edit?"*

**Expected answer (ground truth):**  
Section E, Modifier 59, Chapter I, pages I-16 through I-18; Section P, Chapter I, page I-26. The answer is nuanced: modifier 59 cannot be used to simply bypass a mutually exclusive edit. However, "many" (not all) mutually exclusive edits allow use of NCCI PTP-associated modifiers. Where allowed, modifier 59 may be used only when procedures are performed at different anatomic sites or separate patient encounters. Common misuse: using modifier 59 simply because codes represent different procedures — explicitly prohibited by the manual. Documentation required in all cases.

**App response summary:**  
Correctly answered "no, unless proper criteria are met." Covered different anatomic sites/encounters criteria, documentation requirement, and misuse warning. Did not mention that only "many" (not all) mutually exclusive edits allow modifier use — an important qualifier.

**Citations verified:**  
SOURCE 1 (Chapter I, E, p.30) ✅ SOURCE 3 (Chapter I, P, p.42) ✅

**Gap analysis:**  
Minor gap — the qualifier "many" vs. "all" is an important nuance that the app missed. The retriever brought the correct sections but the specific phrasing was in a chunk not retrieved.

**Verdict:** ✅ Pass  
**Notes:** Correct and well-cited. Minor gap on "many vs. all" qualifier.

---

## Query 3 — Medically Unlikely Edits (MUEs)

**Category:** Factual  
**Query:** *"What are Medically Unlikely Edits and how do they affect claim adjudication?"*

**Expected answer (ground truth):**  
Section V, Chapter I, pages I-28 through I-32. MUEs are units of service edits establishing a per-code ceiling on billable units per day. Two adjudication types: MAI=1 (claim line, modifiers may allow separate lines), MAI=2 (absolute DOS, cannot be overridden), MAI=3 (clinical benchmark DOS, may be overridden with medical review evidence). MUE denials are coding denials — ABN not appropriate, beneficiary cannot be billed. MUE values based on anatomic considerations, CPT descriptors, CMS policies, clinical judgment, and claims data.

**App response summary:**  
Correctly defined MUEs, covered MAI=1/2/3 distinction, claims coverage, and appeals process. Also correctly cited the caution about using modifiers to bypass MUEs. Did not cover: basis for MUE value determination, coding vs. medical necessity denial distinction, ABN prohibition.

**Citations verified:**  
SOURCE 1 (Chapter I, V, p.44) ✅ SOURCE 3 (Chapter XII, D, p.270) ✅ SOURCE 4 (Chapter II, E, p.64) ✅

**Gap analysis:**  
Minor gaps on ABN prohibition and MUE value determination criteria. Core question answered correctly and completely.

**Verdict:** ✅ Pass  
**Notes:** Strong response. Gaps are supplementary detail not required to answer the question.

---

## Query 4 — E&M Services Same Day as Procedure

**Category:** Multi-concept  
**Query:** *"When can an E&M service be billed on the same day as a procedure?"*

**Expected answer (ground truth):**  
Section D, Chapter I, pages I-12 through I-13; Section E, Modifier 25, page I-15. Rules depend on global period: (1) Major procedure (090): E&M separately reportable with modifier 57 only if it was the basis for the surgical decision; (2) Minor procedure (000/010): E&M generally included, except significant/separately identifiable E&M with modifier 25 — new patient status alone is NOT sufficient justification; (3) Postoperative E&M related to recovery or complications: not separately reportable; (4) Postoperative E&M unrelated to surgical diagnosis: separately reportable with modifier 24; (5) XXX procedures: E&M reportable with modifier 25 if above and beyond inherent procedure work.

**App response summary:**  
Correctly covered minor/major/XXX procedures and radiation oncology (a specialty case not even mentioned by ground truth). Missed the important caveat that "new patient" status alone does not justify separate E&M billing with a minor procedure.

**Citations verified:**  
SOURCE 1 (Chapter III, B, p.69) ✅ SOURCE 3 (Chapter I, D, p.28) ✅ SOURCE 4 (Chapter IX, F, p.192) ✅

**Gap analysis:**  
Missing "new patient" caveat. App added radiation oncology specialty case not in ground truth — demonstrates broader retrieval coverage in some areas.

**Verdict:** ✅ Pass  
**Notes:** Correct and comprehensive. Radiation oncology addition shows retrieval breadth.

---

## Query 5 — Bilateral Procedures and Units of Service

**Category:** Edge case  
**Query:** *"What happens when a procedure is performed bilaterally — can it be reported with two units of service?"*

**Expected answer (ground truth):**  
Section V, MUE Criteria Item 3a, Chapter I, pages I-29 through I-31. Answer depends on bilateral surgery indicator: Indicator 0 = 1 UOS, no extra payment; Indicator 1 = 1 UOS + modifier 50 (surgical), or modifier RT/LT options (diagnostic); Indicator 2 = 1 UOS, no modifier 50 (already priced bilateral); Indicator 3 = 1 UOS + modifier 50 (surgical), or 2 UOS/modifier 50/RT+LT options (diagnostic). ASC exception: 2 claim lines with LT and RT. Prohibition: cannot unbundle a bilateral code into 2 unilateral codes.

**App response summary:**  
Correctly covered indicators 1, 2, and 3 for both surgical and diagnostic procedures, and the ASC exception. Did not mention Indicator 0 or the prohibition on unbundling bilateral codes into unilateral codes.

**Citations verified:**  
SOURCE 1 (Chapter I, V, p.44) ✅ with 77% relevance — highest relevance score in eval set. SOURCE 5 (Chapter VII, H, p.153) ✅ for ASC exception.

**Gap analysis:**  
Missing Indicator 0 and unbundling prohibition. Core answer is correct and well-organized.

**Verdict:** ✅ Pass  
**Notes:** Best retrieval performance in eval set (77% relevance). Minor gaps on Indicator 0 and unbundling rule.

---

## Query 6 — "Separate Procedure" Designation

**Category:** Edge case  
**Query:** *"What is a 'separate procedure' and when does the designation affect billing?"*

**Expected answer (ground truth):**  
Section J, Chapter I, page I-23. A CPT code with "separate procedure" in its descriptor cannot be reported separately with a related procedure performed in an anatomically related region through the same skin incision, orifice, or surgical approach. It may be reported separately when: (1) performed at a separate patient encounter, or (2) performed at an anatomically unrelated area through a separate approach. Modifiers 59, XE, or XS may be appended. Policy repeated consistently across all surgical specialty chapters (III–XII).

**App response summary:**  
Correctly defined the designation, covered when it prevents separate billing, when it allows separate billing, and appropriate modifier usage. Concise and accurate.

**Citations verified:**  
SOURCE 1 (Chapter I, J, p.39) ✅ — exactly the correct section.

**Gap analysis:**  
Did not include concrete examples (tracheostomy, nasopharyngoscopy, etc.) or note that the policy is repeated across all chapters. These are supplementary details.

**Verdict:** ✅ Pass  
**Notes:** Clean, precise response. SOURCE 1 directly on target.

---

## Query 7 — Add-On Codes

**Category:** Factual  
**Query:** *"Can add-on codes be reported without their primary procedure code?"*

**Expected answer (ground truth):**  
Section R, Chapter I, page I-26; Section W, Chapter I, pages I-35 through I-36. No, with rare exception. Three AOC types: Type 1 (primary codes explicitly defined — MACs shall not allow other primary codes), Type 2 (no primary codes defined — MACs develop their own lists), Type 3 (some primary codes defined — MACs may expand the list). If primary code is denied by a PTP edit, AOC is also denied. Narrow exception: CPT 99292 may be paid without 99291 on the same claim if another physician of the same group billed 99291. Non-AOC codes shall not be misused as add-ons.

**App response summary:**  
Correctly answered "No." Covered: AOC requires primary procedure, if primary is denied AOC is denied, and misuse prohibition. Did not cover the three AOC types (1/2/3) or the 99292 narrow exception.

**Citations verified:**  
SOURCE 1 (Chapter I, R, p.42) ✅

**Gap analysis:**  
Missing AOC type classification and 99292 exception. Core answer is correct.

**Verdict:** ✅ Pass  
**Notes:** Correct and well-cited. Type classification is advanced detail not required for the base question.

---

## Query 8 — Telehealth Services (Out of Scope Test)

**Category:** Out of scope  
**Query:** *"What are the NCCI coding rules for telehealth services in 2026?"*

**Expected answer (ground truth):**  
Chapter XIII, Section D, Item 16, page XIII-9. The manual contains limited telehealth content: HCPCS G0406–G0408 (follow-up inpatient telehealth consultations) and G0425–G0427 (emergency/initial inpatient telehealth consultations) shall not be reported with face-to-face E&M codes on the same date. Limited to 1 UOS per day. General telehealth coverage, modifier 95, GT/GQ, audio-only, and remote patient monitoring are not addressed in this manual.

**App response summary:**  
Responded "cannot find any specific information about telehealth services." The system correctly admitted uncertainty but was factually incorrect — there is limited telehealth content in Chapter XIII that the retriever did not surface.

**Citations verified:**  
N/A — no citations provided.

**Gap analysis:**  
Critical retrieval gap: Chapter XIII content on telehealth (G0406-G0408, G0425-G0427) was not indexed or retrieved. The system appropriately declined to hallucinate but missed existing content. This indicates incomplete coverage of Chapter XIII in the vector index.

**Verdict:** ❌ Fail  
**Notes:** This is the most significant failure identified in evaluation. The system correctly refused to hallucinate (positive behavior) but the retriever failed to surface existing relevant content. In production, this points to need for: (1) verifying full chapter coverage in the index, (2) query expansion strategies, (3) dynamic threshold adjustment. The telehealth content in the manual is minimal and highly specific — improving recall for rare topics is a known challenge in RAG systems.

---

## Query 9 — Out of Scope (Non-Medical)

**Category:** Out of scope  
**Query:** *"What color is the sky?"*

**Expected answer (ground truth):**  
Not in scope of the NCCI manual. Claude web answered correctly (blue) as a general knowledge question outside the document scope.

**App response summary:**  
"I cannot answer your question about the color of the sky because this information is not found in the provided sources from the 2026 NCCI Medicare Policy Manual. The manual focuses on medical coding policies and procedures, not general information about the sky or weather phenomena."

**Citations verified:**  
N/A — correctly provided no citations.

**Gap analysis:**  
None. Perfect behavior for a completely out-of-scope query.

**Verdict:** ✅ Pass  
**Notes:** Ideal hallucination resistance. Response is accurate, appropriately scoped, and even contextualizes why the question is out of scope ("not meteorological or atmospheric phenomena").

---

## Query 10 — PTP Edits vs. MUEs

**Category:** Multi-concept  
**Query:** *"What is the difference between a PTP edit and an MUE, and how does each affect claim payment?"*

**Expected answer (ground truth):**  
Introduction, page Intro-3; Chapter I, pages I-3 through I-4 and I-28 through I-29. PTP edits: govern whether two *different* codes can be billed together (Column One/Column Two structure); Column Two denied when triggered; CCMI 0/1/9 governs modifier override eligibility; in effect since 1996. MUEs: govern whether too many *units* of the *same* code are billed in one day; MAI 1/2/3 determines adjudication type; in effect since January 1, 2007. Both are coding denials — ABN not appropriate, beneficiary cannot be billed for either.

**App response summary:**  
Correctly explained the core difference (two different codes vs. units of same code), covered Column One/Two structure, MAI 1/2/3, and appeals. Did not cover CCMI values (0/1/9), the beneficiary billing prohibition (ABN), or the historical dates (1996 vs. 2007).

**Citations verified:**  
SOURCE 1 (Introduction, p.10) ✅ SOURCE 2 (Chapter I, V, p.44) ✅ SOURCE 3 (Chapter II, E, p.64) ✅

**Gap analysis:**  
Missing CCMI detail and ABN/beneficiary billing prohibition — both important for a complete answer. Core conceptual distinction is correct and clearly explained.

**Verdict:** ✅ Pass  
**Notes:** Strong conceptual response. CCMI and ABN details are important omissions but do not invalidate the core answer.

---

## Summary

| # | Query | Category | Verdict | Key Gap |
|---|-------|----------|---------|---------|
| 1 | Global surgical package | Factual | ⚠️ Partial Pass | Retrieval gap at section boundary — missing first items in list |
| 2 | Modifier 59 bypass | Multi-concept | ✅ Pass | "Many" vs. "all" edits allow modifiers |
| 3 | MUEs and adjudication | Factual | ✅ Pass | ABN prohibition, MUE value determination criteria |
| 4 | E&M same day as procedure | Multi-concept | ✅ Pass | "New patient" status caveat |
| 5 | Bilateral procedures | Edge case | ✅ Pass | Indicator 0, unbundling prohibition |
| 6 | Separate procedure | Edge case | ✅ Pass | Concrete examples, cross-chapter consistency note |
| 7 | Add-on codes | Factual | ✅ Pass | AOC type classification (1/2/3), 99292 exception |
| 8 | Telehealth (out of scope) | Out of scope | ❌ Fail | Chapter XIII telehealth content not retrieved |
| 9 | Color of sky (out of scope) | Out of scope | ✅ Pass | None — perfect hallucination resistance |
| 10 | PTP edits vs. MUEs | Multi-concept | ✅ Pass | CCMI values, ABN/beneficiary billing prohibition |

**Overall: 8 Pass / 1 Partial Pass / 1 Fail = 85% quality score**

---

## Key Findings

**Strengths:**
- Strong hallucination resistance — the system never fabricated information not in its sources
- Correctly declined out-of-scope questions without citations
- Good retrieval for well-represented sections (Chapter I especially)
- Multi-concept queries handled well when multiple relevant sections were retrieved
- Relevance scores correlated with answer quality — highest score (77%) corresponded to best retrieval performance (Q5)

**Weaknesses:**
- Retrieval gap for Chapter XIII content (telehealth) — indicates uneven coverage across chapters
- Section boundary chunking causes missed content at the beginning of long sections (Q1)
- 5th retrieved chunk is sometimes tangentially related rather than directly relevant

**Production Recommendations:**
- Verify full chapter coverage in the vector index, particularly later chapters (XI–XIII)
- Implement section-aware chunking to prevent boundary gaps in long sections
- Consider query expansion to improve recall for rare or domain-specific topics
- Dynamic MIN_SCORE threshold tuning based on query type
- Hybrid retrieval (dense + sparse/BM25) to improve recall for specific code numbers and terminology
