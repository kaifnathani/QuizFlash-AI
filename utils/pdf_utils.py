from io import BytesIO
from typing import List
from PyPDF2 import PdfReader


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes using PyPDF2."""
    output_lines: List[str] = []
    try:
        reader = PdfReader(BytesIO(file_bytes))
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
                output_lines.append(text)
            except Exception:
                continue
    except Exception:
        return ""

    return "\n".join([ln for ln in output_lines if ln])
