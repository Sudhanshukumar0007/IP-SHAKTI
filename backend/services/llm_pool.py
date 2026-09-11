"""
Groq API-key pool with health checks and a per-key circuit breaker.

On 3 consecutive 401/429 errors inside 60s a key is ejected for 5 minutes.
Round-robin only across currently active keys.

Gemini is DISABLED — all JSON fallback paths use Groq key rotation only.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import random
from typing import Any, Optional

import re as _re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from services import mongo_store
from services.tracing import get_trace_id

logger = logging.getLogger("llm_pool")

EJECT_SECONDS = 300
FAILURE_WINDOW_S = 60
FAILURE_THRESHOLD = 3
# Gemini disabled — all fallback is Groq key rotation.
GEMINI_FAST_MODEL = "disabled"
GEMINI_FAST_FALLBACK = "disabled"

_lock = threading.Lock()
_rr_index = 0


class KeySlot:
    def __init__(self, key_id: str, api_key: str):
        self.key_id = key_id
        self.api_key = api_key
        self.active = True
        self.ejected_until = 0.0
        self.fail_times: list[float] = []
        self.last_error: str = ""

    def is_active(self) -> bool:
        if self.ejected_until and time.time() < self.ejected_until:
            return False
        if self.ejected_until and time.time() >= self.ejected_until:
            self.active = True
            self.ejected_until = 0.0
            self.fail_times = []
            logger.info('{"event":"key_restored","key_id":"%s"}', self.key_id)
        return self.active


def _collect_keys() -> list[KeySlot]:
    slots = []
    seen = set()
    for name, value in os.environ.items():
        if not name.startswith("GROQ_API_KEY"):
            continue
        val = (value or "").strip()
        if not val or val in seen:
            continue
        seen.add(val)
        slots.append(KeySlot(name, val))
    return slots

_keys: list[KeySlot] = _collect_keys()



def _persist(slot: KeySlot) -> None:
    mongo_store.upsert_key_health(slot.key_id, {
        "active": slot.is_active(),
        "ejected_until": slot.ejected_until,
        "last_error": slot.last_error,
        "updated_at": time.time(),
    })


def record_success(key_id: str) -> None:
    with _lock:
        for slot in _keys:
            if slot.key_id == key_id:
                slot.fail_times = []
                _persist(slot)
                return


def record_failure(key_id: str, reason: str) -> None:
    now = time.time()
    with _lock:
        for slot in _keys:
            if slot.key_id != key_id:
                continue
            slot.last_error = reason
            slot.fail_times = [t for t in slot.fail_times if now - t <= FAILURE_WINDOW_S]
            slot.fail_times.append(now)
            if len(slot.fail_times) >= FAILURE_THRESHOLD:
                slot.active = False
                slot.ejected_until = now + EJECT_SECONDS
                logger.error(
                    '{"event":"key_ejected","key_id":"%s","reason":"%s","trace_id":"%s"}',
                    slot.key_id, reason, get_trace_id(),
                )
            _persist(slot)
            return


def _ping_key(slot: KeySlot) -> bool:
    try:
        llm = ChatGroq(model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"), api_key=slot.api_key, temperature=0)
        llm.bind(max_tokens=1).invoke([HumanMessage(content="ok")])
        return True
    except Exception as e:
        err = str(e)
        slot.last_error = err[:200]
        if "401" in err or "invalid api key" in err.lower() or "429" in err:
            slot.active = False
            slot.ejected_until = time.time() + EJECT_SECONDS
            logger.error(
                '{"event":"key_ejected","key_id":"%s","reason":"%s","trace_id":"%s"}',
                slot.key_id, err[:120], get_trace_id(),
            )
        else:
            logger.warning("Health ping failed for %s: %s", slot.key_id, err[:120])
        return False


def health_check_all() -> None:
    global _keys
    with _lock:
        _keys = _collect_keys()
        if not _keys:
            logger.critical("No GROQ_API_KEY* env vars found")
            return
        for slot in _keys:
            ok = _ping_key(slot)
            _persist(slot)
            logger.info("Groq key %s health=%s", slot.key_id, "ok" if ok else "dead")


def next_active_key() -> Optional[KeySlot]:
    global _rr_index
    with _lock:
        active = [s for s in _keys if s.is_active()]
        if not active:
            # last resort: try all, even ejected
            active = list(_keys)
        if not active:
            return None
        slot = active[_rr_index % len(active)]
        _rr_index += 1
        return slot


def all_active_keys() -> list[KeySlot]:
    with _lock:
        return [s for s in _keys if s.is_active()] or list(_keys)


def get_groq_llm(json_mode: bool = False, model_override: Optional[str] = None, temperature: float = 0):
    slot = next_active_key()
    model_name = model_override or os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    if slot is None:
        llm = ChatGroq(model=model_name, api_key=os.getenv("GROQ_API_KEY", ""), temperature=temperature)
        return llm.bind(response_format={"type": "json_object"}) if json_mode else llm, "GROQ_API_KEY"

    # Deterministic round-robin for fallbacks:
    active = all_active_keys()
    try:
        idx = next(i for i, s in enumerate(active) if s.key_id == slot.key_id)
        others = [active[(idx + i) % len(active)] for i in range(1, min(7, len(active)))]
    except StopIteration:
        others = []
    primary = ChatGroq(model=model_name, api_key=slot.api_key, temperature=temperature)
    fallbacks = [ChatGroq(model=model_name, api_key=s.api_key, temperature=temperature) for s in others]
    if json_mode:
        primary = primary.bind(response_format={"type": "json_object"})
        fallbacks = [llm.bind(response_format={"type": "json_object"}) for llm in fallbacks]
    if fallbacks:
        return primary.with_fallbacks(fallbacks), slot.key_id
    return primary, slot.key_id


def _gemini_client():
    from config import settings
    if not settings.GEMINI_API_KEY:
        return None
    try:
        from google import genai
        return genai.Client(api_key=settings.GEMINI_API_KEY)
    except Exception as e:
        logger.warning("Gemini client init failed: %s", e)
        return None


def invoke_gemini_json(prompt: str, system: str = "", timeout_s: float = 20.0) -> Optional[dict]:
    """Gemini disabled — returns None so callers fall through to Groq rotation."""
    return None


def invoke_gemini_text(prompt: str, timeout_s: float = 20.0) -> Optional[str]:
    """Gemini disabled — returns None so callers fall through to Groq rotation."""
    return None



def parse_json_robust(raw: str, trace: Optional[list], context: str) -> Any:
    cleaned = _re.sub(r"<think>.*?</think>", "", raw or "", flags=_re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(line for line in cleaned.split("\n") if not line.strip().startswith("```")).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        if trace is not None:
            raw_preview = (raw or "<empty>")[:500].replace("\n", " ")
            trace.append(f"[{context}] JSON parse error: {e}. Raw output (first 500 chars): {raw_preview}")
        return None


def call_json_with_fallback(
    prompt: str,
    schema: str,
    *,
    trace: Optional[list] = None,
    context: str = "JSON",
) -> tuple[Optional[dict], str]:
    """
    1) Groq json_mode
    2) One retry at temperature=0 with schema+query only
    3) Gemini 3 Flash structured output
    4) Empty dict + SKIPPED_TRANSIENT
    """

    def _log(msg: str) -> None:
        if trace is not None:
            trace.append(msg)
        logger.info("%s %s", context, msg)

    schema_prompt = f"Return ONLY valid JSON matching this schema:\n{schema}\n\n{prompt}"
    last_err = ""
    key_id = "unknown"

    try:
        llm, key_id = get_groq_llm(json_mode=True, temperature=0)
        resp = llm.invoke([
            SystemMessage(content="You output only valid JSON. " + schema),
            HumanMessage(content=prompt),
        ])
        parsed = parse_json_robust(getattr(resp, "content", "") or "", trace, context)
        if isinstance(parsed, dict):
            record_success(key_id)
            _log(f"JSON produced by groq/{key_id}")
            return parsed, f"groq/{key_id}"
    except Exception as e:
        last_err = str(e)
        if "401" in last_err or "invalid api key" in last_err.lower():
            record_failure(key_id, "401")
            _log(f"401 on {key_id}; retrying with next key")
            try:
                llm, key_id = get_groq_llm(json_mode=True, temperature=0)
                resp = llm.invoke([
                    SystemMessage(content="You output only valid JSON. " + schema),
                    HumanMessage(content=prompt),
                ])
                parsed = parse_json_robust(getattr(resp, "content", "") or "", trace, context)
                if isinstance(parsed, dict):
                    record_success(key_id)
                    _log(f"JSON produced by groq/{key_id} after 401 rotate")
                    return parsed, f"groq/{key_id}"
            except Exception as e2:
                last_err = str(e2)
                record_failure(key_id, str(e2)[:80])
        elif "429" in last_err:
            record_failure(key_id, "429")
        elif "400" in last_err or "json_validate_failed" in last_err.lower():
            _log("json_validate_failed; retrying trimmed prompt")
        else:
            _log(f"Groq JSON error: {last_err[:160]}")

    try:
        llm, key_id = get_groq_llm(json_mode=True, temperature=0)
        trimmed = f"{schema}\n\nQuery:\n{prompt[:800]}"
        resp = llm.invoke([HumanMessage(content=trimmed)])
        parsed = parse_json_robust(getattr(resp, "content", "") or "", trace, context)
        if isinstance(parsed, dict):
            record_success(key_id)
            _log(f"JSON produced by groq/{key_id} (trimmed retry)")
            return parsed, f"groq/{key_id}"
    except Exception as e:
        last_err = str(e)
        _log(f"Trimmed Groq retry failed: {last_err[:160]}")

    # Step 3 — third Groq key rotation (Gemini disabled)
    try:
        llm, key_id = get_groq_llm(json_mode=True, temperature=0)
        resp = llm.invoke([
            SystemMessage(content="You output only valid JSON. " + schema),
            HumanMessage(content=prompt[:600]),
        ])
        parsed = parse_json_robust(getattr(resp, "content", "") or "", trace, context)
        if isinstance(parsed, dict):
            record_success(key_id)
            _log(f"JSON produced by groq/{key_id} (3rd rotation)")
            return parsed, f"groq/{key_id}"
    except Exception as e:
        last_err = str(e)
        record_failure(key_id, last_err[:80])
        _log(f"3rd Groq rotation failed: {last_err[:160]}")

    _log(f"SKIPPED_TRANSIENT after all Groq retries: {last_err[:120]}")
    return {"missing_references": []}, "SKIPPED_TRANSIENT"
