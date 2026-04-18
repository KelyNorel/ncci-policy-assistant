"""
llm.py
Wraps Anthropic API calls for:
  - RAG-grounded Q&A (chat)
  - Structured policy insights (insights feature)
  - CPT code pair analysis (CPT Analyzer feature)
"""

import os
import anthropic
from dotenv import load_dotenv
load_dotenv()

MODEL = "claude-sonnet-4-20250514"

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Run: export ANTHROPIC_API_KEY=sk-ant-..."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ── Chat (RAG Q&A) ───────────────────────────────────────────────────────────

CHAT_SYSTEM = """You are an expert assistant on the 2026 CMS Medicare NCCI (National Correct Coding Initiative) Coding Policy Manual.

Answer the user's question using ONLY the source excerpts provided below. 
- Always cite your sources using the format [SOURCE N] inline.
- If multiple sources support a point, cite all of them.
- If the answer is not found in the sources, say so clearly — do not hallucinate, and do not cite any sources.
- Be concise and precise. Use bullet points for multi-part answers.
- When citing a specific rule or policy, quote the relevant phrase briefly and cite it.
"""

def chat(query: str, context: str, history: list[dict] | None = None) -> str:
    client = _get_client()

    user_message = f"""Here are the relevant excerpts from the 2026 NCCI Medicare Policy Manual:

{context}

---

Question: {query}

Answer based on the sources above. Cite [SOURCE N] inline."""

    messages = []
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=CHAT_SYSTEM,
        messages=messages,
    )

    return response.content[0].text


# ── Insights ─────────────────────────────────────────────────────────────────

INSIGHTS_SYSTEM = """You are an expert analyst of the 2026 CMS Medicare NCCI Coding Policy Manual.

Your task is to produce a clear, structured summary of a specific policy topic based on the provided manual excerpts.

Format your response as:
## Overview
2-3 sentence summary of the topic.

## Key Rules
- Bullet list of the most important rules or policies (cite [SOURCE N] for each)

## Important Exceptions or Edge Cases
- Any notable exceptions, special cases, or caveats

## Relevant CPT Code Ranges (if applicable)
- Any specific code ranges or codes mentioned

Keep it practical and precise. A medical coder should be able to act on this summary."""


def get_insights(topic: str, context: str) -> str:
    client = _get_client()

    user_message = f"""Here are excerpts from the 2026 NCCI Medicare Policy Manual relevant to: "{topic}"

{context}

---

Please provide a structured policy summary for: {topic}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=INSIGHTS_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    return response.content[0].text


# ── CPT Code Analyzer ────────────────────────────────────────────────────────

CPT_SINGLE_SYSTEM = """You are an expert on the 2026 CMS Medicare NCCI Coding Policy Manual, specializing in CPT code policy analysis.

The user has provided a single CPT code. Analyze it based on the provided manual excerpts.

Format your response as:

## CPT Code {code} — Policy Analysis

## Applicable NCCI Policies
- Key policies and rules that apply to this code (cite [SOURCE N] for each)

## Global Surgery Indicator
- What global period applies (000, 010, 090, XXX, YYY, ZZZ, MMM) if mentioned

## Bundling Considerations
- What services are typically bundled with this code
- What cannot be reported separately

## Modifier Guidance
- Which modifiers are relevant and when to use them

## Important Notes
- Any special rules, exceptions, or caveats

If specific information about this code is not found in the sources, say so clearly and provide only what the sources support. Do not hallucinate code-specific details."""


CPT_PAIR_SYSTEM = """You are an expert on the 2026 CMS Medicare NCCI Coding Policy Manual, specializing in NCCI PTP (Procedure-to-Procedure) edit analysis.

The user has provided two CPT codes. Analyze whether they can be reported together based on the provided manual excerpts.

Format your response as:

## CPT Code Pair Analysis: {code1} + {code2}

## Compatibility Assessment
A clear statement: Can these codes be reported together? (Yes / No / Conditional)

## Applicable NCCI Policies
- Relevant policies from the manual that apply to this pair (cite [SOURCE N] for each)

## Potential Edit Types
- Mutually Exclusive Edit: yes/no/possible — with explanation
- Bundling Edit: yes/no/possible — with explanation  
- MUE considerations if relevant

## Modifier Options
- If conditional: which modifiers (59, XE, XS, XP, XU, 25, 57, etc.) may allow separate reporting and under what circumstances

## Documentation Requirements
- What documentation would be needed to support separate billing

## Manual References
- Key sections and page numbers cited

If the sources do not contain enough information to make a definitive assessment, say so clearly and explain what additional information would be needed."""


def analyze_single_cpt(code: str, context: str) -> str:
    """
    Analyze NCCI policies for a single CPT code.
    """
    client = _get_client()

    system = CPT_SINGLE_SYSTEM.replace("{code}", code)

    user_message = f"""Here are excerpts from the 2026 NCCI Medicare Policy Manual relevant to CPT code {code}:

{context}

---

Please analyze the NCCI policies applicable to CPT code {code}."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    return response.content[0].text


def analyze_cpt_pair(code1: str, code2: str, context: str) -> str:
    """
    Analyze whether two CPT codes can be reported together under NCCI rules.
    """
    client = _get_client()

    system = CPT_PAIR_SYSTEM.replace("{code1}", code1).replace("{code2}", code2)

    user_message = f"""Here are excerpts from the 2026 NCCI Medicare Policy Manual relevant to CPT codes {code1} and {code2}:

{context}

---

Please analyze whether CPT codes {code1} and {code2} can be reported together, and what NCCI policies apply to this pair."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    return response.content[0].text
