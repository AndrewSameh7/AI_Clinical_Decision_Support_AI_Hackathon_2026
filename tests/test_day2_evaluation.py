from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evaluation import precision_at_k, reciprocal_rank


def test_precision_at_k_and_reciprocal_rank():
    results = [
        {"metadata": {"document_id": "WRONG", "section": "Other"}},
        {"metadata": {"document_id": "HTN-NG136", "section": "1.2 Diagnosing hypertension"}},
        {"metadata": {"document_id": "HTN-NG136", "section": "1.2 Diagnosing hypertension"}},
    ]
    assert precision_at_k(results, ["HTN-NG136"], ["1.2 Diagnosing hypertension"], 3) == 2 / 3
    assert reciprocal_rank(results, ["HTN-NG136"], ["1.2 Diagnosing hypertension"]) == 0.5


def test_day2_dataset_has_15_to_20_questions():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "data" / "clinical_test_questions.json").read_text(encoding="utf-8"))
    assert 15 <= len(data) <= 20
