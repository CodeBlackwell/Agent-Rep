from dataclasses import dataclass

from src.core.neo4j_client import Neo4jClient
from src.core.nim_client import NimClient


@dataclass
class MatchResult:
    requirement: str
    confidence: str  # "Strong", "Partial", "None"
    evidence: list[dict]


def match_requirement(requirement: str, neo4j_client: Neo4jClient, nim_client: NimClient) -> MatchResult:
    embedding = nim_client.embed([requirement])[0]
    results = neo4j_client.vector_search(embedding, top_k=5)
    evidence = [
        {
            "file_path": r["props"].get("file_path", ""),
            "start_line": r["props"].get("start_line", 0),
            "end_line": r["props"].get("end_line", 0),
            "content": r["props"].get("content", ""),
        }
        for r in results
    ]
    count = len(evidence)
    if count >= 3:
        confidence = "Strong"
    elif count >= 1:
        confidence = "Partial"
    else:
        confidence = "None"
    return MatchResult(requirement=requirement, confidence=confidence, evidence=evidence)
