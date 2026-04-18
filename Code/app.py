"""
app.py
Streamlit app for the 2026 NCCI Medicare Policy Manual AI Assistant.
Four tabs:
  1. Chat             — RAG-grounded Q&A with source citations
  2. Policy Insights  — Structured policy summaries by topic
  3. CPT Analyzer     — Single code or code pair NCCI analysis
  4. Conflict Detector — Multi-code bundling conflict detection (up to 4 codes)
"""

import streamlit as st
import concurrent.futures
import itertools
from retriever import retrieve, format_context, format_citation, warmup
from llm import chat, get_insights, analyze_single_cpt, analyze_cpt_pair

import warnings
warnings.filterwarnings("ignore")
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

warmup()  # pre-load model and ChromaDB before any parallel calls

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NCCI Policy Assistant",
    page_icon="🏥",
    layout="wide",
)

st.title("🏥 2026 Medicare NCCI Policy Assistant")
st.caption("AI-powered exploration of the CMS National Correct Coding Initiative Policy Manual")

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_chat, tab_insights, tab_cpt, tab_conflict = st.tabs([
    "💬 Chat", "🔍 Policy Insights", "🔎 CPT Analyzer", "⚠️ Conflict Detector"
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — CHAT
# ════════════════════════════════════════════════════════════════════════════
with tab_chat:
    st.subheader("Ask anything about the NCCI Manual")
    st.markdown(
        "Ask questions about coding policies, modifiers, procedures, and more. "
        "All answers are grounded in the manual with page citations."
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "sources" not in st.session_state:
        st.session_state.sources = {}

    # Display chat history
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and i in st.session_state.sources:
                if "[SOURCE" in msg["content"]:
                    with st.expander("📚 Manual sections used", expanded=False):
                        for j, chunk in enumerate(st.session_state.sources[i], 1):
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.markdown(f"**[SOURCE {j}]** `{format_citation(chunk)}`")
                                st.caption(chunk["text"][:300] + "…")
                            with col2:
                                st.metric("Relevance", f"{chunk['score']:.0%}")

    # Chat input
    if prompt := st.chat_input("E.g. What are the rules for reporting add-on codes?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching manual…"):
                chunks  = retrieve(prompt, top_k=5)
                context = format_context(chunks)
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1]
                ]
                response = chat(prompt, context, history=history)

            st.markdown(response)

            turn_index = len(st.session_state.messages)
            if "[SOURCE" in response:
                with st.expander("📚 Manual sections used", expanded=False):
                    for j, chunk in enumerate(chunks, 1):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.markdown(f"**[SOURCE {j}]** `{format_citation(chunk)}`")
                            st.caption(chunk["text"][:300] + "…")
                        with col2:
                            st.metric("Relevance", f"{chunk['score']:.0%}")

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.session_state.sources[turn_index] = chunks

    if st.session_state.messages:
        if st.button("🗑️ Clear chat", key="clear_chat"):
            st.session_state.messages = []
            st.session_state.sources  = {}
            st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — POLICY INSIGHTS
# ════════════════════════════════════════════════════════════════════════════
with tab_insights:
    st.subheader("Structured Policy Summaries")
    st.markdown(
        "Select a topic to get a structured summary of the relevant NCCI policies, "
        "key rules, exceptions, and applicable CPT code ranges — grounded in the manual."
    )

    TOPICS = {
        "— Select a topic —": None,
        "General Correct Coding Policies": "General correct coding policies and principles",
        "Mutually Exclusive Procedures": "Mutually exclusive procedures and when they can be separately reported",
        "Add-on Codes": "Add-on codes: definition, rules, and reporting requirements",
        "Modifiers and Modifier Indicators": "NCCI PTP-associated modifiers and modifier indicators",
        "Medically Unlikely Edits (MUEs)": "Medically Unlikely Edits: definition, purpose, and adjudication",
        "Evaluation & Management (E&M) Services": "E&M services coding policies and modifiers",
        "Anesthesia Services": "Anesthesia coding policies including monitored anesthesia care",
        "Medical/Surgical Package": "What is included in the global surgical package",
        "Separate Procedure Definition": "CPT separate procedure definition and implications",
        "Musculoskeletal Surgery Coding": "Coding policies for musculoskeletal surgery (CPT 20000-29999)",
        "Cardiovascular Surgery Coding": "Coding policies for cardiovascular procedures (CPT 30000-39999)",
        "Endoscopy and Laparoscopy": "Endoscopic and laparoscopic procedure coding rules",
        "Radiology Services": "Radiology coding policies and supervision requirements",
        "Laboratory and Pathology": "Laboratory panel and pathology coding policies",
    }

    selected_label = st.selectbox("Choose a policy topic:", list(TOPICS.keys()))
    custom_topic   = st.text_input(
        "…or enter a custom topic:",
        placeholder="E.g. bilateral procedure modifiers",
    )

    active_topic = None
    if custom_topic.strip():
        active_topic = custom_topic.strip()
    elif TOPICS.get(selected_label):
        active_topic = TOPICS[selected_label]

    generate_btn = st.button("Generate Policy Summary", type="primary", disabled=not active_topic)

    if generate_btn and active_topic:
        with st.spinner(f"Retrieving and summarizing: {active_topic}…"):
            chunks  = retrieve(active_topic, top_k=6)
            context = format_context(chunks)
            summary = get_insights(active_topic, context)

        st.markdown("---")
        st.markdown(summary)

        with st.expander("📚 Manual sections used", expanded=True):
            for j, chunk in enumerate(chunks, 1):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**[SOURCE {j}]** `{format_citation(chunk)}`")
                    st.caption(chunk["text"][:250] + "…")
                with col2:
                    st.metric("Relevance", f"{chunk['score']:.0%}")

        st.download_button(
            label="⬇️ Download summary (.md)",
            data=summary,
            file_name=f"ncci_summary_{active_topic[:40].replace(' ','_')}.md",
            mime="text/markdown",
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — CPT ANALYZER
# ════════════════════════════════════════════════════════════════════════════
with tab_cpt:
    st.subheader("CPT Code NCCI Analyzer")
    st.markdown(
        "Enter one CPT code to understand applicable NCCI policies, "
        "or two codes to analyze whether they can be reported together."
    )

    mode = st.radio(
        "Analysis mode:",
        ["Single code — policy lookup", "Code pair — compatibility check"],
        horizontal=True,
    )

    if mode == "Single code — policy lookup":
        col1, _ = st.columns([1, 2])
        with col1:
            code = st.text_input(
                "CPT Code",
                placeholder="e.g. 99213",
                max_chars=10,
            ).strip()

        if code and not (code.isdigit() and len(code) == 5):
            st.warning("⚠️ Invalid CPT code. Must be 5 digits (e.g. 99213).")
        analyze_btn = st.button("Analyze Code", type="primary", disabled=not code or not (code.isdigit() and len(code) == 5))

        if analyze_btn and code:
            query = f"CPT code {code} billing rules modifiers bundling global period"
            with st.spinner(f"Analyzing CPT code {code}…"):
                chunks  = retrieve(query, top_k=6)
                context = format_context(chunks)
                result  = analyze_single_cpt(code, context)

            st.markdown("---")
            st.markdown(result)

            with st.expander("📚 Manual sections used", expanded=False):
                for j, chunk in enumerate(chunks, 1):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**[SOURCE {j}]** `{format_citation(chunk)}`")
                        st.caption(chunk["text"][:250] + "…")
                    with col2:
                        st.metric("Relevance", f"{chunk['score']:.0%}")

            st.download_button(
                label="⬇️ Download analysis (.md)",
                data=result,
                file_name=f"ncci_cpt_{code}_analysis.md",
                mime="text/markdown",
            )

    else:
        col1, col2, _ = st.columns([1, 1, 1])
        with col1:
            code1 = st.text_input("CPT Code 1", placeholder="e.g. 99213", max_chars=10).strip()
        with col2:
            code2 = st.text_input("CPT Code 2", placeholder="e.g. 20610", max_chars=10).strip()

        invalid_pair = [c for c in [code1, code2] if c and not (c.isdigit() and len(c) == 5)]
        if invalid_pair:
            st.warning(f"⚠️ Invalid CPT code(s): {', '.join(invalid_pair)}. Must be 5 digits (e.g. 99213).")
        analyze_btn = st.button("Analyze Pair", type="primary", disabled=not (code1 and code2) or bool(invalid_pair))

        if analyze_btn and code1 and code2:
            query = (
                f"CPT codes {code1} {code2} mutually exclusive bundling "
                f"modifier 59 separate procedure NCCI edit"
            )
            with st.spinner(f"Analyzing pair {code1} + {code2}…"):
                chunks  = retrieve(query, top_k=6)
                context = format_context(chunks)
                result  = analyze_cpt_pair(code1, code2, context)

            st.markdown("---")

            result_lower = result.lower()
            if "yes" in result_lower[:500] and "conditional" not in result_lower[:500]:
                st.success("✅ These codes may be reportable together")
            elif "conditional" in result_lower[:500]:
                st.warning("⚠️ Conditional — modifier or documentation may be required")
            elif "no" in result_lower[:500]:
                st.error("❌ These codes are likely not separately reportable")

            st.markdown(result)

            with st.expander("📚 Manual sections used", expanded=False):
                for j, chunk in enumerate(chunks, 1):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**[SOURCE {j}]** `{format_citation(chunk)}`")
                        st.caption(chunk["text"][:250] + "…")
                    with col2:
                        st.metric("Relevance", f"{chunk['score']:.0%}")

            st.download_button(
                label="⬇️ Download analysis (.md)",
                data=result,
                file_name=f"ncci_pair_{code1}_{code2}_analysis.md",
                mime="text/markdown",
            )


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — CONFLICT DETECTOR
# ════════════════════════════════════════════════════════════════════════════

def _analyze_pair_worker(args):
    """Worker function for parallel pair analysis."""
    c1, c2 = args
    query = (
        f"CPT codes {c1} {c2} mutually exclusive bundling "
        f"modifier 59 separate procedure NCCI edit"
    )
    chunks  = retrieve(query, top_k=5)
    context = format_context(chunks)
    result  = analyze_cpt_pair(c1, c2, context)
    return c1, c2, result


def _classify_result(result: str) -> tuple[str, str]:
    """Return (emoji, label) based on LLM result text."""
    r = result.lower()[:500]
    if "conditional" in r:
        return "🟡", "Conditional"
    elif r.startswith("no") or "cannot be reported" in r or "not separately reportable" in r:
        return "🔴", "Conflict"
    elif "yes" in r and "conditional" not in r:
        return "🟢", "Compatible"
    else:
        return "🟡", "Review needed"


with tab_conflict:
    st.subheader("⚠️ Multi-Code Conflict Detector")
    st.markdown(
        "Enter up to **4 CPT codes** billed together. "
        "The system will analyze all code pairs in parallel and flag potential NCCI conflicts."
    )

    # Code inputs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        cd1 = st.text_input("CPT Code 1", placeholder="e.g. 99213", max_chars=10, key="cd1").strip()
    with col2:
        cd2 = st.text_input("CPT Code 2", placeholder="e.g. 20610", max_chars=10, key="cd2").strip()
    with col3:
        cd3 = st.text_input("CPT Code 3 (optional)", placeholder="e.g. 97140", max_chars=10, key="cd3").strip()
    with col4:
        cd4 = st.text_input("CPT Code 4 (optional)", placeholder="e.g. 27447", max_chars=10, key="cd4").strip()

    codes = [c for c in [cd1, cd2, cd3, cd4] if c]
    pairs = list(itertools.combinations(codes, 2))

    def _is_valid_cpt(code: str) -> bool:
        return code.isdigit() and len(code) == 5

    invalid = [c for c in codes if not _is_valid_cpt(c)]
    if invalid:
        st.warning(f"⚠️ Invalid CPT code(s): {', '.join(invalid)}. CPT codes must be 5 digits (e.g. 99213).")

    detect_btn = st.button(
        "Detect Conflicts",
        type="primary",
        disabled=len(codes) < 2 or bool(invalid),
    )

    if detect_btn and len(pairs) > 0:
        st.markdown("---")
        st.markdown(f"Analyzing **{len(pairs)} pair(s)** across {len(codes)} codes in parallel…")

        # Run all pairs in parallel
        results = {}
        with st.spinner("Running conflict analysis…"):
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(pairs)) as executor:
                futures = {executor.submit(_analyze_pair_worker, pair): pair for pair in pairs}
                for future in concurrent.futures.as_completed(futures):
                    c1, c2, result = future.result()
                    results[(c1, c2)] = result

        # ── Summary grid ──────────────────────────────────────────────────
        st.subheader("Conflict Summary")
        st.caption("🔴 Conflict  🟡 Conditional / Review needed  🟢 Compatible")

        # Header row
        header_cols = st.columns([1] + [1] * len(codes))
        header_cols[0].markdown("**Pair**")
        for i, c in enumerate(codes):
            header_cols[i + 1].markdown(f"**{c}**")

        # One row per pair
        for (c1, c2), result in results.items():
            emoji, label = _classify_result(result)
            row = st.columns([2, 1, 3])
            with row[0]:
                st.markdown(f"**{c1}** × **{c2}**")
            with row[1]:
                st.markdown(f"{emoji} {label}")
            with row[2]:
                with st.expander("View analysis", expanded=False):
                    # Badge
                    if emoji == "🔴":
                        st.error("❌ Likely conflict — separate billing may be denied")
                    elif emoji == "🟡":
                        st.warning("⚠️ Conditional — modifier or documentation required")
                    else:
                        st.success("✅ Generally reportable together")
                    st.markdown(result)

        # ── Download full report ──────────────────────────────────────────
        report_lines = [f"# NCCI Conflict Detection Report\n\n**Codes analyzed:** {', '.join(codes)}\n"]
        for (c1, c2), result in results.items():
            emoji, label = _classify_result(result)
            report_lines.append(f"\n---\n\n## {emoji} {c1} × {c2} — {label}\n\n{result}")
        report_md = "\n".join(report_lines)

        st.download_button(
            label="⬇️ Download full report (.md)",
            data=report_md,
            file_name=f"ncci_conflict_report_{'_'.join(codes)}.md",
            mime="text/markdown",
        )
