from dataclasses import dataclass

from src.core.neo4j_client import Neo4jClient
from src.jd_match.matcher import MatchResult, match_requirement
from src.jd_match.parser import parse_requirements

SUMMARY_PROMPT = (
    "Summarize this job match analysis in 2-3 sentences. "
    "Match percentage: {pct:.0f}%. Requirements:\n{details}"
)


@dataclass
class MatchReport:
    requirements: list[MatchResult]
    match_percentage: float
    summary: str


class JDMatchAgent:
    def __init__(self, neo4j_client: Neo4jClient, chat_client, embed_client):
        self.neo4j = neo4j_client
        self.chat = chat_client
        self.embed = embed_client

    def match(self, jd_text: str) -> MatchReport:
        reqs = parse_requirements(jd_text, self.chat)
        results = [match_requirement(r, self.neo4j, self.embed) for r in reqs]
        matched = sum(1 for r in results if r.confidence in ("Strong", "Partial"))
        pct = (matched / len(results) * 100) if results else 0.0
        details = "\n".join(f"- {r.requirement}: {r.confidence}" for r in results)
        response = self.chat.chat([
            {"role": "user", "content": SUMMARY_PROMPT.format(pct=pct, details=details)},
        ])
        summary = response.choices[0].message.content.strip()
        return MatchReport(requirements=results, match_percentage=pct, summary=summary)
