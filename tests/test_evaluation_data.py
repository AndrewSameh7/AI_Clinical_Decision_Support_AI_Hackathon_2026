import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "data" / "clinical_test_questions.json"


def test_evaluation_dataset_is_valid_and_labeled():
    data = json.loads(TEST_DATA.read_text(encoding="utf-8"))

    assert isinstance(data, list)
    assert 15 <= len(data) <= 20

    for item in data:
        assert item["id"]
        assert item["question"]
        assert item["topic"]
        assert item["expected_sources"]
        assert item["expected_sections"]
