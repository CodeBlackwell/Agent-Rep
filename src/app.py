import json
import hashlib
import mimetypes
import os
import time
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

mimetypes.add_type("image/webp", ".webp")
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config.settings import Settings
from src.core import logger
from src.core.client_factory import build_clients
from src.jd_match import JDMatchAgent
from src.jd_match.extract import extract_text
from src.qa.agent import QAAgent

settings = Settings.load()
clients = build_clients(settings)
db = clients["db"]

# Cache-bust key: hash of all static files so browsers refetch on deploy
def _static_hash() -> str:
    h = hashlib.md5()
    static_dir = Path(__file__).parent / "static"
    for f in sorted(static_dir.glob("*.min.css")) + sorted(static_dir.glob("*.min.js")):
        h.update(f.read_bytes())
    return h.hexdigest()[:8]

STATIC_V = _static_hash()
DEV_MODE = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes")

# Cypher fragment: exclude static/generated assets from snippet queries
_SKIP_ASSET_PATHS = (
    "AND NONE(seg IN split(f.path, '/') WHERE seg IN ['static', 'public', 'vendor', 'generated', 'assets']) "
    "AND NOT f.path ENDS WITH '.min.js' AND NOT f.path ENDS WITH '.min.css' "
)

# Attach SQLite as additional log sink (after DB is created)
logger.attach_db(db)

qa_agent = QAAgent(clients["neo4j_client"], clients["chat_client"], clients["embed_client"],
                   show_private_code=settings.show_private_code,
                   github_owner=settings.github_owner)
jd_agent = JDMatchAgent(clients["neo4j_client"], clients["chat_client"], clients["embed_client"])

logger.info("app.startup", chat_provider=settings.chat_provider,
            embed_provider=settings.embed_provider)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.cleanup_rate_limits()
    yield


app = FastAPI(lifespan=lifespan)
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


_BOT_UA_FRAGMENTS = (
    "facebookexternalhit", "twitterbot", "slackbot", "linkedinbot",
    "whatsapp", "telegrambot", "discordbot", "googlebot", "bingbot",
    "applebot", "iframely", "opengraph", "embedly", "showyoubot",
    "outbrain", "pinterestbot", "bitlybot",
)

BYPASS_TOKEN = os.getenv("RATE_LIMIT_BYPASS", "")


def _is_local(request: Request) -> bool:
    ip = request.client.host if request.client else ""
    return ip in ("127.0.0.1", "::1", "localhost")


def _skip_limit(request: Request) -> bool:
    """Skip rate limiting for localhost, known bots, or bypass token."""
    if _is_local(request):
        return True
    # Bypass via secret header (for owner testing)
    if BYPASS_TOKEN and request.headers.get("x-bypass-token") == BYPASS_TOKEN:
        return True
    # Exempt crawlers/bots so link previews always work
    ua = (request.headers.get("user-agent") or "").lower()
    return any(bot in ua for bot in _BOT_UA_FRAGMENTS)


def _check_limit(visitor_id: str, bucket: str, request: Request | None = None) -> JSONResponse | None:
    """Return a 429 response if rate limited, else None. Skips for localhost, bots, and bypass token."""
    if request and _skip_limit(request):
        return None
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
    return templates.TemplateResponse("index.html", {
        "request": request, "name": name,
        "github_owner": settings.github_owner,
        "cdn_base": settings.cdn_base,
        "static_v": STATIC_V,
        "dev_mode": DEV_MODE,
    })


@app.get("/api/chat")
def chat(request: Request, q: str, session_id: str | None = None, fp: str | None = None):
    vid = _visitor_id(request, fp)
    blocked = _check_limit(vid, "chat", request)
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
                elif chunk.get("_evidence"):
                    yield f"event: evidence\ndata: {json.dumps(chunk)}\n\n"
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
# Repository overview (repo tiles on landing page)
# ---------------------------------------------------------------------------

@app.get("/api/repositories")
def list_repositories(request: Request):
    vid = _visitor_id(request)
    blocked = _check_limit(vid, "read", request)
    if blocked:
        return blocked

    neo4j = clients["neo4j_client"]
    with neo4j.driver.session() as s:
        rows = s.run(
            "MATCH (r:Repository) "
            "OPTIONAL MATCH (r)-[:CONTAINS]->(:File)-[:CONTAINS]->(cs:CodeSnippet)-[:DEMONSTRATES]->(sk:Skill) "
            "OPTIONAL MATCH (d:Domain)-[:CONTAINS]->(:Category)-[:CONTAINS]->(sk) "
            "WITH r, d.name AS domain, count(DISTINCT sk) AS skill_count, count(cs) AS snippet_count "
            "RETURN r.name AS name, r.display_name AS display_name, r.private AS private, "
            "       collect({domain: domain, skill_count: skill_count, snippets: snippet_count}) AS domains "
            "ORDER BY r.name"
        ).data()

    return [
        {"name": r["name"], "display_name": r["display_name"] or r["name"],
         "private": bool(r["private"]) if r["private"] else False,
         "domains": [d for d in r["domains"] if d["domain"]]}
        for r in rows
    ]


