from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Parser

import tree_sitter_python as tsp
import tree_sitter_javascript as tsj
import tree_sitter_typescript as tst


@dataclass
class CodeChunk:
    content: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    name: str


LANGUAGES = {
    ".py": Language(tsp.language()),
    ".js": Language(tsj.language()),
    ".ts": Language(tst.language_typescript()),
    ".tsx": Language(tst.language_tsx()),
}

EXTRACTABLE_TYPES = {
    ".py": ("function_definition", "class_definition"),
    ".js": ("function_declaration", "class_declaration"),
    ".ts": ("function_declaration", "class_declaration"),
    ".tsx": ("function_declaration", "class_declaration"),
}


def _extract_name(node) -> str:
    name_node = node.child_by_field_name("name")
    return name_node.text.decode() if name_node else "<anonymous>"


def _parse_with_treesitter(source: bytes, lang: Language, suffix: str, file_path: str) -> list[CodeChunk]:
    parser = Parser(lang)
    tree = parser.parse(source)
    node_types = EXTRACTABLE_TYPES[suffix]
    chunks = []
    for child in tree.root_node.children:
        if child.type in node_types:
            chunks.append(CodeChunk(
                content=child.text.decode(),
                file_path=file_path,
                start_line=child.start_point[0] + 1,
                end_line=child.end_point[0] + 1,
                language=suffix.lstrip("."),
                name=_extract_name(child),
            ))
    return chunks


def _fallback_parse(text: str, file_path: str, suffix: str) -> list[CodeChunk]:
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    chunks = []
    line = 1
    for block in blocks:
        line_count = block.count("\n") + 1
        chunks.append(CodeChunk(
            content=block,
            file_path=file_path,
            start_line=line,
            end_line=line + line_count - 1,
            language=suffix.lstrip(".") or "unknown",
            name=f"block_{line}",
        ))
        line += line_count + 1
    return chunks


def parse_file(file_path: str | Path) -> list[CodeChunk]:
    path = Path(file_path)
    text = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()

    if suffix in LANGUAGES:
        return _parse_with_treesitter(text.encode(), LANGUAGES[suffix], suffix, str(path))
    return _fallback_parse(text, str(path), suffix)
