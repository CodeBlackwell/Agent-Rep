from src.core.neo4j_client import Neo4jClient
from src.ingestion.skill_taxonomy import SKILL_HIERARCHY

MIN_SCORE = 0.3


def search_code(query: str, neo4j_client: Neo4jClient, embed_client) -> list[dict]:
    embedding = embed_client.embed([query], input_type="query")[0]
    results = neo4j_client.vector_search(embedding, top_k=10)
    return [
        {
            "file_path": r["props"].get("file_path", ""),
            "start_line": r["props"].get("start_line", 0),
            "end_line": r["props"].get("end_line", 0),
            "content": r["props"].get("content", ""),
            "context": r["props"].get("context", ""),
            "score": r["score"],
            "repo": r.get("repo"),
            "skills": r.get("skills", []),
        }
        for r in results
        if r["score"] >= MIN_SCORE
    ]


def get_evidence(skill_name: str, neo4j_client: Neo4jClient) -> list[dict]:
    results = neo4j_client.get_skill_evidence(skill_name)
    return [
        {
            "file_path": r.get("file_path", ""),
            "start_line": r.get("start_line", 0),
            "end_line": r.get("end_line", 0),
            "content": r.get("content", ""),
            "context": r.get("context", ""),
            "first_seen": r.get("first_seen"),
            "last_seen": r.get("last_seen"),
            "proficiency": r.get("proficiency"),
            "repo": r.get("repo"),
            "skill_name": skill_name,
        }
        for r in results
    ]


def find_gaps(skills_csv: str, neo4j_client: Neo4jClient) -> list[dict]:
    results = []
    for skill in (s.strip() for s in skills_csv.split(",") if s.strip()):
        info = neo4j_client.get_skill_with_hierarchy(skill)
        if info and info.get("snippet_count", 0) > 0:
            results.append({
                "skill": skill, "status": "demonstrated",
                "code_examples": info["snippet_count"],
                "proficiency": info.get("proficiency", "none"),
                "domain": info.get("domain"), "category": info.get("category"),
            })
            continue

        # Check category-level for related skills
        hierarchy = SKILL_HIERARCHY.get(skill)
        if hierarchy:
            domain, category = hierarchy
            related = _find_related_in_category(category, neo4j_client)
            if related:
                results.append({
                    "skill": skill, "status": "not_found_but_related",
                    "code_examples": 0, "domain": domain, "category": category,
                    "related_demonstrated": related,
                })
                continue

        with neo4j_client.driver.session() as session:
            claim = session.run(
                "MATCH (:Engineer)-[:CLAIMS]->(:Skill {name: $name}) RETURN count(*) AS c",
                name=skill,
            ).single()["c"]
        status = "claimed_only" if claim > 0 else "not_found"
        results.append({"skill": skill, "status": status, "code_examples": 0})
    return results


def _find_related_in_category(category: str, neo4j_client: Neo4jClient) -> list[str]:
    with neo4j_client.driver.session() as session:
        result = session.run(
            "MATCH (:Category {name: $cat})-[:CONTAINS]->(s:Skill) "
            "WHERE s.proficiency IS NOT NULL AND s.proficiency <> 'none' "
            "RETURN s.name AS name",
            cat=category,
        )
        return [r["name"] for r in result]


def get_repo_overview(repo_name: str, neo4j_client: Neo4jClient) -> dict:
    result = neo4j_client.get_repo_overview(repo_name)
    if not result:
        return {"error": f"Repository '{repo_name}' not found"}
    return {
        "name": result["name"],
        "file_count": result["file_count"],
        "sample_files": result["sample_files"],
        "top_skills": result["top_skills"],
    }


def get_connected_evidence(skill_name: str, repo_name: str, neo4j_client: Neo4jClient) -> list[dict]:
    snippets = neo4j_client.get_connected_snippets(skill_name, repo_name)
    return [
        {
            "file_path": s["file_path"],
            "snippet_name": s.get("snippet_name", ""),
            "start_line": s["start_line"],
            "end_line": s["end_line"],
            "content": s["content"],
            "context": s.get("context", ""),
            "proficiency": s["proficiency"],
            "repo": repo_name,
            "related_skills": s.get("related_skills", []),
            "skill_name": skill_name,
        }
        for s in snippets
    ]


def search_resume(query: str, neo4j_client: Neo4jClient) -> list[dict]:
    cypher = (
        "MATCH (n) WHERE n:Engineer "
        "WITH n, [key IN keys(n) WHERE key <> 'embedding' | toString(n[key])] AS vals "
        "WHERE ANY(v IN vals WHERE toLower(v) CONTAINS toLower($term)) "
        "RETURN labels(n) AS labels, properties(n) AS props"
    )
    with neo4j_client.driver.session() as session:
        result = session.run(cypher, term=query)
        return [
            {"labels": r["labels"], **{k: v for k, v in r["props"].items() if k != "embedding"}}
            for r in result
        ]