REPO_BREAKDOWNS = {
    "SPICE": {
        "tagline": "Self-Piloting Intelligent Capital Engine",
        "summary": "Full-stack autonomous trading system that runs 24/7 on AWS. "
                   "Modular service architecture with real-time market data ingestion, "
                   "strategy execution, risk management, and a React dashboard for monitoring live positions.",
        "stack": ["Python", "FastAPI", "React", "PostgreSQL/TimescaleDB", "Redis", "Docker", "AWS"],
        "url": "https://spice.letitcook.ing",
    },
    "PROVE": {
        "tagline": "Portfolio Reasoning Over Verified Evidence",
        "summary": "This portfolio app. An AI agent reasons over a Neo4j knowledge graph of real code snippets "
                   "to answer questions about skills and experience, backed by vector search and streaming SSE responses.",
        "stack": ["Python", "FastAPI", "Neo4j", "D3.js", "Anthropic", "Voyage AI"],
        "url": "https://prove.codeblackwell.ai",
    },
    "C.R.A.C.K.": {
        "tagline": "Comprehensive Recon & Attack Creation Kit",
        "summary": "Modular pentesting toolkit featuring 700+ commands, 50+ attack chains, and Neo4j-powered "
                   "attack path visualization. Because methodology beats memorization.",
        "stack": ["Python", "Bash", "Nmap", "Burp Suite", "Metasploit", "Neo4j", "Docker"],
    },
    "Flow-Ohana": {
        "tagline": "Collaborative Workflow Platform",
        "summary": "Full-stack team collaboration app with real-time updates, role-based access control, "
                   "and a rich frontend. End-to-end tested with comprehensive integration coverage.",
        "stack": ["Python", "FastAPI", "React", "PostgreSQL", "WebSockets", "Docker"],
    },
    "PANEL": {
        "tagline": "Multi-Agent PRD Stress-Testing System",
        "summary": "13 specialized AI agents debate architecture, security, and UX before you write a line of code. "
                   "3 judges score the result, then packages a complete PRD with transcripts and structured exports.",
        "stack": ["Python", "FastAPI", "AutoGen", "Vue 3", "GPT-4o"],
        "url": "https://panel.codeblackwell.ai",
    },
    "Agent_Blackwell": {
        "tagline": "Modular AI Agent Orchestration System",
        "summary": "A symphony of expert AI agents communicating via the Agent Communication Protocol (ACP). "
                   "Specialized agents seamlessly integrate their capabilities to deconstruct and resolve intricate challenges.",
        "stack": ["Python", "Redis", "Pinecone", "MCP", "Linear API"],
    },
    "kata": {
        "tagline": "Declarative Schema Engine",
        "summary": "Schema definition and validation library with a live playground demo. "
                   "Define data shapes declaratively and generate validators, migrations, and documentation from a single source.",
        "stack": ["Python", "FastAPI", "D3.js", "CodeMirror"],
        "url": "https://kata.codeblackwell.ai",
    },
    "veridatum": {
        "tagline": "Cross-Source DataFrame Comparison Library",
        "summary": "Data validation framework and cross-source comparison engine. "
                   "Compares DataFrames across sources with configurable rules, web monitoring, and detailed diff reports.",
        "stack": ["Python", "FastAPI", "D3.js", "Pandas"],
        "url": "https://veridatum.codeblackwell.ai",
    },
    "d3_visualization_gallery": {
        "tagline": "D3 Visualization Gallery",
        "summary": "Collection of D3.js visualizations built with TypeScript and modern React. "
                   "Explores different chart types, layouts, and interaction patterns with hot reloading.",
        "stack": ["TypeScript", "React", "D3.js", "Vite"],
    },
    "POI_Alchemist": {
        "tagline": "Point-of-Interest Data Enrichment",
        "summary": "Geospatial data pipeline that enriches raw location data with contextual metadata, "
                   "scoring, and categorization using ML classifiers and external APIs.",
        "stack": ["Python", "Pandas", "scikit-learn", "GeoPandas"],
    },
    "A.U.R.A-Avantlink_Universal_Reporting_Assistant": {
        "tagline": "Avantlink Universal Reporting Assistant",
        "summary": "Fine-tuned code generation model for automated affiliate marketing report creation. "
                   "Custom training pipeline with data preprocessing, model training, and inference serving.",
        "stack": ["Python", "Transformers", "PyTorch"],
    },
}


