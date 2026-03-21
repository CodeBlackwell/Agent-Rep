import json
import hashlib
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config.settings import Settings
from src.core import logger
from src.core.client_factory import build_clients
from src.qa.agent import QAAgent

settings = Settings.load()
clients = build_clients(settings)
db = clients["db"]

# Attach SQLite as additional log sink (after DB is created)
logger.attach_db(db)

qa_agent = QAAgent(clients["neo4j_client"], clients["chat_client"], clients["embed_client"])

logger.info("app.startup", chat_provider=settings.chat_provider,
            embed_provider=settings.embed_provider)

app = FastAPI()
base = Path(__file__).parent
app.mount("/static", StaticFiles(directory=base / "static"), name="static")
templates = Jinja2Templates(directory=base / "templates")

MAX_HISTORY_TURNS = 20

# Rate limits: (max_requests, window_seconds)
RATE_LIMITS = {
    "chat": (20, 3600),     # 20 queries/hour — each costs ~$0.01
    "read": (60, 3600),     # 60 reads/hour for browsing endpoints
}


def _visitor_id(request: Request, fp: str | None = None) -> str:
    """Build a composite visitor ID from IP + browser fingerprint."""
    ip = request.client.host if request.client else "unknown"
    raw = f"{ip}:{fp or 'none'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _check_limit(visitor_id: str, bucket: str) -> JSONResponse | None:
    """Return a 429 response if rate limited, else None."""
    max_req, window = RATE_LIMITS[bucket]
    allowed, remaining = db.check_rate_limit(visitor_id, bucket, max_req, window)
    if not allowed:
        logger.warning("rate_limit.exceeded", visitor_id=visitor_id, bucket=bucket)
        return JSONResponse(
            {"error": "Rate limit exceeded. Please try again later.",
             "retry_after_seconds": window},
            status_code=429,
            headers={"Retry-After": str(window)},
        )
    return None


@app.get("/")
def index(request: Request):
    with clients["neo4j_client"].driver.session() as s:
        r = s.run("MATCH (e:Engineer) RETURN e.name AS name LIMIT 1").single()
    name = r["name"] if r else "Engineer"
    return templates.TemplateResponse("index.html", {"request": request, "name": name})


@app.get("/api/chat")
def chat(request: Request, q: str, session_id: str | None = None, fp: str | None = None):
    vid = _visitor_id(request, fp)
    blocked = _check_limit(vid, "chat")
    if blocked:
        return blocked

    # Resolve or create session
    if session_id and db.session_exists(session_id):
        sid = session_id
    else:
        sid = session_id or uuid.uuid4().hex[:12]

    # Load conversation history from DB
    history = db.get_session_history(sid, limit=MAX_HISTORY_TURNS * 2)

    def generate():
        t0 = time.perf_counter()
        logger.start_session(query=q, source="api/chat")

        yield f"event: session\ndata: {json.dumps({'session_id': sid})}\n\n"

        assistant_text = ""
        for chunk in qa_agent.answer_stream(q, history=history):
            if isinstance(chunk, dict):
                if chunk.get("_status"):
                    yield f"event: status\ndata: {json.dumps(chunk)}\n\n"
                else:
                    yield f"event: graph\ndata: {json.dumps(chunk)}\n\n"
            else:
                assistant_text = chunk
                sse = "".join(f"data: {line}\n" for line in chunk.split("\n"))
                yield sse + "\n"
        yield "data: [DONE]\n\n"

        # Persist this turn (answer without evidence section to save space)
        answer_for_history = assistant_text.split("\n**Evidence:**")[0].strip()
        db.save_message(sid, "user", q)
        db.save_message(sid, "assistant", answer_for_history)

        latency = int((time.perf_counter() - t0) * 1000)
        logger.end_session()
        logger.log_request(method="GET", path="/api/chat", query=q,
                           latency_ms=latency, session_id=sid,
                           visitor_id=vid, history_turns=len(history) // 2)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# History & log browsing endpoints
# ---------------------------------------------------------------------------

@app.get("/api/sessions")
def list_sessions(request: Request, limit: int = 50, offset: int = 0):
    vid = _visitor_id(request)
    blocked = _check_limit(vid, "read")
    if blocked:
        return blocked
    return db.list_sessions(limit=limit, offset=offset)


@app.get("/api/sessions/{session_id}")
def get_session(request: Request, session_id: str):
    vid = _visitor_id(request)
    blocked = _check_limit(vid, "read")
    if blocked:
        return blocked
    messages = db.get_session_history(session_id, limit=1000)
    if not messages:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"session_id": session_id, "messages": messages}


@app.get("/api/logs")
def query_logs(request: Request, session_id: str | None = None, event: str | None = None,
               level: str | None = None, limit: int = 100, offset: int = 0):
    vid = _visitor_id(request)
    blocked = _check_limit(vid, "read")
    if blocked:
        return blocked
    return db.query_logs(session_id=session_id, event=event, level=level,
                         limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Periodic cleanup (runs on startup, then every hour via background task)
# ---------------------------------------------------------------------------

@app.on_event("startup")
def _startup_cleanup():
    db.cleanup_rate_limits()
