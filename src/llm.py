"""Thin wrapper around the Anthropic (Claude) API.

The LLM is used for four things only:
    1. routing   - deciding which agents a question needs (orchestrator)
    2. tool use  - deciding which data tools to call (data agent)
    3. research  - web search for organizations (outreach agent)
    4. writing   - turning collected evidence into a readable answer (synthesis)

It is never used to produce numbers: every number comes from SQL/Python.

Without an API key, get_llm() returns None and every caller falls back to
its offline (rule-based / template) path.
"""

import json

from src.config import LLM_EFFORT, LLM_MODEL, llm_available

# Server-side refusal fallback (recommended for Claude Opus 5 / Fable 5.1): if
# the model declines on a safety classifier, the API re-runs the request on a
# suitable fallback model instead of returning a refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1"}


class LLMRefusal(RuntimeError):
    pass


class LLM:
    def __init__(self, client=None, model=LLM_MODEL, effort=LLM_EFFORT):
        if client is None:
            import anthropic  # imported here so offline mode never needs the package configured
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.effort = effort
        self.calls = []   # (purpose, model, input tokens, output tokens), shown in the trace

    def create(self, *, system, messages, tools=None, max_tokens=16000, json_schema=None, purpose=""):
        """One Messages API call. Returns the raw response message."""
        output_config = {"effort": self.effort}
        if json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}
        kwargs = dict(model=self.model, max_tokens=max_tokens, system=system, messages=messages,
                      thinking={"type": "adaptive"}, output_config=output_config)
        if tools:
            kwargs["tools"] = tools
        if self.model in FALLBACK_MODELS:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        response = self.client.beta.messages.create(**kwargs)
        usage = getattr(response, "usage", None)
        self.calls.append({"purpose": purpose, "model": getattr(response, "model", self.model),
                           "input_tokens": getattr(usage, "input_tokens", None),
                           "output_tokens": getattr(usage, "output_tokens", None)})
        if response.stop_reason == "refusal":
            raise LLMRefusal(f"The model declined this request ({purpose}).")
        return response

    def json(self, *, system, prompt, schema, purpose="", max_tokens=8000):
        """Call with structured output and return the parsed JSON object."""
        response = self.create(system=system, messages=[{"role": "user", "content": prompt}],
                               json_schema=schema, max_tokens=max_tokens, purpose=purpose)
        return json.loads(text_of(response))


def text_of(response):
    """All text blocks of a response, joined (thinking and tool blocks skipped)."""
    return "\n".join(block.text for block in response.content if block.type == "text").strip()


def get_llm():
    """An LLM if a credential is configured, otherwise None (offline mode)."""
    return LLM() if llm_available() else None
