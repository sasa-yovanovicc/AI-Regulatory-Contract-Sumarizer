import os
import time
import random
import json
from typing import List, Optional, Dict, Any
import requests
from openai import OpenAI
from openai import RateLimitError
from dotenv import load_dotenv

load_dotenv()

SYSTEM_BASE = (
    "You are an AI assistant specialized in summarizing and analyzing EU regulatory and contractual documents for banking staff. "
    "Avoid legal jargon, keep a concise business tone, and respond in clear professional English unless explicitly instructed otherwise."
)

_client = None
BACKEND = os.getenv("LLM_BACKEND", "openai").lower()  # openai | ollama | basic

def _extract_text_fragment(messages: List[Dict[str, str]]) -> str:
    # Try to pull the longest 'Text:' section from last user message for basic fallback summarization
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if "Text:" in content:
                return content.split("Text:", 1)[1][:5000]
            return content[:5000]
    return ""


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Create a .env file or export the variable before calling LLM functions."
            )
        _client = OpenAI(api_key=api_key)
    return _client


def _ollama_chat(messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    # Merge messages into a single prompt; keep simple formatting
    prompt_parts = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        prompt_parts.append(f"[{role.upper()}]\n{content}")
    prompt = "\n\n".join(prompt_parts)
    resp = requests.post(
        f"{base}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": temperature},
            # Ollama ignores max_tokens but we keep param for parity
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    # Ollama streams sometimes; final message in 'message'
    if "message" in data and isinstance(data["message"], dict):
        content = data["message"].get("content", "")
    else:
        content = json.dumps(data)
    return {"choices": [{"message": {"content": content}}]}


def _basic_fallback(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    text = _extract_text_fragment(messages)
    # Naive summarization: take first 3 sentences or 60 words
    sentences = [s.strip() for s in text.replace('\n', ' ').split('.') if s.strip()]
    summary_sentences = sentences[:3]
    if not summary_sentences:
        summary_sentences = [text[:200]]
    summary = '. '.join(summary_sentences)
    words = summary.split()
    if len(words) > 60:
        summary = ' '.join(words[:60]) + '...'
    return {"choices": [{"message": {"content": summary}}]}


def _chat_with_retries(messages, model: str, temperature: float, max_tokens: int, *, purpose: str):
    # Direct alternate backends bypass OpenAI
    if BACKEND == "basic":
        return _basic_fallback(messages)
    if BACKEND == "ollama":
        ollama_model = os.getenv("OLLAMA_MODEL", model)
        try:
            return _ollama_chat(messages, ollama_model, temperature, max_tokens)
        except Exception as e:  # fallback to basic
            return _basic_fallback(messages + [{"role": "system", "content": f"[ollama error fallback] {e}"}])

    client = _get_client()  # default openai path
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
    base_delay = float(os.getenv("OPENAI_RETRY_BASE_DELAY", "1.0"))
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except RateLimitError as e:
            if attempt == max_retries - 1:
                # If insufficient quota -> degrade to basic fallback (if allowed)
                if "insufficient_quota" in str(e) and os.getenv("ALLOW_BASIC_FALLBACK", "1") == "1":
                    return _basic_fallback(messages + [{"role": "system", "content": "[quota fallback: basic heuristic summary]"}])
                raise RuntimeError(
                    f"Rate limit exceeded after {max_retries} attempts for {purpose}. Consider reducing chunk size, slowing requests, or upgrading quota. Original: {e}"  # noqa: E501
                ) from e
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.25)
            time.sleep(delay)
        except Exception as e:  # transient network / 5xx
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (1.5 ** attempt) + random.uniform(0, 0.2)
            time.sleep(delay)
    # Should never reach
    raise RuntimeError("Exhausted retries without raising inside loop.")


def summarize_chunk(text: str, focus: Optional[str] = None) -> str:
    focus_part = f" Focus: {focus}." if focus else ""
    prompt = (
        f"Summarize the following regulatory text into at most 3 clear sentences understandable to a banking officer.{focus_part}\n"
        f"Text:\n{text}\n---\nSummary:"
    )
    resp = _chat_with_retries(
        [
            {"role": "system", "content": SYSTEM_BASE},
            {"role": "user", "content": prompt},
        ],
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.3,
        max_tokens=220,
        purpose="summarize_chunk",
    )
    return resp.choices[0].message.content.strip()


def consolidate_summaries(summaries: List[str], focus: Optional[str] = None) -> str:
    joined = "\n".join(f"- {s}" for s in summaries)
    focus_part = f" Focus: {focus}." if focus else ""
    prompt = (
        f"Using the partial summaries, produce a structured executive overview (sections + bullet points) no longer than one A4 page.{focus_part}\n"
        f"Partial summaries:\n{joined}\n---\nFinal overview:"
    )
    resp = _chat_with_retries(
        [
            {"role": "system", "content": SYSTEM_BASE},
            {"role": "user", "content": prompt},
        ],
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.25,
        max_tokens=800,
        purpose="consolidate_summaries",
    )
    return resp.choices[0].message.content.strip()


# Additional task-specific prompts
TASK_TEMPLATES = {
    "summary": {
        "chunk": (
            "Extract up to 3 concise bullet points capturing the core obligations, constraints, and operational impacts in this text."
        ),
        "final": (
            "Merge the bullet points into a de-duplicated structured summary (Sections: Scope, Obligations, Risks, Operational Notes). Limit to ~300 words."  # noqa: E501
        ),
    },
    "unfavorable_elements": {
        "chunk": (
            "List up to 3 potentially unfavorable or high-risk clauses for the signatory. For each: Bullet: <short clause gist> – Rationale (<risk type>)."  # noqa: E501
        ),
        "final": (
            "Consolidate and de-duplicate all bullets. Group by Risk Type. Output format:\nRisk Type: ...\n- Clause gist – Rationale"  # noqa: E501
        ),
    },
    "conflicts": {
        "chunk": (
            "Identify at most 2 potential internal conflicts or inconsistencies in this segment. Format each as: Conflict: <Clause A gist> VS <Clause B gist> – Explanation."  # noqa: E501
        ),
        "final": (
            "Aggregate conflicts removing duplicates. Prioritize those impacting obligations, liability, data protection, or timeline. Output a table-like list (no markdown table needed)."  # noqa: E501
        ),
    },
}


def analyze_chunk(text: str, task: str) -> str:
    template = TASK_TEMPLATES.get(task, TASK_TEMPLATES["summary"])  # fallback
    
    # Debug logging
    debug = os.getenv("DEBUG_STREAM", "0") == "1"
    if debug:
        print(f"[CHUNK] task={task}, template={list(template.keys())}")
    
    prompt = f"{template['chunk']}\nText:\n{text}\n---\nOutput:"
    resp = _chat_with_retries(
        [
            {"role": "system", "content": SYSTEM_BASE},
            {"role": "user", "content": prompt},
        ],
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.35,
        max_tokens=300,
        purpose="analyze_chunk",
    )
    return resp.choices[0].message.content.strip()


def consolidate_task_outputs(outputs: List[str], task: str, focus: Optional[str] = None) -> str:
    template = TASK_TEMPLATES.get(task, TASK_TEMPLATES["summary"])  # fallback
    joined = "\n".join(outputs)
    focus_part = f" Additional focus: {focus}." if focus else ""
    
    # Debug logging
    debug = os.getenv("DEBUG_STREAM", "0") == "1"
    if debug:
        print(f"[CONSOLIDATE] task={task}, template={list(template.keys())}, focus={focus}")
    
    prompt = (
        f"{template['final']}{focus_part}\nRaw extracted items:\n{joined}\n---\nFinal consolidated output:"  # noqa: E501
    )
    resp = _chat_with_retries(
        [
            {"role": "system", "content": SYSTEM_BASE},
            {"role": "user", "content": prompt},
        ],
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.3,
        max_tokens=900,
        purpose="consolidate_task_outputs",
    )
    return resp.choices[0].message.content.strip()
