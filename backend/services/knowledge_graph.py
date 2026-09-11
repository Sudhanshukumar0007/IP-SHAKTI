import json
import logging
import os
import re
import string

logger = logging.getLogger("knowledge_graph")

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "registry.json")

_TOKEN_SPLIT = re.compile(r"[\s,;:/\\\-_()\[\]{}.]+")
_STOP = frozenset({"the", "of", "and", "act", "on", "for", "to", "a", "an", "in"})


def _normalize_tokens(text: str) -> list[str]:
    cleaned = (text or "").lower().translate(str.maketrans("", "", string.punctuation))
    return [t for t in _TOKEN_SPLIT.split(cleaned) if t and t not in _STOP]


def token_overlap_ratio(a: str, b: str) -> float:
    ta, tb = set(_normalize_tokens(a)), set(_normalize_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


class KnowledgeGraph:
    def __init__(self):
        self.registry = {}
        self.act_name_to_ids = {}
        self.latest_versions = {}
        self.edges_amended_by = {}
        self.edges_governed_by = {}
        self._registry_mtime: float | None = None
        self._load_registry()

    def _maybe_reload(self) -> None:
        if not os.path.exists(REGISTRY_PATH):
            return
        try:
            mtime = os.path.getmtime(REGISTRY_PATH)
        except OSError as e:
            logger.warning("Could not stat registry.json: %s", e)
            return
        if self._registry_mtime is None or mtime > self._registry_mtime:
            self._load_registry()

    def _load_registry(self):
        if not os.path.exists(REGISTRY_PATH):
            return

        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                self.registry = json.load(f)
            self._registry_mtime = os.path.getmtime(REGISTRY_PATH)
        except json.JSONDecodeError as e:
            logger.error("registry.json is not valid JSON: %s", e)
            return
        except OSError as e:
            logger.error("Failed to read registry.json: %s", e)
            return

        self.act_name_to_ids = {}
        self.latest_versions = {}
        self.edges_amended_by = {}
        self.edges_governed_by = {}

        for doc_id, doc in self.registry.items():
            act_name = doc.get("act_name", "").lower()
            act_id = doc.get("act_id", "").lower()

            if act_name not in self.act_name_to_ids:
                self.act_name_to_ids[act_name] = []
            self.act_name_to_ids[act_name].append(doc_id)

            if act_id:
                if act_id not in self.act_name_to_ids:
                    self.act_name_to_ids[act_id] = []
                self.act_name_to_ids[act_id].append(doc_id)

            if doc.get("is_latest_consolidated", False):
                if act_id:
                    self.latest_versions[act_id] = doc_id
                if act_name:
                    self.latest_versions[act_name] = doc_id

            if doc.get("superseded_by"):
                self.edges_amended_by[doc_id] = doc["superseded_by"]

            cat = doc.get("category_type", "unknown").lower()
            if cat not in self.edges_governed_by:
                self.edges_governed_by[cat] = []
            self.edges_governed_by[cat].append(doc_id)

    def resolve_reference(self, reference_text: str) -> list[str]:
        """
        Resolve a textual reference (e.g. "Section 3(p) of the Patents Act, 1970")
        to document IDs. Uses exact act_id match or >=80% token overlap — not
        substring matching, which over-matched short keys like "3(p)".
        """
        self._maybe_reload()
        ref_lower = (reference_text or "").lower()
        matched_ids = set()

        for key, ids in self.act_name_to_ids.items():
            if not key:
                continue
            exact_id = key == ref_lower or key in ref_lower.split()
            overlap = token_overlap_ratio(key, ref_lower)
            if exact_id or overlap >= 0.80:
                matched_ids.update(ids)
                if key in self.latest_versions:
                    matched_ids.add(self.latest_versions[key])

        final_ids = set()
        for d in matched_ids:
            current = d
            visited = set()
            while current in self.edges_amended_by:
                if current in visited:
                    logger.warning("AMENDED_BY cycle detected at %s; breaking walk", current)
                    break
                visited.add(current)
                current = self.edges_amended_by[current]
            final_ids.add(current)
            final_ids.add(d)

        return list(final_ids)

    def get_governing_documents(self, category: str) -> list[str]:
        self._maybe_reload()
        return self.edges_governed_by.get(category.lower(), [])


kg = KnowledgeGraph()


def resolve_reference(reference_text: str) -> list[str]:
    kg._maybe_reload()
    if not kg.registry:
        kg._load_registry()
    return kg.resolve_reference(reference_text)
