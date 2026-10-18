"""One function, `llm(prompt) -> str`, behind which any provider can sit.

If no provider is configured, `available()` is False and every caller falls
back to a deterministic path. The LLM never writes Cypher: it only picks
tools, extracts claims as JSON, or phrases an answer from tool results.
"""
from __future__ import annotations

import json
import os
import re


def provider() -> str | None:
    p = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if p:
        return p
    for name, key in (("gemini", "GEMINI_API_KEY"), ("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")):
        if os.getenv(key):
            return name
    return None


def available() -> bool:
    return provider() is not None


def llm(prompt: str, system: str = "", temperature: float = 0.0) -> str:
    p = provider()
    if p == "gemini":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        r = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system or None, temperature=temperature),
        )
        return r.text or ""
    if p == "openai":
        from openai import OpenAI

        client = OpenAI()
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        r = client.chat.completions.create(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                                           messages=msgs, temperature=temperature)
        return r.choices[0].message.content or ""
    if p == "anthropic":
        import anthropic

        client = anthropic.Anthropic()
        r = client.messages.create(model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"), max_tokens=1500,
                                   system=system or anthropic.NOT_GIVEN, temperature=temperature,
                                   messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    raise RuntimeError("no LLM provider configured")


def llm_json(prompt: str, system: str = ""):
    """Call the LLM and parse the first JSON object or array in its reply."""
    text = llm(prompt, system=system)
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError(f"no JSON in LLM reply: {text[:200]}")
    return json.JSONDecoder().raw_decode(text[start:])[0]
