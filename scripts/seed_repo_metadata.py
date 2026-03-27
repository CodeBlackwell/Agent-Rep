"""Seed Repository nodes with display metadata (tagline, summary, stack, url, display_name).

Run once to populate, idempotent via MERGE + SET:
  uv run python scripts/seed_repo_metadata.py
"""
from src.config.settings import Settings
from src.core import Neo4jClient

METADATA = {
    "SPICE": {
        "display_name": "SPICE",
        "tagline": "Self-Piloting Intelligent Capital Engine",
        "summary": "Full-stack autonomous trading system that runs 24/7 on AWS. "
                   "Modular service architecture with real-time market data ingestion, "
                   "strategy execution, risk management, and a React dashboard for monitoring live positions.",
        "stack": ["Python", "FastAPI", "React", "PostgreSQL/TimescaleDB", "Redis", "Docker", "AWS"],
        "url": "https://spice.letitcook.ing",
    },
    "PROVE": {
        "display_name": "PROVE",
        "tagline": "Portfolio Reasoning Over Verified Evidence",
        "summary": "This portfolio app. An AI agent reasons over a Neo4j knowledge graph of real code snippets "
                   "to answer questions about skills and experience, backed by vector search and streaming SSE responses.",
        "stack": ["Python", "FastAPI", "Neo4j", "D3.js", "Anthropic", "Voyage AI"],
        "url": "https://prove.codeblackwell.ai",
    },
    "C.R.A.C.K.": {
        "display_name": "C.R.A.C.K.",
        "tagline": "Comprehensive Recon & Attack Creation Kit",
        "summary": "Modular pentesting toolkit featuring 700+ commands, 50+ attack chains, and Neo4j-powered "
                   "attack path visualization. Because methodology beats memorization.",
        "stack": ["Python", "Bash", "Nmap", "Burp Suite", "Metasploit", "Neo4j", "Docker"],
    },
    "Flow-Ohana": {
        "display_name": "Flow Ohana",
        "tagline": "Collaborative Workflow Platform",
        "summary": "Full-stack team collaboration app with real-time updates, role-based access control, "
                   "and a rich frontend. End-to-end tested with comprehensive integration coverage.",
        "stack": ["Python", "FastAPI", "React", "PostgreSQL", "WebSockets", "Docker"],
    },
    "PANEL": {
        "display_name": "PANEL",
        "tagline": "Multi-Agent PRD Stress-Testing System",
        "summary": "13 specialized AI agents debate architecture, security, and UX before you write a line of code. "
                   "3 judges score the result, then packages a complete PRD with transcripts and structured exports.",
        "stack": ["Python", "FastAPI", "AutoGen", "Vue 3", "GPT-4o"],
        "url": "https://panel.codeblackwell.ai",
    },
    "Agent_Blackwell": {
        "display_name": "Agent Blackwell",
        "tagline": "Modular AI Agent Orchestration System",
        "summary": "A symphony of expert AI agents communicating via the Agent Communication Protocol (ACP). "
                   "Specialized agents seamlessly integrate their capabilities to deconstruct and resolve intricate challenges.",
        "stack": ["Python", "Redis", "Pinecone", "MCP", "Linear API"],
    },
    "kata": {
        "display_name": "Kata",
        "tagline": "Declarative Schema Engine",
        "summary": "Schema definition and validation library with a live playground demo. "
                   "Define data shapes declaratively and generate validators, migrations, and documentation from a single source.",
        "stack": ["Python", "FastAPI", "D3.js", "CodeMirror"],
        "url": "https://kata.codeblackwell.ai",
    },
    "veridatum": {
        "display_name": "Veridatum",
        "tagline": "Cross-Source DataFrame Comparison Library",
        "summary": "Data validation framework and cross-source comparison engine. "
                   "Compares DataFrames across sources with configurable rules, web monitoring, and detailed diff reports.",
        "stack": ["Python", "FastAPI", "D3.js", "Pandas"],
        "url": "https://veridatum.codeblackwell.ai",
    },
    "d3_visualization_gallery": {
        "display_name": "D3 Visualization Gallery",
        "tagline": "D3 Visualization Gallery",
        "summary": "Collection of D3.js visualizations built with TypeScript and modern React. "
                   "Explores different chart types, layouts, and interaction patterns with hot reloading.",
        "stack": ["TypeScript", "React", "D3.js", "Vite"],
    },
    "POI_Alchemist": {
        "display_name": "P.o.I Alchemist",
        "tagline": "Point-of-Interest Data Enrichment",
        "summary": "Geospatial data pipeline that enriches raw location data with contextual metadata, "
                   "scoring, and categorization using ML classifiers and external APIs.",
        "stack": ["Python", "Pandas", "scikit-learn", "GeoPandas"],
    },
    "A.U.R.A-Avantlink_Universal_Reporting_Assistant": {
        "display_name": "A.U.R.A.",
        "tagline": "Avantlink Universal Reporting Assistant",
        "summary": "Fine-tuned code generation model for automated affiliate marketing report creation. "
                   "Custom training pipeline with data preprocessing, model training, and inference serving.",
        "stack": ["Python", "Transformers", "PyTorch"],
    },
}


def seed():
    settings = Settings.load()
    neo4j = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)

    with neo4j.driver.session() as session:
        for name, meta in METADATA.items():
            session.run(
                "MATCH (r:Repository {name: $name}) "
                "SET r.display_name = $display_name, r.tagline = $tagline, "
                "    r.summary = $summary, r.stack = $stack, r.url = $url",
                name=name,
                display_name=meta.get("display_name", name),
                tagline=meta.get("tagline", ""),
                summary=meta.get("summary", ""),
                stack=meta.get("stack", []),
                url=meta.get("url", ""),
            )
            print(f"  {name} → {meta.get('display_name', name)}")

    neo4j.driver.close()
    print("Done.")


if __name__ == "__main__":
    seed()
