import json
import re
from pathlib import Path

RESUME_PROMPT = (
    "Extract structured data from this resume. Return ONLY valid JSON with this schema:\n"
    '{"name": "string", "roles": [{"title": "string", "company": "string", "dates": "string"}], '
    '"skills": ["string"]}\n'
    "Be thorough with skills and roles."
)


def _read_file(file_path: Path) -> str:
    if file_path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return file_path.read_text(encoding="utf-8", errors="replace")


def parse_resume(file_path, neo4j_client, chat_client):
    path = Path(file_path)
    text = _read_file(path)

    response = chat_client.chat([
        {"role": "system", "content": RESUME_PROMPT},
        {"role": "user", "content": text},
    ])
    raw = response.choices[0].message.content.strip()

    # Strip <think> blocks from reasoning models
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Extract JSON from possible markdown code blocks
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    # Find JSON object boundaries if extra text surrounds it
    start = raw.find("{")
    if start >= 0:
        raw = raw[start:]
    data = None
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(raw)
    except json.JSONDecodeError:
        end = raw.rfind("}") + 1
        if end > 0:
            data = json.loads(raw[:end])
    if data is None:
        raise ValueError(f"Could not parse JSON from resume response: {raw[:200]}")

    with neo4j_client.driver.session() as session:
        name = data["name"]
        session.run("MERGE (e:Engineer {name: $name})", name=name)

        for role in data.get("roles", []):
            session.run(
                "MATCH (e:Engineer {name: $name}) "
                "MERGE (c:Company {name: $company}) "
                "MERGE (r:Role {title: $title, company: $company}) "
                "MERGE (e)-[:HELD]->(r) "
                "MERGE (r)-[:AT]->(c) "
                "SET r.dates = $dates",
                name=name, title=role["title"],
                company=role["company"], dates=role.get("dates", ""),
            )

        for skill in data.get("skills", []):
            session.run(
                "MATCH (e:Engineer {name: $name}) "
                "MERGE (s:Skill {name: $skill}) "
                "MERGE (e)-[:CLAIMS]->(s)",
                name=name, skill=skill,
            )

    return name
