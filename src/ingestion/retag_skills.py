"""Re-tag all existing CodeSnippets with keyword-based skill detection.
Run after ingestion to link skills without re-embedding."""

from src.config.settings import Settings
from src.core import Neo4jClient, logger
from src.ingestion.skill_keywords import SKILL_MAP


def _detect_skills(content: str, file_path: str) -> set[str]:
    text = (content + " " + file_path).lower()
    found = set()
    for skill_name, patterns in SKILL_MAP.items():
        for pattern in patterns:
            if pattern.lower() in text:
                found.add(skill_name)
                break
    return found


def retag():
    settings = Settings.load()
    neo4j = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)

    with neo4j.driver.session() as s:
        # Clear old skill edges
        s.run("MATCH ()-[r:DEMONSTRATES]->() DELETE r")
        s.run("MATCH ()-[r:USES_SKILL]->() DELETE r")
        s.run("MATCH ()-[r:USES]->() DELETE r")
        s.run("MATCH (n:Skill) WHERE NOT (n)<-[:CLAIMS]-(:Engineer) DETACH DELETE n")
        s.run("MATCH (n:Technology) DETACH DELETE n")
        logger.info("retag.cleared", detail="old skill/tech data")

        # Get all snippets with their repo
        snippets = s.run(
            "MATCH (r:Repository)-[:CONTAINS]->(:File)-[:CONTAINS]->(cs:CodeSnippet) "
            "RETURN r.name AS repo, cs.name AS name, cs.file_path AS fp, cs.content AS content"
        ).data()
        logger.info("retag.processing", snippet_count=len(snippets))

        repo_skills: dict[str, set[str]] = {}
        demo_count = 0
        for row in snippets:
            skills = _detect_skills(row["content"], row["fp"])
            repo = row["repo"]
            if repo not in repo_skills:
                repo_skills[repo] = set()
            repo_skills[repo].update(skills)

            for skill in skills:
                s.run(
                    "MERGE (sk:Skill {name: $skill}) WITH sk "
                    "MATCH (cs:CodeSnippet {name: $name, file_path: $fp}) "
                    "MERGE (cs)-[:DEMONSTRATES]->(sk)",
                    skill=skill, name=row["name"], fp=row["fp"],
                )
                demo_count += 1

        # Link skills to repos
        for repo, skills in repo_skills.items():
            for skill in skills:
                s.run(
                    "MATCH (r:Repository {name: $repo}) "
                    "MERGE (sk:Skill {name: $skill}) "
                    "MERGE (r)-[:USES_SKILL]->(sk)",
                    repo=repo, skill=skill,
                )
                s.run(
                    "MATCH (r:Repository {name: $repo}) "
                    "MERGE (t:Technology {name: $skill}) "
                    "MERGE (r)-[:USES]->(t)",
                    repo=repo, skill=skill,
                )
            logger.info("retag.repo_skills", repo=repo, skill_count=len(skills))

        # Link engineer to repos
        eng = s.run("MATCH (e:Engineer) RETURN e.name AS name LIMIT 1").single()
        if eng:
            for repo in repo_skills:
                s.run(
                    "MATCH (e:Engineer {name: $eng}), (r:Repository {name: $repo}) "
                    "MERGE (e)-[:OWNS]->(r)",
                    eng=eng["name"], repo=repo,
                )

        logger.info("retag.done", demonstrates_edges=demo_count,
                     uses_skill_edges=sum(len(v) for v in repo_skills.values()))

    neo4j.close()


if __name__ == "__main__":
    retag()
