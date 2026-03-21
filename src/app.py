import json
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config.settings import Settings
from src.core import logger
from src.core.client_factory import build_clients
from src.qa.agent import QAAgent

settings = Settings.load()
clients = build_clients(settings)
qa_agent = QAAgent(clients["neo4j_client"], clients["chat_client"], clients["embed_client"])

logger.info("app.startup", chat_provider=settings.chat_provider,
            embed_provider=settings.embed_provider)

app = FastAPI()
base = Path(__file__).parent
app.mount("/static", StaticFiles(directory=base / "static"), name="static")
templates = Jinja2Templates(directory=base / "templates")

# ---------------------------------------------------------------------------
# Conversation session store (in-memory, capped at 200 sessions via LRU eviction)
# Each session stores condensed history: [{role, content}, ...] of user/assistant turns.
# ---------------------------------------------------------------------------
MAX_SESSIONS = 200
MAX_HISTORY_TURNS = 20  # max user+assistant pairs kept per session

_sessions: OrderedDict[str, list[dict]] = OrderedDict()


def _get_or_create_session(session_id: str | None) -> tuple[str, list[dict]]:
    """Return (session_id, history). Creates a new session if id is missing/unknown."""
    if session_id and session_id in _sessions:
        _sessions.move_to_end(session_id)
        return session_id, _sessions[session_id]
    new_id = session_id or uuid.uuid4().hex[:12]
    _sessions[new_id] = []
    if len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)
    return new_id, _sessions[new_id]


@app.get("/")
def index(request: Request):
    with clients["neo4j_client"].driver.session() as s:
        r = s.run("MATCH (e:Engineer) RETURN e.name AS name LIMIT 1").single()
    name = r["name"] if r else "Engineer"
    return templates.TemplateResponse("index.html", {"request": request, "name": name})


@app.get("/api/chat")
def chat(q: str, session_id: str | None = None):
    sid, history = _get_or_create_session(session_id)

    def generate():
        t0 = time.perf_counter()
        log_sid = logger.start_session(query=q, source="api/chat")

        # Send session_id to client on first event so it can include it in follow-ups
        yield f"event: session\ndata: {json.dumps({'session_id': sid})}\n\n"

        # Pass conversation history to agent
        assistant_text = ""
        for chunk in qa_agent.answer_stream(q, history=list(history)):
            if isinstance(chunk, dict):
                yield f"event: graph\ndata: {json.dumps(chunk)}\n\n"
            else:
                assistant_text = chunk
                sse = "".join(f"data: {line}\n" for line in chunk.split("\n"))
                yield sse + "\n"
        yield "data: [DONE]\n\n"

        # Store this turn in session history (condensed: just question + answer text)
        # Strip evidence section from stored answer to save context space
        answer_for_history = assistant_text.split("\n**Evidence:**")[0].strip()
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer_for_history})

        # Cap history length
        while len(history) > MAX_HISTORY_TURNS * 2:
            history.pop(0)
            history.pop(0)

        latency = int((time.perf_counter() - t0) * 1000)
        logger.end_session()
        logger.log_request(method="GET", path="/api/chat", query=q,
                           latency_ms=latency, session_id=sid,
                           history_turns=len(history) // 2)

    return StreamingResponse(generate(), media_type="text/event-stream")
