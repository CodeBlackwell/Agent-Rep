import json
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


@app.get("/")
def index(request: Request):
    with clients["neo4j_client"].driver.session() as s:
        r = s.run("MATCH (e:Engineer) RETURN e.name AS name LIMIT 1").single()
    name = r["name"] if r else "Engineer"
    return templates.TemplateResponse("index.html", {"request": request, "name": name})


@app.get("/api/chat")
def chat(q: str, session_id: str | None = None):
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
        summary = logger.end_session()
        logger.log_request(method="GET", path="/api/chat", query=q,
                           latency_ms=latency, session_id=sid,
                           history_turns=len(history) // 2)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# History & log browsing endpoints
# ---------------------------------------------------------------------------

@app.get("/api/sessions")
def list_sessions(limit: int = 50, offset: int = 0):
    return db.list_sessions(limit=limit, offset=offset)


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    messages = db.get_session_history(session_id, limit=1000)
    if not messages:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"session_id": session_id, "messages": messages}


@app.get("/api/logs")
def query_logs(session_id: str | None = None, event: str | None = None,
               level: str | None = None, limit: int = 100, offset: int = 0):
    return db.query_logs(session_id=session_id, event=event, level=level,
                         limit=limit, offset=offset)