@app.get("/api/repositories/{repo_name}")
def get_repository_detail(repo_name: str, request: Request):
    vid = _visitor_id(request)
    blocked = _check_limit(vid, "read", request)
    if blocked:
        return blocked

    neo4j = clients["neo4j_client"]
    owner = os.getenv("GITHUB_OWNER", "codeblackwell")
    with neo4j.driver.session() as s:
        meta = s.run(
            "MATCH (r:Repository {name: $name}) "
            "RETURN r.tagline AS tagline, r.summary AS summary, r.stack AS stack, r.url AS url",
            name=repo_name,
        ).single()

        rows = s.run(
            "MATCH (r:Repository {name: $name})-[:CONTAINS]->(f:File)-[:CONTAINS]->(cs:CodeSnippet)-[:DEMONSTRATES]->(sk:Skill) "
            "WHERE true " + _SKIP_ASSET_PATHS +
            "OPTIONAL MATCH (d:Domain)-[:CONTAINS]->(cat:Category)-[:CONTAINS]->(sk) "
            "RETURN d.name AS domain, sk.name AS skill, count(cs) AS snippets, "
            "       collect(DISTINCT {file: f.path, start: cs.start_line, branch: r.default_branch})[0..3] AS files "
            "ORDER BY domain, snippets DESC",
            name=repo_name,
        ).data()

    if not rows:
        return JSONResponse({"error": "not found"}, status_code=404)

    domains = {}
    for r in rows:
        d = r["domain"] or "Other"
        if d not in domains:
            domains[d] = []
        files = [
            f"https://github.com/{owner}/{repo_name}/blob/{f['branch'] or 'main'}/{f['file']}#L{f['start']}"
            for f in (r["files"] or []) if f.get("file")
        ]
        domains[d].append({"skill": r["skill"], "snippets": r["snippets"], "files": files})

    # Prefer Neo4j metadata, fall back to hardcoded dict during migration
    if meta and meta["tagline"]:
        breakdown = {k: v for k, v in dict(meta).items() if v}
        if "stack" in breakdown and isinstance(breakdown["stack"], list):
            pass  # already a list from Neo4j
    else:
        breakdown = REPO_BREAKDOWNS.get(repo_name, {})

    return {"name": repo_name, "domains": domains, "breakdown": breakdown}


# ---------------------------------------------------------------------------
# Repo-scoped skill snippets (lazy-loaded by detail view accordions)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=128)
def _repo_skill_snippets(repo_name: str, skill_name: str):
    neo4j = clients["neo4j_client"]
    owner = os.getenv("GITHUB_OWNER", "codeblackwell")
    with neo4j.driver.session() as s:
        rows = s.run(
            "MATCH (r:Repository {name: $repo})-[:CONTAINS]->(f:File)-[:CONTAINS]->(cs:CodeSnippet)-[:DEMONSTRATES]->(sk:Skill {name: $skill}) "
            "WHERE true " + _SKIP_ASSET_PATHS +
            "RETURN r.default_branch AS branch, r.private AS private, f.path AS path, "
            "cs.name AS snippet_name, cs.context AS context, cs.content AS content, "
            "cs.start_line AS start_line, cs.end_line AS end_line, cs.language AS lang "
            "ORDER BY f.path, cs.start_line",
            repo=repo_name, skill=skill_name,
        ).data()
    return [
        {
            "path": r["path"],
            "snippet_name": r["snippet_name"],
            "context": r["context"] or "",
            "content": "" if r["private"] else (r["content"] or ""),
            "start_line": r["start_line"] or 0,
            "end_line": r["end_line"] or 0,
            "language": r["lang"] or "",
            "private": bool(r["private"]) if r["private"] is not None else False,
            "branch": r["branch"] or "main",
            "url": f"https://github.com/{owner}/{repo_name}/blob/{r['branch'] or 'main'}/{r['path']}#L{r['start_line'] or 0}",
        }
        for r in rows
    ]


@app.get("/api/repositories/{repo_name}/skills/{skill_name}/snippets")
def repo_skill_snippets(repo_name: str, skill_name: str, request: Request):
    vid = _visitor_id(request)
    blocked = _check_limit(vid, "read", request)
    if blocked:
        return blocked
    snippets = _repo_skill_snippets(repo_name, skill_name)
    if not snippets:
        return JSONResponse({"error": "not found"}, status_code=404)
    return snippets


