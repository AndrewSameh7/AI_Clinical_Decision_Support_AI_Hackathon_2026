import hashlib
import re
from pathlib import Path
from typing import Dict, List, Tuple

from pypdf import PdfReader

from src.config import CHUNK_SIZE, CHUNK_OVERLAP, DOCUMENTS


# IMPORTANT:
# Day-1 section metadata is used later for evidence panels and citations.
# The previous generic heading regex could mistake numbered recommendations
# (for example 1.2.3 ...) and table fragments for section headings.
# We therefore use document-aware, exact heading sets for the two approved PDFs.
NG136_SECTION_HEADINGS = {
    "Overview",
    "Who is it for?",
    "Recommendations",
    "1.1 Measuring blood pressure",
    "1.2 Diagnosing hypertension",
    "1.3 Assessing cardiovascular risk and target organ damage",
    "1.4 Treating and monitoring hypertension",
    "1.5 Identifying who to refer for same-day specialist review",
    "Terms used in this guideline",
    "Recommendations for research",
    "Key recommendations for research",
    "Other recommendations for research",
    "Rationale and impact",
    "Diagnosing hypertension",
    "Relaxation therapies",
    "Starting antihypertensive drug treatment",
    "Monitoring treatment and blood pressure targets",
    "Choosing antihypertensive drug treatment for people with cardiovascular disease",
    "Step 1 treatment",
    "Step 2 and 3 treatment",
    "Step 4 treatment",
    "Identifying who to refer for same-day specialist review",
    "Context",
    "Finding more information and committee details",
    "Update information",
}

PATIENT_AID_SECTION_HEADINGS = {
    "I’ve been diagnosed with high blood pressure. What does this mean for me?",
    "I've been diagnosed with high blood pressure. What does this mean for me?",
    "What are my options?",
    "What are the types of medicine and what are they called?",
    "What are some of the common side effects?",
    "What are some of the common side effects? (Continued.)",
    "Will I need blood tests?",
    "What else do I need to think about?",
    "Your chance of getting side effects",
}


def _normalize_heading(text: str) -> str:
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _heading_aliases(document_id: str) -> Dict[str, str]:
    if document_id == "HTN-NG136":
        return {_normalize_heading(x): x for x in NG136_SECTION_HEADINGS}
    if document_id == "HTN-PDA-2019":
        return {_normalize_heading(x): x for x in PATIENT_AID_SECTION_HEADINGS}
    return {}


def detect_section(line: str, document_id: str) -> str | None:
    normalized = _normalize_heading(line)
    aliases = _heading_aliases(document_id)
    return aliases.get(normalized)


def detect_section_prefix(line: str, document_id: str) -> tuple[str | None, str]:
    normalized = _normalize_heading(line)
    aliases = _heading_aliases(document_id)

    exact = aliases.get(normalized)
    if exact:
        return exact, ""

    # Some PDF pages place the heading and the first sentence on the same
    # extracted line (for example: "Will I need blood tests? You’ll need...").
    # Accept only an exact approved heading followed by whitespace.
    for normalized_heading, canonical_heading in aliases.items():
        if normalized.startswith(normalized_heading + " "):
            remainder = normalized[len(normalized_heading):].strip()
            return canonical_heading, remainder

    return None, line


def clean_text(text: str, preserve_lines: bool = False) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if preserve_lines:
        return text.strip()

    return re.sub(r"(?<![.!?:;])\n(?!\n)", " ", text).strip()


def sliding_chunks(
    text: str,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    if not text:
        return []
    if overlap >= size:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + size, len(text))

        if end < len(text):
            boundary = max(
                text.rfind(". ", start, end),
                text.rfind(".\n", start, end),
                text.rfind(" ", start, end),
            )
            if boundary > start + int(size * 0.60):
                end = boundary + (
                    2 if text[boundary:boundary + 2] in [". ", ".\n"] else 1
                )

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return chunks


def make_chunk_id(
    document_id: str,
    page: int,
    section: str,
    chunk_index: int,
    text: str,
) -> str:
    safe_sec = re.sub(r"[^A-Za-z0-9]", "", section)[:8].upper() or "GEN"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"{document_id}-P{page:03d}-S_{safe_sec}-C{chunk_index:03d}-{digest}"


def validate_metadata(metadata: Dict) -> None:
    required = [
        "document_id",
        "document_name",
        "source",
        "source_url",
        "version",
        "section",
        "page_number",
        "chunk_id",
    ]

    missing = [key for key in required if not metadata.get(key)]
    if missing:
        raise ValueError(f"Chunk metadata missing required fields: {missing}")

    if not isinstance(metadata["page_number"], int):
        raise TypeError("page_number must be an integer")


def load_documents(chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> List[Dict]:
    all_chunks = []

    for doc_cfg in DOCUMENTS:
        path: Path = doc_cfg["path"]

        if not path.exists():
            raise FileNotFoundError(f"Missing PDF: {path}")

        reader = PdfReader(str(path))
        current_section = "Overview"
        doc_chunk_counter = 0

        for page_idx, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            line_preserved = clean_text(raw, preserve_lines=True)

            if not line_preserved:
                continue

            lines = [x.strip() for x in line_preserved.splitlines() if x.strip()]
            page_blocks: List[Tuple[str, str]] = []
            buf = []
            i = 0

            while i < len(lines):
                heading, remainder = detect_section_prefix(lines[i], doc_cfg["document_id"])
                consumed = 1

                # PDF extraction may wrap a real heading over 2–3 lines.
                # Join only when the combined text exactly matches one of the
                # approved document-specific headings. This avoids false
                # positives on recommendation/table fragments.
                if not heading:
                    for width in (2, 3):
                        if i + width <= len(lines):
                            candidate = " ".join(lines[i:i + width])
                            heading = detect_section(candidate, doc_cfg["document_id"])
                            if heading:
                                remainder = ""
                                consumed = width
                                break

                if heading:
                    if buf:
                        page_blocks.append((current_section, " ".join(buf)))
                        buf = []
                    current_section = heading
                    if remainder:
                        buf.append(remainder)
                else:
                    buf.append(lines[i])

                i += consumed

            if buf:
                page_blocks.append((current_section, " ".join(buf)))

            for sec_name, block_text in page_blocks:
                clean_block = clean_text(block_text)

                for chunk_text in sliding_chunks(clean_block, size=chunk_size, overlap=chunk_overlap):
                    doc_chunk_counter += 1

                    chunk_id = make_chunk_id(
                        doc_cfg["document_id"],
                        page_idx,
                        sec_name,
                        doc_chunk_counter,
                        chunk_text,
                    )

                    metadata = {
                        "document_id": doc_cfg["document_id"],
                        "document_name": doc_cfg["title"],
                        "source": doc_cfg["source"],
                        "source_url": doc_cfg["url"],
                        "publisher": doc_cfg["publisher"],
                        "publication_date": doc_cfg["publication_date"],
                        "last_updated": doc_cfg["last_updated"],
                        "version": doc_cfg["version"],
                        "section": sec_name,
                        "page_number": page_idx,
                        "chunk_id": chunk_id,
                    }

                    validate_metadata(metadata)

                    all_chunks.append({
                        "id": chunk_id,
                        "text": chunk_text,
                        "metadata": metadata,
                    })

    return all_chunks
