TAXONOMY = {
    "AI & Machine Learning": {
        "LLM & Generative AI": ["LLM Integration", "Prompt Engineering", "Fine-Tuning", "Embeddings", "Model Serving"],
        "Agentic AI": ["Multi-Agent Orchestration", "Agentic AI", "RAG", "MCP Protocol"],
        "Classical ML": ["scikit-learn", "PyTorch", "TensorFlow", "MLOps"],
        "NLP & Vision": ["NLP", "Computer Vision"],
    },
    "Backend Engineering": {
        "Web Frameworks": ["FastAPI", "Django", "Flask", "Express.js"],
        "API & Protocols": ["REST API Design", "GraphQL", "gRPC", "WebSocket"],
        "Architecture Patterns": ["Async Programming", "Microservices", "Event-Driven Architecture", "Distributed Systems", "Message Queues"],
    },
    "Frontend Engineering": {
        "Frameworks": ["React", "Next.js", "Vue.js"],
        "Languages & Styling": ["TypeScript", "Tailwind CSS"],
        "Visualization": ["D3.js", "Three.js / WebGL"],
        "State & Rendering": ["State Management", "SSR / SSG", "Component Libraries"],
    },
    "Data Engineering": {
        "Orchestration": ["Data Pipelines", "dbt"],
        "Processing": ["Apache Spark", "Apache Kafka", "Pandas", "Parquet / Arrow"],
        "Storage & Modeling": ["Data Warehousing", "Data Modeling"],
    },
    "Cloud & Infrastructure": {
        "Cloud Providers": ["AWS", "GCP", "Azure"],
        "Containers & Orchestration": ["Docker", "Kubernetes"],
        "IaC & CI/CD": ["Terraform", "CI/CD"],
    },
    "Security": {
        "Offensive Security": ["Penetration Testing", "MITRE ATT&CK", "Credential Harvesting"],
        "Application Security": ["OWASP", "Vulnerability Assessment", "DevSecOps"],
        "Infrastructure Security": ["Network Security", "Cryptography", "Secrets Management"],
    },
    "DevOps & SRE": {
        "Observability": ["Observability", "Logging", "Monitoring"],
        "Automation": ["Infrastructure Automation"],
    },
    "Databases": {
        "Relational": ["PostgreSQL", "SQLAlchemy"],
        "NoSQL & Graph": ["Neo4j", "MongoDB", "Redis", "DuckDB"],
        "Search & Vector": ["Vector Databases", "Elasticsearch"],
    },
    "Software Engineering": {
        "Quality & Design": ["Testing", "Design Patterns", "API Design", "Performance Optimization"],
    },
    "Emerging Tech": {
        "Real-Time & Streaming": ["Streaming / SSE", "Real-Time Systems"],
    },
    "Domain-Specific": {
        "Specialized": ["Geospatial", "Financial / Trading", "PDF Processing", "Web Scraping", "Audio / Signal Processing"],
    },
}

ALL_SKILLS = [skill for domain in TAXONOMY.values() for cat in domain.values() for skill in cat]

SKILL_HIERARCHY = {
    skill: (domain_name, cat_name)
    for domain_name, categories in TAXONOMY.items()
    for cat_name, skills in categories.items()
    for skill in skills
}

CATEGORY_TO_DOMAIN: dict[str, str] = {
    cat: domain
    for domain, categories in TAXONOMY.items()
    for cat in categories
}

# Maps resume keywords (orphan CLAIMS nodes) to taxonomy.
# skill→skill for near-matches, "cat:X" for broad terms placed under a category.
RESUME_SKILL_ALIASES: dict[str, str] = {
    # Near-match → exact taxonomy skill name
    "React.js": "React",
    "LLM": "LLM Integration",
    "APIs": "REST API Design",
    "Automation": "Infrastructure Automation",
    # Broad terms → closest taxonomy category
    "Python": "cat:Web Frameworks",
    "JavaScript": "cat:Frameworks",
    "Machine Learning": "cat:Classical ML",
    "SQL": "cat:Relational",
    "HTML/CSS": "cat:Languages & Styling",
    "Git": "cat:IaC & CI/CD",
    "Redshift": "cat:Storage & Modeling",
    "Snowflake": "cat:Storage & Modeling",
}
