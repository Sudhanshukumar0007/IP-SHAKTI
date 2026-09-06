import datetime
from typing import List, Dict, Any


class LiveRegistryConnector:
    """
    Live patent/IP registry search via DuckDuckGo.

    Phase 2 feature: live structured patent record lookup is not yet wired
    to a paid API (IP India, WIPO patentscope). The connector performs a
    best-effort web search and surfaces snippets as supporting evidence.

    When no records are returned, the status is surfaced as
    "phase2_not_enabled" so the execution trace reads as an intentional
    roadmap item rather than a broken feature.
    """

    # Phase 2 readiness flag — flip to True once a paid structured API is wired
    _PHASE2_ENABLED: bool = False

    def __init__(self):
        # Lazy-import so the rest of the app works if duckduckgo_search is not installed
        try:
            from duckduckgo_search import DDGS
            self._ddgs = DDGS()
        except ImportError:
            self._ddgs = None

    def search_registry(self, query: str) -> Dict[str, Any]:
        """
        Search for live factual evidence regarding patents and IP.

        Returns a dict with:
          status   — "success" | "no_results" | "phase2_not_enabled" | "error:<msg>"
          evidence — list[dict] of evidence records
        """
        if not self._PHASE2_ENABLED or self._ddgs is None:
            return {
                "status": "phase2_not_enabled",
                "evidence": [],
                "message": (
                    "Phase 2 — live registry search not yet enabled. "
                    "Structured patent record lookup (IP India, WIPO Patentscope) "
                    "will be wired in Phase 2."
                ),
            }

        full_query = f"{query} patent registry India WIPO"
        evidence_list = []
        try:
            results = self._ddgs.text(full_query, max_results=3)
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
        except Exception as e:
            status = f"error: {str(e)}"

        return {
            "status": status,
            "evidence": evidence_list,
        }
