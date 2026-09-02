"""
SQLite-backed structured query log.

One row per completed query. Designed to support /eval/summary which
turns "safe abstention rate", "citation correctness", and "multilingual quality"
from claims into numbers pulled from a table.

All confidence components are logged individually so thresholds can be tuned
empirically — not just the composite score.
"""

from __future__ import annotations

import os
import json
import sqlite3
import datetime
from typing import Optional, Any

DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "query_log.db")
)

_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def init_db() -> None:
    """Create the query_log table if it doesn't exist. Called at startup."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id                              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id                      TEXT    NOT NULL,
            timestamp                       TEXT    NOT NULL,
            raw_query                       TEXT,
            language                        TEXT,
            jurisdiction_mode               TEXT,
            formulation_category            TEXT,

            -- Full Q&A trail (JSON)
            clarification_history           TEXT,

            -- Chunk provenance (JSON lists)
            retrieved_chunk_ids_national    TEXT,
            retrieved_chunk_ids_intl        TEXT,
            similarities_national           TEXT,
            similarities_intl               TEXT,

            -- Citations used in the answer (JSON)
            national_citations              TEXT,
            international_citations         TEXT,

            -- Confidence components — stored individually for threshold tuning
            max_similarity                  REAL,
            mean_similarity                 REAL,
            relevant_chunk_count            INTEGER,
            disclosure_fill_rate            REAL,
            confidence_score                REAL,

            -- Abstention
            abstain                         INTEGER,
            abstain_reason                  TEXT,

            -- Cost/perf
            llm_calls_made                  INTEGER,
            latency_ms                      REAL
        )
    """)
    conn.commit()


def log_query(state: dict) -> None:
    """Persist one completed query to the log. Accepts the full AgentState dict."""
    nat = state.get("retrieved_chunks_national") or []
    intl = state.get("retrieved_chunks_international") or []
    comp = state.get("confidence_components") or {}

    conn = _get_conn()
    conn.execute("""
        INSERT INTO query_log (
            session_id, timestamp, raw_query, language, jurisdiction_mode,
            formulation_category, clarification_history,
            retrieved_chunk_ids_national, retrieved_chunk_ids_intl,
            similarities_national, similarities_intl,
            national_citations, international_citations,
            max_similarity, mean_similarity, relevant_chunk_count,
            disclosure_fill_rate, confidence_score,
            abstain, abstain_reason,
            llm_calls_made, latency_ms
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?
        )
    """, (
        state.get("session_id"),
        datetime.datetime.utcnow().isoformat(),
        state.get("raw_query"),
        state.get("language"),
        state.get("jurisdiction_mode"),
        state.get("formulation_category"),
        json.dumps(state.get("clarification_history") or []),
        json.dumps([c["chunk_id"] for c in nat]),
        json.dumps([c["chunk_id"] for c in intl]),
        json.dumps([c["similarity"] for c in nat]),
        json.dumps([c["similarity"] for c in intl]),
        json.dumps(state.get("national_citations") or []),
        json.dumps(state.get("international_citations") or []),
        comp.get("max_similarity"),
        comp.get("mean_similarity"),
        comp.get("relevant_chunk_count"),
        comp.get("disclosure_fill_rate"),
        state.get("confidence_score"),
        1 if state.get("abstain") else 0,
        state.get("abstain_reason"),
        state.get("llm_calls_made"),
        state.get("latency_ms"),
    ))
    conn.commit()


def get_summary() -> dict[str, Any]:
    """Aggregate the log for /eval/summary."""
    conn = _get_conn()

    total = conn.execute("SELECT COUNT(*) FROM query_log").fetchone()[0]
    abstained = conn.execute(
        "SELECT COUNT(*) FROM query_log WHERE abstain = 1"
    ).fetchone()[0]
    avg_conf = conn.execute(
        "SELECT AVG(confidence_score) FROM query_log WHERE abstain = 0"
    ).fetchone()[0]
    avg_lat = conn.execute(
        "SELECT AVG(latency_ms) FROM query_log"
    ).fetchone()[0]

    by_jurisdiction = dict(
        conn.execute(
            "SELECT jurisdiction_mode, COUNT(*) FROM query_log GROUP BY jurisdiction_mode"
        ).fetchall()
    )
    by_category = dict(
        conn.execute(
            "SELECT formulation_category, COUNT(*) "
            "FROM query_log GROUP BY formulation_category"
        ).fetchall()
    )
    by_language = dict(
        conn.execute(
            "SELECT language, COUNT(*) FROM query_log GROUP BY language"
        ).fetchall()
    )

    # Similarity distribution for answered queries
    sim_rows = conn.execute(
        "SELECT max_similarity, mean_similarity, relevant_chunk_count "
        "FROM query_log WHERE abstain = 0"
    ).fetchall()
    if sim_rows:
        avg_max_sim = round(sum(r[0] for r in sim_rows if r[0]) / len(sim_rows), 4)
        avg_mean_sim = round(sum(r[1] for r in sim_rows if r[1]) / len(sim_rows), 4)
        avg_relevant = round(sum(r[2] for r in sim_rows if r[2]) / len(sim_rows), 2)
    else:
        avg_max_sim = avg_mean_sim = avg_relevant = None

    return {
        "total_queries": total,
        "abstained": abstained,
        "abstention_rate": round(abstained / total, 4) if total else 0.0,
        "avg_confidence_score": round(avg_conf, 4) if avg_conf is not None else None,
        "avg_latency_ms": round(avg_lat, 1) if avg_lat is not None else None,
        "avg_max_similarity": avg_max_sim,
        "avg_mean_similarity": avg_mean_sim,
        "avg_relevant_chunks": avg_relevant,
        "by_jurisdiction": by_jurisdiction,
        "by_formulation_category": by_category,
        "by_language": by_language,
    }
