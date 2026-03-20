import json
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config.settings import Settings
from src.core.client_factory import build_clients
from src.qa.agent import QAAgent

settings = Settings.load()
clients = build_clients(settings)
qa_agent = QAAgent(clients["neo4j_client"], clients["chat_client"], clients["embed_client"])

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
        for chunk in qa_agent.answer_stream(q):
            if isinstance(chunk, dict):
                yield f"event: graph\ndata: {json.dumps(chunk)}\n\n"
            else:
                sse = "".join(f"data: {line}\n" for line in chunk.split("\n"))
                yield sse + "\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
