"""Structured logger for auditing application sessions and logic.

Outputs:
  - Console: human-readable colored lines
  - File: JSON lines (one object per entry) at logs/app.jsonl

Session tracking via ContextVar — each request gets a session_id with
accumulated cost, latency, and call counts.
"""

import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Cost table ($ per 1 M tokens)
# ---------------------------------------------------------------------------
COST_PER_M_TOKENS: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    # NVIDIA NIM (free tier)
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": {"input": 0.0, "output": 0.0},
    "nvidia/llama-3.2-nv-embedqa-1b-v2": {"input": 0.0, "output": 0.0},
    # Voyage
    "voyage-3.5": {"input": 0.06, "output": 0.0},
    "voyage-3": {"input": 0.06, "output": 0.0},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    rates = COST_PER_M_TOKENS.get(model, {})
    return (input_tokens * rates.get("input", 0) + output_tokens * rates.get("output", 0)) / 1_000_000


# ---------------------------------------------------------------------------
# Session context
# ---------------------------------------------------------------------------
_session: ContextVar[dict | None] = ContextVar("audit_session", default=None)


def start_session(query: str = "", source: str = "api") -> str:
    """Start a new audit session. Returns session_id."""
    sid = uuid.uuid4().hex[:12]
    _session.set({
        "session_id": sid,
        "query": query,
        "source": source,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "llm_calls": 0,
        "embed_calls": 0,
        "tool_calls": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "total_latency_ms": 0,
    })
    _log.info("session.start", session_id=sid, query=query, source=source)
    return sid


def end_session() -> dict:
    """End the current session and log summary. Returns the summary dict."""
    s = _session.get()
    if not s:
        return {}
    s["ended_at"] = datetime.now(timezone.utc).isoformat()
    _log.info("session.end", **s)
    _session.set(None)
    return s


def get_session() -> dict | None:
    return _session.get()


def _accum(key: str, value):
    s = _session.get()
    if s:
        s[key] = s.get(key, 0) + value


# ---------------------------------------------------------------------------
# Structured log helpers
# ---------------------------------------------------------------------------

class _StructuredLogger:
    """Thin wrapper that attaches structured fields to log records."""

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def _log(self, level: int, event: str, **fields):
        s = _session.get()
        record_extra = {"event": event, "fields": fields}
        if s:
            record_extra["session_id"] = s["session_id"]
        self._logger.log(level, event, extra={"structured": record_extra})

    def debug(self, event: str, **kw):   self._log(logging.DEBUG, event, **kw)
    def info(self, event: str, **kw):    self._log(logging.INFO, event, **kw)
    def warning(self, event: str, **kw): self._log(logging.WARNING, event, **kw)
    def error(self, event: str, **kw):   self._log(logging.ERROR, event, **kw)


_log = _StructuredLogger("showmeoff")


# Expose module-level convenience functions
def debug(event, **kw):   _log.debug(event, **kw)
def info(event, **kw):    _log.info(event, **kw)
def warning(event, **kw): _log.warning(event, **kw)
def error(event, **kw):   _log.error(event, **kw)


# ---------------------------------------------------------------------------
# Domain-specific log functions
# ---------------------------------------------------------------------------

def log_llm_call(*, provider: str, model: str, input_tokens: int,
                 output_tokens: int, latency_ms: int, purpose: str,
                 tool_calls: int = 0, **extra):
    cost = estimate_cost(model, input_tokens, output_tokens)
    _accum("llm_calls", 1)
    _accum("total_input_tokens", input_tokens)
    _accum("total_output_tokens", output_tokens)
    _accum("total_cost_usd", cost)
    _accum("total_latency_ms", latency_ms)
    _log.info("llm.call", provider=provider, model=model,
              input_tokens=input_tokens, output_tokens=output_tokens,
              latency_ms=latency_ms, cost_usd=round(cost, 6),
              purpose=purpose, tool_calls=tool_calls, **extra)


def log_llm_retry(*, provider: str, attempt: int, wait_s: int, reason: str = "rate_limit"):
    _log.warning("llm.retry", provider=provider, attempt=attempt,
                 wait_s=wait_s, reason=reason)


def log_llm_error(*, provider: str, error: str, purpose: str = ""):
    _log.error("llm.error", provider=provider, error=error, purpose=purpose)


