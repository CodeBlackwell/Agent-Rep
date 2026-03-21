from neo4j import GraphDatabase

EMBED_PROVIDERS = ("nim", "voyage")


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str, embed_provider: str = "nim"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        if embed_provider not in EMBED_PROVIDERS:
            raise ValueError(f"embed_provider must be one of {EMBED_PROVIDERS}, got '{embed_provider}'")
        self.embed_provider = embed_provider
        self.embed_property = f"embedding_{embed_provider}"
        self.vector_index = f"code_embedding_{embed_provider}"

    def init_schema(self):
        with self.driver.session() as session:
            for label in ("Skill", "Repository", "Engineer", "Domain", "Category"):
                session.run(
                    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.name IS UNIQUE"
                )
            for provider in EMBED_PROVIDERS:
                prop = f"embedding_{provider}"
                idx = f"code_embedding_{provider}"
                session.run(
                    f"CREATE VECTOR INDEX {idx} IF NOT EXISTS "
                    f"FOR (n:CodeSnippet) ON (n.{prop}) "
                    "OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}"
                )

    def ensure_taxonomy(self, taxonomy: dict):
        with self.driver.session() as session:
            for domain_name, categories in taxonomy.items():
                session.run("MERGE (d:Domain {name: $name})", name=domain_name)
                for cat_name, skills in categories.items():
                    session.run(
                        "MERGE (c:Category {name: $cat}) "
                        "WITH c MATCH (d:Domain {name: $dom}) "
                        "MERGE (d)-[:CONTAINS]->(c)",
                        cat=cat_name, dom=domain_name,
                    )
                    for skill_name in skills:
                        session.run(
                            "MERGE (s:Skill {name: $skill}) "
                            "WITH s MATCH (c:Category {name: $cat}) "
                            "MERGE (c)-[:CONTAINS]->(s)",
                            skill=skill_name, cat=cat_name,
                        )

    def compute_repo_rollups(self, repo_name: str):
        with self.driver.session() as session:
            session.run(
                "MATCH (r:Repository {name: $repo})-[:CONTAINS]->(:File)-[:CONTAINS]->"
                "(cs:CodeSnippet)-[:DEMONSTRATES]->(s:Skill) "
                "WITH r, s, count(cs) AS snippet_count, "
                "sum(cs.end_line - cs.start_line + 1) AS total_lines "
                "MERGE (r)-[d:DEMONSTRATES]->(s) "
                "SET d.snippet_count = snippet_count, d.total_lines = total_lines",
                repo=repo_name,
            )

    def compute_proficiency(self):
        with self.driver.session() as session:
            session.run(
                "MATCH (s:Skill) "
                "OPTIONAL MATCH (cs:CodeSnippet)-[:DEMONSTRATES]->(s) "
                "OPTIONAL MATCH (r:Repository)-[:DEMONSTRATES]->(s) "
                "WITH s, count(DISTINCT cs) AS snippets, count(DISTINCT r) AS repos "
                "SET s.proficiency = CASE "
                "  WHEN snippets >= 10 AND repos >= 2 THEN 'extensive' "
                "  WHEN snippets >= 3 THEN 'moderate' "
                "  WHEN snippets >= 1 THEN 'minimal' "
                "  ELSE 'none' END, "
                "s.snippet_count = snippets, s.repo_count = repos"
            )

    def get_skill_with_hierarchy(self, skill_name: str) -> dict | None:
        query = (
            "MATCH (d:Domain)-[:CONTAINS]->(c:Category)-[:CONTAINS]->(s:Skill {name: $name}) "
            "RETURN s.name AS skill, d.name AS domain, c.name AS category, "
            "s.proficiency AS proficiency, s.snippet_count AS snippet_count"
        )
        with self.driver.session() as session:
            record = session.run(query, name=skill_name).single()
            return dict(record) if record else None

    def vector_search(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        # Fetch extra candidates so test-file demotion doesn't starve results
        query = (
            f"CALL db.index.vector.queryNodes('{self.vector_index}', $fetch_k, $embedding) "
            "YIELD node, score "
            "OPTIONAL MATCH (r:Repository)-[:CONTAINS]->(:File)-[:CONTAINS]->(node) "
            "OPTIONAL MATCH (node)-[:DEMONSTRATES]->(sk:Skill) "
            "WITH node, score, r, collect(DISTINCT sk.name) AS skills "
            "WITH properties(node) AS props, skills, score, r, "
            "CASE WHEN node.file_path =~ '.*(?i)(test_|_test\\\\.|spec\\\\.|/tests?/).*' "
            "THEN score * 0.7 ELSE score END AS adjusted_score "
            "RETURN props, adjusted_score AS score, r.name AS repo, "
            "r.private AS private, skills "
            "ORDER BY adjusted_score DESC LIMIT $top_k"
        )
        with self.driver.session() as session:
            result = session.run(query, embedding=embedding, top_k=top_k,
                                 fetch_k=top_k + 5)
            return [{"props": r["props"], "score": r["score"], "repo": r["repo"],
                     "private": bool(r["private"]), "skills": r["skills"]} for r in result]

    def get_skill_evidence(self, skill_name: str) -> list[dict]:
        query = (
            "MATCH (c:CodeSnippet)-[d:DEMONSTRATES]->(s:Skill {name: $name}) "
            "OPTIONAL MATCH (r:Repository)-[:CONTAINS]->(:File)-[:CONTAINS]->(c) "
            "RETURN properties(c) AS props, d.first_seen AS first_seen, "
            "d.last_seen AS last_seen, s.proficiency AS proficiency, "
            "r.name AS repo, r.private AS private "
            "LIMIT 10"
        )
        with self.driver.session() as session:
            result = session.run(query, name=skill_name)
            return [
                {**r["props"], "first_seen": str(r["first_seen"]) if r["first_seen"] else None,
                 "last_seen": str(r["last_seen"]) if r["last_seen"] else None,
                 "proficiency": r["proficiency"], "repo": r["repo"],
                 "private": bool(r["private"])}
                for r in result
            ]

    def get_competency_map(self) -> list[dict]:
        query = (
            "MATCH (d:Domain)-[:CONTAINS]->(c:Category)-[:CONTAINS]->(s:Skill) "
            "WHERE s.proficiency IS NOT NULL AND s.proficiency <> 'none' "
            "OPTIONAL MATCH (cs:CodeSnippet)-[:DEMONSTRATES]->(s) "
            "RETURN d.name AS domain, c.name AS category, s.name AS skill, "
            "s.proficiency AS proficiency, count(cs) AS evidence_count"
        )
        with self.driver.session() as session:
            result = session.run(query)
            return [dict(r) for r in result]

    def get_repo_overview(self, repo_name: str) -> dict | None:
        query = (
            "MATCH (r:Repository {name: $name}) "
            "OPTIONAL MATCH (r)-[:CONTAINS]->(f:File) "
            "WITH r, collect(DISTINCT f.path) AS files "
            "OPTIONAL MATCH (r)-[d:DEMONSTRATES]->(s:Skill) "
            "WITH r, files, s, d ORDER BY d.snippet_count DESC "
            "WITH r, files, "
            "collect({skill: s.name, proficiency: s.proficiency, "
            "snippet_count: d.snippet_count, total_lines: d.total_lines}) AS skills "
            "RETURN r.name AS name, r.path AS path, "
            "size(files) AS file_count, files[..20] AS sample_files, "
            "skills[..10] AS top_skills"
        )
        with self.driver.session() as session:
            record = session.run(query, name=repo_name).single()
            return dict(record) if record else None

    def get_connected_snippets(self, skill_name: str, repo_name: str) -> list[dict]:
        query = (
            "MATCH (r:Repository {name: $repo})-[:CONTAINS]->(f:File)"
            "-[:CONTAINS]->(cs:CodeSnippet)-[:DEMONSTRATES]->(s:Skill {name: $skill}) "
            "OPTIONAL MATCH (cs)-[:DEMONSTRATES]->(other:Skill) "
            "WHERE other.name <> $skill "
            "WITH r, f, cs, s, collect(DISTINCT other.name) AS related_skills "
            "ORDER BY f.path, cs.start_line "
            "RETURN f.path AS file_path, cs.name AS snippet_name, "
            "cs.start_line AS start_line, cs.end_line AS end_line, "
            "cs.content AS content, cs.context AS context, "
            "s.proficiency AS proficiency, r.private AS private, related_skills "
            "LIMIT 15"
        )
        with self.driver.session() as session:
            return [dict(r) for r in session.run(query, skill=skill_name, repo=repo_name)]

    def close(self):
        self.driver.close()
