import datetime
import logging
import os
import time
from typing import List, Dict, Any

from config import settings

logger = logging.getLogger("connector")

# Gemini search disabled — DDGS only.
GEMINI_TIMEOUT_S = 8
DDGS_TIMEOUT_S = 6
OUTER_TIMEOUT_S = 10


def _error_obj(error_code: str, provider: str, latency_ms: float, message: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "error_code": error_code,
        "provider": provider,
        "latency_ms": round(latency_ms, 1),
        "message": message,
        "evidence": [],
    }


class LiveRegistryConnector:
    """
    Live patent/IP registry search using DuckDuckGo (DDGS).
    Gemini Search Grounding is disabled — DDGS is the only live provider.
    """

    _PHASE2_ENABLED: bool = True

    def __init__(self):
        self._gemini_client = None   # disabled
        self._ddgs = None

        try:
            from duckduckgo_search import DDGS
            try:
                self._ddgs = DDGS(timeout=DDGS_TIMEOUT_S)
            except TypeError:
                self._ddgs = DDGS()
        except ImportError:
            logger.warning("duckduckgo-search not installed")

    def search_registry(self, query: str) -> Dict[str, Any]:
        if not self._PHASE2_ENABLED:
            return {
                "status": "phase2_not_enabled",
                "error_code": None,
                "provider": None,
                "latency_ms": 0,
                "evidence": [],
                "message": "Phase 2 — live registry search not yet enabled.",
            }

        # Gemini disabled — go straight to DDGS
        if self._ddgs:
            try:
                return self._run_with_timeout(self._search_ddgs, query, "ddgs")
            except Exception as e:
                return _error_obj("PROVIDER_ERROR", "ddgs", 0, str(e))


        return _error_obj("NO_PROVIDERS", "none", 0, "Both Gemini and DuckDuckGo failed to initialize.")

    def _run_with_timeout(self, fn, query: str, provider: str) -> Dict[str, Any]:
        import concurrent.futures
        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn, query)
            try:
                return fut.result(timeout=OUTER_TIMEOUT_S)
            except concurrent.futures.TimeoutError:
                latency = (time.time() - start) * 1000
                logger.error("Search timeout after %ss (%s)", OUTER_TIMEOUT_S, provider)
                return _error_obj("TIMEOUT", provider, latency, f"Exceeded {OUTER_TIMEOUT_S}s outer timeout")

    def _search_gemini(self, query: str) -> Dict[str, Any]:
        from google.genai import types

        start = time.time()
        search_query = (
            "Search official live patent registries, IP India, WIPO, and government "
            f"sources for the current factual status of: {query}"
        )
        model = os.getenv("GEMINI_FAST_MODEL", "gemini-3-flash")
        config_kwargs: Dict[str, Any] = {
            "tools": [{"google_search": {}}],
            "temperature": 0.0,
        }
        try:
            config = types.GenerateContentConfig(
                **config_kwargs,
                http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_S * 1000),
            )
        except (TypeError, AttributeError):
            config = types.GenerateContentConfig(**config_kwargs)

        try:
            response = self._gemini_client.models.generate_content(
                model=model,
                contents=search_query,
                config=config,
            )
        except Exception:
            response = self._gemini_client.models.generate_content(
                model=os.getenv("GEMINI_FAST_FALLBACK", "gemini-2.5-flash"),
                contents=search_query,
                config=config,
            )

        latency = (time.time() - start) * 1000
        evidence_list = []
        urls = []
        titles = []

        if response.candidates and response.candidates[0].grounding_metadata:
            chunks = response.candidates[0].grounding_metadata.grounding_chunks
            if chunks:
                for c in chunks:
                    if hasattr(c, "web") and c.web:
                        if getattr(c.web, "uri", None):
                            urls.append(c.web.uri)
                        if getattr(c.web, "title", None):
                            titles.append(c.web.title)

        evidence_list.append({
            "source": "Gemini Live Search Grounding",
            "retrieved_at": datetime.datetime.utcnow().isoformat() + "Z",
            "title": " | ".join(titles[:3]) if titles else "Live Web Synthesis",
            "url": ", ".join(urls[:3]) if urls else "Web Search",
            "evidence": response.text if response.text else "No synthesized text returned.",
            "record_id": "gemini-live-search",
        })

        return {
            "status": "success",
            "error_code": None,
            "provider": "gemini",
            "latency_ms": round(latency, 1),
            "evidence": evidence_list,
        }

    def _search_ddgs(self, query: str) -> Dict[str, Any]:
        start = time.time()
        full_query = f"{query} patent registry India WIPO"
        evidence_list = []
        try:
            try:
                results = self._ddgs.text(full_query, max_results=3, timeout=DDGS_TIMEOUT_S)
            except TypeError:
                results = self._ddgs.text(full_query, max_results=3)
        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.error("DDGS search failed: %s", e)
            return _error_obj("PROVIDER_ERROR", "ddgs", latency, str(e))

        latency = (time.time() - start) * 1000
        for res in results:
            url = res.get("href", "")
            if "ipindia" in url:
                source_name = "IP India"
            elif "wipo" in url:
                source_name = "WIPO"
            else:
                source_name = "Web Source"
            evidence_list.append({
                "source": source_name,
                "retrieved_at": datetime.datetime.utcnow().isoformat() + "Z",
                "title": res.get("title", "Unknown Title"),
                "url": url,
                "evidence": res.get("body", ""),
                "record_id": url.split("/")[-1] if "/" in url else "unknown",
            })

        status = "success" if evidence_list else "no_results"
        return {
            "status": status,
            "error_code": None if evidence_list else "NO_RESULTS",
            "provider": "ddgs",
            "latency_ms": round(latency, 1),
            "evidence": evidence_list,
        }