def log_embed_call(*, provider: str, model: str, batch_size: int,
                   latency_ms: int, **extra):
    cost = estimate_cost(model, batch_size * 500)  # rough: ~500 tokens/snippet
    _accum("embed_calls", 1)
    _accum("total_cost_usd", cost)
    _accum("total_latency_ms", latency_ms)
    _log.info("embed.call", provider=provider, model=model,
              batch_size=batch_size, latency_ms=latency_ms,
              cost_usd=round(cost, 6), **extra)


def log_embed_retry(*, provider: str, attempt: int, wait_s: int):
    _log.warning("embed.retry", provider=provider, attempt=attempt, wait_s=wait_s)


def log_tool_call(*, tool_name: str, args: dict, result_size: int, latency_ms: int):
    _accum("tool_calls", 1)
    _accum("total_latency_ms", latency_ms)
    _log.info("tool.call", tool_name=tool_name, args=args,
              result_size=result_size, latency_ms=latency_ms)


def log_tool_result(*, tool_name: str, result_count: int, sample_keys: list[str] | None = None):
    _log.debug("tool.result", tool_name=tool_name, result_count=result_count,
               sample_keys=sample_keys or [])


def log_curation(*, kept: int, dropped: int, total: int, fallback: bool = False):
    _log.info("curation.decision", kept=kept, dropped=dropped,
              total=total, fallback=fallback)


def log_evidence(*, collected: int, unique_repos: int, unique_skills: int):
    _log.info("evidence.collected", collected=collected,
              unique_repos=unique_repos, unique_skills=unique_skills)


def log_vector_search(*, query_preview: str, top_score: float, result_count: int, min_score: float):
    _log.debug("vector.search", query_preview=query_preview[:80],
               top_score=round(top_score, 4), result_count=result_count,
               min_score=min_score)


def log_ingestion_step(*, step: str, detail: str = "", **extra):
    _log.info(f"ingestion.{step}", detail=detail, **extra)


def log_context_gen(*, batch_size: int, success: int, failed: int, latency_ms: int):
    _log.info("context.generate", batch_size=batch_size, success=success,
              failed=failed, latency_ms=latency_ms)


def log_request(*, method: str, path: str, query: str = "", status: int = 200, latency_ms: int = 0):
    _log.info("http.request", method=method, path=path, query=query,
              status=status, latency_ms=latency_ms)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

_COLORS = {
    "DEBUG": "\033[36m",     # cyan
    "INFO": "\033[32m",      # green
    "WARNING": "\033[33m",   # yellow
    "ERROR": "\033[31m",     # red
    "RESET": "\033[0m",
}


class ConsoleFormatter(logging.Formatter):
    def format(self, record):
        extra = getattr(record, "structured", {})
        event = extra.get("event", record.getMessage())
        fields = extra.get("fields", {})
        sid = extra.get("session_id", "")
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        c = _COLORS.get(record.levelname, "")
        r = _COLORS["RESET"]
        sid_str = f" [{sid}]" if sid else ""
        # Build field string — skip empty/None values
        field_parts = []
        for k, v in fields.items():
            if v is None or v == "" or v == 0:
                continue
            if isinstance(v, float):
                v = f"{v:.6f}" if v < 0.01 else f"{v:.4f}"
            if isinstance(v, dict):
                v = json.dumps(v, default=str)
            field_parts.append(f"{k}={v}")
        fields_str = " ".join(field_parts)
        if fields_str:
            fields_str = f" | {fields_str}"
        return f"{ts} {c}{record.levelname:<7}{r}{sid_str} {event}{fields_str}"


class JSONFormatter(logging.Formatter):
    def format(self, record):
        extra = getattr(record, "structured", {})
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": extra.get("event", record.getMessage()),
            **extra.get("fields", {}),
        }
        sid = extra.get("session_id")
        if sid:
            entry["session_id"] = sid
        return json.dumps(entry, default=str)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

_configured = False


def setup_logging(level: str = "INFO", log_file: str = "logs/app.jsonl"):
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger("showmeoff")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(ConsoleFormatter())
    root.addHandler(ch)

    # File handler (JSON lines)
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(JSONFormatter())
    root.addHandler(fh)

    # Suppress noisy third-party loggers
    for name in ("httpx", "httpcore", "neo4j", "anthropic", "openai", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)


# Auto-setup on import with env-configurable level
setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))
