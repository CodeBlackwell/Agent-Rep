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


def _walk_nodes(node, types):
    """Recursively yield all nodes matching the given types."""
    if node.type in types:
        yield node
    for child in node.children:
        yield from _walk_nodes(child, types)


def _parse_with_treesitter(source: bytes, lang: Language, suffix: str, file_path: str) -> list[CodeChunk]:
    parser = Parser(lang)
    tree = parser.parse(source)
    node_types = EXTRACTABLE_TYPES[suffix]
    chunks = []
    for node in _walk_nodes(tree.root_node, node_types):
        chunks.append(CodeChunk(
            content=node.text.decode(),
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            language=suffix.lstrip("."),
            name=_extract_name(node),
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


def _parse_notebook(file_path: str | Path) -> list[CodeChunk]:
    """Extract code cells from Jupyter notebooks as parseable Python chunks."""
    import json
    path = Path(file_path)
    try:
        nb = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError):
        return []
    cells = nb.get("cells", [])

    # Collect code cells, track line offsets
    code_cells = []
    for i, cell in enumerate(cells):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue
        code_cells.append((i, source))

    if not code_cells:
        return []

    # Combine all code cells into one Python source for tree-sitter parsing
    combined_lines = []
    cell_offsets = []  # (start_line_in_combined, cell_index, cell_source)
    for cell_idx, source in code_cells:
        start = len(combined_lines) + 1
        lines = source.split("\n")
        combined_lines.extend(lines)
        cell_offsets.append((start, cell_idx, source, len(lines)))

    combined = "\n".join(combined_lines)
    py_path = str(file_path).replace(".ipynb", ".py")

    # Parse with tree-sitter to extract functions/classes
    chunks = _parse_with_treesitter(
        combined.encode(), LANGUAGES[".py"], ".py", py_path,
    )

    # If tree-sitter found nothing (all top-level code), fall back to per-cell chunks
    if not chunks:
        for start, cell_idx, source, line_count in cell_offsets:
            if len(source.strip()) < 20:
                continue
            chunks.append(CodeChunk(
                content=source,
                file_path=py_path,
                start_line=start,
                end_line=start + line_count - 1,
                language="py",
                name=f"cell_{cell_idx}",
            ))

    return chunks


def parse_file(file_path: str | Path) -> list[CodeChunk]:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".ipynb":
        return _parse_notebook(path)

    text = path.read_text(encoding="utf-8", errors="replace")

    if suffix in LANGUAGES:
        return _parse_with_treesitter(text.encode(), LANGUAGES[suffix], suffix, str(path))
    return _fallback_parse(text, str(path), suffix)
