import json

from src.core.nim_client import NimClient

EXTRACT_PROMPT = (
    "Extract individual technical requirements from this job description. "
    "Return ONLY a JSON array of strings. Each string should be a specific "
    "technical skill or experience requirement. Exclude generic traits like "
    "'team player' or 'good communication'. Examples of good extractions: "
    "'Python 3+ years', 'Kubernetes deployment', 'REST API design'.\n\n"
    "Job Description:\n{jd_text}"
)


def parse_requirements(jd_text: str, nim_client: NimClient) -> list[str]:
    response = nim_client.chat([
        {"role": "user", "content": EXTRACT_PROMPT.format(jd_text=jd_text)},
    ])
    raw = response.choices[0].message.content.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    requirements = json.loads(raw)
    return list(dict.fromkeys(requirements))
