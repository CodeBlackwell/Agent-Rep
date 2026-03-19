import json
from typing import Generator

from src.core.neo4j_client import Neo4jClient
from src.core.nim_client import NimClient
from src.qa.tools import search_code, get_evidence, search_resume

SYSTEM_PROMPT = (
    "You are a QA agent for a software engineer's portfolio. "
    "Every claim must cite a specific file path and line range. "
    "If evidence is insufficient, say 'No evidence found for this claim.' "
    "Never infer skills not demonstrated in the provided materials."
)

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search code snippets by semantic similarity",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_evidence",
            "description": "Get code snippets demonstrating a specific skill",
            "parameters": {
                "type": "object",
                "properties": {"skill_name": {"type": "string", "description": "Skill name"}},
                "required": ["skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_resume",
            "description": "Search resume data including engineer info, roles, and companies",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
]

MAX_TOOL_CALLS = 3


def format_response(answer: str, evidence: list[dict]) -> str:
    lines = [answer, ""]
    if evidence:
        lines.append("Evidence:")
        for e in evidence:
            fp = e.get("file_path", "unknown")
            start = e.get("start_line", 0)
            end = e.get("end_line", 0)
            desc = e.get("content", "")[:100]
            lines.append(f"  [{fp}:L{start}-L{end}] {desc}")
    count = len(evidence)
    if count >= 3:
        confidence = "Strong"
    elif count >= 1:
        confidence = "Partial"
    else:
        confidence = "None"
    lines.append(f"\nConfidence: {confidence} ({count} code example{'s' if count != 1 else ''})")
    return "\n".join(lines)


class QAAgent:
    def __init__(self, neo4j_client: Neo4jClient, nim_client: NimClient):
        self.neo4j = neo4j_client
        self.nim = nim_client

    def _execute_tool(self, name: str, args: dict) -> str:
        dispatch = {
            "search_code": lambda: search_code(args["query"], self.neo4j, self.nim),
            "get_evidence": lambda: get_evidence(args["skill_name"], self.neo4j),
            "search_resume": lambda: search_resume(args["query"], self.neo4j, self.nim),
        }
        result = dispatch.get(name, lambda: {"error": f"Unknown tool: {name}"})()
        return json.dumps(result)

    def _collect_evidence(self, tool_result: str, evidence: list[dict]):
        try:
            parsed = json.loads(tool_result)
            if isinstance(parsed, list):
                evidence.extend(item for item in parsed if "file_path" in item)
        except (json.JSONDecodeError, TypeError):
            pass

    def _assistant_msg(self, choice) -> dict:
        msg = {"role": "assistant", "content": choice.message.content}
        if choice.message.tool_calls:
            msg["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in choice.message.tool_calls
            ]
        return msg

    def answer(self, question: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        all_evidence = []

        for _ in range(MAX_TOOL_CALLS):
            response = self.nim.chat(messages, tools=TOOL_DEFINITIONS)
            choice = response.choices[0]
            if not choice.message.tool_calls:
                return format_response(choice.message.content or "", all_evidence)
            messages.append(self._assistant_msg(choice))
            for tc in choice.message.tool_calls:
                result = self._execute_tool(tc.function.name, json.loads(tc.function.arguments))
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                self._collect_evidence(result, all_evidence)

        response = self.nim.chat(messages)
        return format_response(response.choices[0].message.content or "", all_evidence)

    def answer_stream(self, question: str) -> Generator[str, None, None]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        all_evidence = []

        for _ in range(MAX_TOOL_CALLS):
            response = self.nim.chat(messages, tools=TOOL_DEFINITIONS)
            choice = response.choices[0]
            if not choice.message.tool_calls:
                yield format_response(choice.message.content or "", all_evidence)
                return
            messages.append(self._assistant_msg(choice))
            for tc in choice.message.tool_calls:
                yield f"Searching for: {tc.function.name}..."
                result = self._execute_tool(tc.function.name, json.loads(tc.function.arguments))
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                self._collect_evidence(result, all_evidence)

        response = self.nim.chat(messages)
        yield format_response(response.choices[0].message.content or "", all_evidence)
