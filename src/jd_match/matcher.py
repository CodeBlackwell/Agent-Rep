from dataclasses import dataclass

from src.core.neo4j_client import Neo4jClient

MIN_SCORE = 0.3


@dataclass
class MatchResult:
    requirement: str
    confidence: str  # "Strong", "Partial", "None"
    evidence: list[dict]


def _compute_confidence(evidence: list[dict]) -> str:
    count = len(evidence)
    if count == 0:
        return "None"
    # Boost for extensive/moderate proficiency
    proficiencies = [e.get("proficiency") for e in evidence if e.get("proficiency")]
    if any(p in ("extensive", "moderate") for p in proficiencies):
        scores = [e["score"] for e in evidence if "score" in e]
        avg = sum(scores) / len(scores) if scores else 0
        if avg >= 0.3:
            return "Strong"
    scores = [e["score"] for e in evidence if "score" in e]
    avg = sum(scores) / len(scores) if scores else 0
    if count >= 3 and avg >= 0.5:
        return "Strong"
    if avg >= 0.3:
        return "Partial"
    return "None"


def match_requirement(requirement: str, neo4j_client: Neo4jClient, embed_client) -> MatchResult:
    embedding = embed_client.embed([requirement], input_type="query")[0]
    results = neo4j_client.vector_search(embedding, top_k=5)
    evidence = []
    for r in results:
        if r["score"] < MIN_SCORE:
            continue
        entry = {
            "file_path": r["props"].get("file_path", ""),
            "start_line": r["props"].get("start_line", 0),
            "end_line": r["props"].get("end_line", 0),
            "content": r["props"].get("content", ""),
            "score": r["score"],
        }
        # Enrich with proficiency from skill nodes
        _enrich_with_proficiency(entry, r["props"].get("name", ""), neo4j_client)
        evidence.append(entry)
    return MatchResult(requirement=requirement, confidence=_compute_confidence(evidence), evidence=evidence)


def _enrich_with_proficiency(entry: dict, snippet_name: str, neo4j_client: Neo4jClient):
    with neo4j_client.driver.session() as session:
        result = session.run(
            "MATCH (cs:CodeSnippet {name: $name})-[:DEMONSTRATES]->(s:Skill) "
            "RETURN s.proficiency AS proficiency LIMIT 1",
            name=snippet_name,
        ).single()
        if result:
            entry["proficiency"] = result["proficiency"]
