from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion import load_documents


def test_chunks_have_required_metadata():
    chunks = load_documents()
    assert len(chunks) > 0
    for item in chunks[:50]:
        md = item["metadata"]
        assert md["document_name"]
        assert md["section"]
        assert isinstance(md["page_number"], int)
        assert md["chunk_id"] == item["id"]


def test_section_metadata_does_not_use_recommendation_sentences():
    chunks = load_documents()
    bad_prefixes = ("1.1.", "1.2.", "1.3.", "1.4.", "1.5.")

    for item in chunks:
        section = item["metadata"]["section"]
        assert not section.startswith(bad_prefixes), section
        assert len(section) <= 120


def test_patient_decision_aid_sections_are_real_headings():
    chunks = load_documents()
    patient_sections = {
        item["metadata"]["section"]
        for item in chunks
        if item["metadata"]["document_id"] == "HTN-PDA-2019"
    }

    assert "What are my options?" in patient_sections
    assert "What are some of the common side effects?" in patient_sections
    assert "Will I need blood tests?" in patient_sections
    assert "What else do I need to think about?" in patient_sections
    assert "10 may help make" not in patient_sections
    assert "1 or more people in" not in patient_sections
