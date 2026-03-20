from src.ingestion.code_parser import CodeChunk

SKILL_PROMPT = (
    "List the specific technical skills demonstrated in this code. "
    "Return only skill names, one per line. "
    "Be specific (e.g. 'Kafka consumer groups' not just 'messaging')."
)


def extract_skills(chunk: CodeChunk, chat_client) -> list[str]:
    response = chat_client.chat([
        {"role": "system", "content": SKILL_PROMPT},
        {"role": "user", "content": chunk.content},
    ])
    raw = response.choices[0].message.content.strip()
    return [line.strip().lstrip("- ") for line in raw.splitlines() if line.strip()]


def store_skills(chunk_name: str, file_path: str, repo_name: str, skills: list[str], session):
    for skill in skills:
        session.run(
            "MERGE (s:Skill {name: $skill}) "
            "WITH s "
            "MATCH (cs:CodeSnippet {name: $chunk, file_path: $fp}) "
            "MERGE (cs)-[:DEMONSTRATES]->(s)",
            skill=skill, chunk=chunk_name, fp=file_path,
        )
        session.run(
            "MERGE (t:Technology {name: $skill}) "
            "WITH t "
            "MATCH (r:Repository {name: $repo}) "
            "MERGE (r)-[:USES]->(t)",
            skill=skill, repo=repo_name,
        )
