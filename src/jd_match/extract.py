import io
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".md", ".txt", ".text"}


def extract_text(filename: str, content: bytes) -> str:
    """Extract plain text from uploaded file bytes."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif ext == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    elif ext in (".md", ".txt", ".text", ""):
        return content.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file type: {ext}. Use PDF, DOCX, MD, or TXT.")
