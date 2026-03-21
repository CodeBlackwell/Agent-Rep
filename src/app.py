import json
import time
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


@app.get("/")
def index(request: Request):
    with clients["neo4j_client"].driver.session() as s:
        r = s.run("MATCH (e:Engineer) RETURN e.name AS name LIMIT 1").single()
    name = r["name"] if r else "Engineer"
    return templates.TemplateResponse("index.html", {"request": request, "name": name})


@app.get("/api/chat")
def chat(q: str):
    def generate():
        t0 = time.perf_counter()
        sid = logger.start_session(query=q, source="api/chat")

        for chunk in qa_agent.answer_stream(q):
            if isinstance(chunk, dict):
                yield f"event: graph\ndata: {json.dumps(chunk)}\n\n"
            else:
                sse = "".join(f"data: {line}\n" for line in chunk.split("\n"))
                yield sse + "\n"
        yield "data: [DONE]\n\n"

        latency = int((time.perf_counter() - t0) * 1000)
        summary = logger.end_session()
        logger.log_request(method="GET", path="/api/chat", query=q,
                           latency_ms=latency)

    return StreamingResponse(generate(), media_type="text/event-stream")
