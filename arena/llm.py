"""One OpenAI-compatible client for every arena model (all served by the Kaggle notebook)."""
import re

from openai import OpenAI

from arena import config

_client = None
THINK = re.compile(r"<think>.*?</think>", re.S)


def client():
    global _client
    if _client is None:
        _client = OpenAI(base_url=config.BASE_URL, api_key=config.API_KEY, timeout=180)
    return _client


def chat(model, messages, tools=None, **kw):
    """Return the assistant message object (content and/or tool_calls)."""
    if tools:
        kw["tools"] = tools
    return client().chat.completions.create(model=model, messages=messages, **kw).choices[0].message


def strip_think(text):
    """Qwen3 models may wrap hidden reasoning in <think> tags; never show or judge it.
    Sometimes only the closing tag comes back, so also drop everything before a lone </think>."""
    text = THINK.sub("", text or "")
    return text.rsplit("</think>", 1)[-1].strip()
