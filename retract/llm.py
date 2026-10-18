"""One function, `llm(prompt) -> str`, behind which any provider can sit.

Providers are tried in order (LLM_PROVIDER first, then every provider with a
key: groq, gemini, openai, anthropic; Groq first because it is fastest). If one fails, the next is tried. If
none is configured, `available()` is False and every caller falls back to a
deterministic path. The LLM never writes Cypher: it only extracts claims as
JSON, picks tools, or phrases an answer from tool results.
"""
from __future__ import annotations

import json
import os
import re

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

KEYS = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY"}
last_used: str | None = None


def providers() -> list[str]:
    order = [p for p in ("groq", "gemini", "openai", "anthropic") if os.getenv(KEYS[p])]
    first = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if first in order:
        order.remove(first)
        order.insert(0, first)
    return order


def provider() -> str | None:
    """Human-readable provider chain, e.g. 'gemini > groq'."""
    p = providers()
    return " > ".join(p) if p else None


def available() -> bool:
    return bool(providers())


def _call(p: str, prompt: str, system: str, temperature: float) -> str:
    if p == "gemini":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        r = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system or None, temperature=temperature,
                thinking_config=types.ThinkingConfig(thinking_budget=int(os.getenv("GEMINI_THINKING_BUDGET", "0")))),
        )
        return r.text or ""
    if p in ("groq", "openai"):
        from openai import OpenAI

        if p == "groq":
            client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1",
                            timeout=45, max_retries=1)
            model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        else:
            client = OpenAI()
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        r = client.chat.completions.create(model=model, messages=msgs, temperature=temperature)
        return r.choices[0].message.content or ""
    if p == "anthropic":
        import anthropic

        client = anthropic.Anthropic()
        r = client.messages.create(model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"), max_tokens=1500,
                                   system=system or anthropic.NOT_GIVEN, temperature=temperature,
                                   messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    raise RuntimeError(f"unknown provider {p}")


def llm(prompt: str, system: str = "", temperature: float = 0.0) -> str:
    global last_used
    errors = []
    for p in providers():
        try:
            out = _call(p, prompt, system, temperature)
            if out.strip():
                last_used = p
                return out
            errors.append(f"{p}: empty reply")
        except Exception as e:
            errors.append(f"{p}: {type(e).__name__}: {str(e)[:120]}")
    raise RuntimeError("no LLM provider succeeded: " + "; ".join(errors or ["none configured"]))


def llm_json(prompt: str, system: str = ""):
    """Call the LLM and parse the first JSON object or array in its reply."""
    text = llm(prompt, system=system)
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError(f"no JSON in LLM reply: {text[:200]}")
    return json.JSONDecoder().raw_decode(text[min(starts):])[0]