# ---------------------------------------------------------------------------
# History & log browsing endpoints
# ---------------------------------------------------------------------------

@app.get("/api/sessions")
def list_sessions(request: Request, limit: int = 50, offset: int = 0):
    vid = _visitor_id(request)
    blocked = _check_limit(vid, "read", request)
    if blocked:
        return blocked
    return db.list_sessions(limit=limit, offset=offset)


@app.get("/api/sessions/{session_id}")
def get_session(request: Request, session_id: str):
    vid = _visitor_id(request)
    blocked = _check_limit(vid, "read", request)
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
    blocked = _check_limit(vid, "read", request)
    if blocked:
        return blocked
    return db.query_logs(session_id=session_id, event=event, level=level,
                         limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Skill reference detail endpoint
# ---------------------------------------------------------------------------

@app.get("/api/skills/{skill_name}/references")
def skill_references(request: Request, skill_name: str):
    vid = _visitor_id(request)
    blocked = _check_limit(vid, "read", request)
    if blocked:
        return blocked

    neo4j = clients["neo4j_client"]
    with neo4j.driver.session() as s:
        # Skill metadata + hierarchy
        meta = s.run(
            "MATCH (d:Domain)-[:CONTAINS]->(c:Category)-[:CONTAINS]->(sk:Skill {name: $name}) "
            "RETURN d.name AS domain, c.name AS category, sk.proficiency AS proficiency, "
            "sk.snippet_count AS snippet_count, sk.repo_count AS repo_count",
            name=skill_name,
        ).single()

        if not meta:
            return JSONResponse({"error": "Skill not found"}, status_code=404)

        # All evidence snippets
        rows = s.run(
            "MATCH (f:File)-[:CONTAINS]->(cs:CodeSnippet)-[d:DEMONSTRATES]->(sk:Skill {name: $name}) "
            "MATCH (r:Repository)-[:CONTAINS]->(f) "
            "WHERE true " + _SKIP_ASSET_PATHS +
            "RETURN r.name AS repo, r.default_branch AS branch, r.private AS private, f.path AS path, "
            "cs.name AS snippet_name, cs.context AS context, cs.content AS content, "
            "cs.start_line AS start_line, cs.end_line AS end_line, "
            "cs.language AS lang, d.first_seen AS first_seen, d.last_seen AS last_seen, "
            "d.snippet_lines AS lines "
            "ORDER BY r.name, f.path, cs.start_line",
            name=skill_name,
        ).data()

    return {
        "skill": skill_name,
        "domain": meta["domain"],
        "category": meta["category"],
        "proficiency": meta["proficiency"],
        "snippet_count": meta["snippet_count"] or 0,
        "repo_count": meta["repo_count"] or 0,
        "references": [
            {
                "repo": r["repo"],
                "branch": r["branch"] or "main",
                "path": r["path"],
                "snippet_name": r["snippet_name"],
                "context": r["context"] or "",
                "content": "" if (r["private"]) else (r["content"] or ""),
                "start_line": r["start_line"] or 0,
                "end_line": r["end_line"] or 0,
                "language": r["lang"] or "",
                "first_seen": r["first_seen"] or "",
                "last_seen": r["last_seen"] or "",
                "lines": r["lines"] or 0,
                "private": bool(r["private"]) if r["private"] is not None else False,
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# JD Match endpoint
# ---------------------------------------------------------------------------

_MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB
_MAX_TEXT_CHARS = 50_000  # ~12 pages of text

@app.post("/api/jd-match")
async def jd_match(request: Request, file: UploadFile = File(None),
                   text: str = Form(None), fp: str = Form(None)):
    vid = _visitor_id(request, fp)
    blocked = _check_limit(vid, "chat", request)
    if blocked:
        return blocked

    if file and file.filename:
        content = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(content) > _MAX_UPLOAD_BYTES:
            return JSONResponse({"error": "File too large (2 MB max)"}, status_code=400)
        try:
            jd_text = extract_text(file.filename, content)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    elif text:
        if len(text) > _MAX_TEXT_CHARS:
            return JSONResponse({"error": "Text too long (50,000 char max)"}, status_code=400)
        jd_text = text
    else:
        return JSONResponse({"error": "Provide a file or text"}, status_code=400)

    if not jd_text.strip():
        return JSONResponse({"error": "Could not extract text from file"}, status_code=400)

    logger.info("jd_match.start", text_length=len(jd_text))
    report = jd_agent.match(jd_text)
    logger.info("jd_match.done", match_pct=report.match_percentage,
                req_count=len(report.requirements))
    return {
        "match_percentage": report.match_percentage,
        "summary": report.summary,
        "requirements": [
            {
                "requirement": r.requirement,
                "confidence": r.confidence,
                "evidence_count": len(r.evidence),
                "evidence": [
                    {
                        "repo": e.get("repo", ""),
                        "path": e.get("file_path", ""),
                        "start_line": e.get("start_line", 0),
                        "end_line": e.get("end_line", 0),
                        "context": e.get("context", ""),
                        "private": e.get("private", False),
                    }
                    for e in r.evidence[:5]
                ],
            }
            for r in report.requirements
        ],
    }


# ---------------------------------------------------------------------------
# SEO: Sitemap & skill HTML views
# ---------------------------------------------------------------------------

@app.get("/sitemap.xml", response_class=Response)
def sitemap():
    neo4j = clients["neo4j_client"]
    urls = ['  <url><loc>https://prove.codeblackwell.ai/</loc><priority>1.0</priority><changefreq>weekly</changefreq></url>']

    with neo4j.driver.session() as s:
        rows = s.run("MATCH (sk:Skill) RETURN sk.name AS name ORDER BY sk.name").data()

    for row in rows:
        name = row["name"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        slug = row["name"].replace(" ", "-").lower()
        urls.append(f'  <url><loc>https://prove.codeblackwell.ai/skills/{slug}</loc><priority>0.6</priority><changefreq>monthly</changefreq></url>')

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls)
    xml += "\n</urlset>\n"
    return Response(content=xml, media_type="application/xml")


@app.get("/skills/{skill_slug}")
def skill_page(request: Request, skill_slug: str):
    """SEO-friendly HTML page for an individual skill."""
    skill_name = skill_slug.replace("-", " ")

    neo4j = clients["neo4j_client"]
    with neo4j.driver.session() as s:
        # Case-insensitive match
        meta = s.run(
            "MATCH (d:Domain)-[:CONTAINS]->(c:Category)-[:CONTAINS]->(sk:Skill) "
            "WHERE toLower(sk.name) = toLower($name) "
            "RETURN sk.name AS name, d.name AS domain, c.name AS category, "
            "sk.proficiency AS proficiency, sk.snippet_count AS snippet_count, sk.repo_count AS repo_count",
            name=skill_name,
        ).single()

    if not meta:
        return templates.TemplateResponse("skill.html", {
            "request": request, "skill": None, "cdn_base": settings.cdn_base, "static_v": STATIC_V, "dev_mode": DEV_MODE,
        }, status_code=404)

    with neo4j.driver.session() as s:
        rows = s.run(
            "MATCH (f:File)-[:CONTAINS]->(cs:CodeSnippet)-[:DEMONSTRATES]->(sk:Skill) "
            "WHERE toLower(sk.name) = toLower($name) "
            "MATCH (r:Repository)-[:CONTAINS]->(f) "
            "WHERE true " + _SKIP_ASSET_PATHS +
            "RETURN r.name AS repo, f.path AS path, cs.name AS snippet_name, cs.context AS context, "
            "cs.start_line AS start_line, cs.end_line AS end_line, r.private AS private "
            "ORDER BY r.name, f.path LIMIT 10",
            name=skill_name,
        ).data()

        # Get engineer name
        eng = s.run("MATCH (e:Engineer) RETURN e.name AS name LIMIT 1").single()

    return templates.TemplateResponse("skill.html", {
        "request": request,
        "skill": {
            "name": meta["name"],
            "domain": meta["domain"],
            "category": meta["category"],
            "proficiency": meta["proficiency"] or "minimal",
            "snippet_count": meta["snippet_count"] or 0,
            "repo_count": meta["repo_count"] or 0,
            "references": [
                {
                    "repo": r["repo"],
                    "path": r["path"],
                    "snippet_name": r["snippet_name"],
                    "context": r["context"] or "",
                    "start_line": r["start_line"] or 0,
                    "end_line": r["end_line"] or 0,
                    "private": bool(r["private"]) if r["private"] is not None else False,
                }
                for r in rows
            ],
        },
        "engineer_name": eng["name"] if eng else "Engineer",
        "cdn_base": settings.cdn_base,
        "static_v": STATIC_V,
        "github_owner": settings.github_owner,
        "dev_mode": DEV_MODE,
    })


# ---------------------------------------------------------------------------
# Periodic cleanup (runs on startup, then every hour via background task)
# ---------------------------------------------------------------------------

