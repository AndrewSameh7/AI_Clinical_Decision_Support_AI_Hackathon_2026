from __future__ import annotations

from typing import Dict, Iterable, List, Optional


def is_relevant(result: Dict, expected_sources: Iterable[str], expected_sections: Iterable[str]) -> bool:
    md = result.get("metadata", {})
    source_ok = not expected_sources or md.get("document_id") in set(expected_sources)
    section_ok = not expected_sections or md.get("section") in set(expected_sections)
    return bool(source_ok and section_ok)


def precision_at_k(results: List[Dict], expected_sources: Iterable[str], expected_sections: Iterable[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    top = results[:k]
    if not top:
        return 0.0
    relevant = sum(is_relevant(r, expected_sources, expected_sections) for r in top)
    return relevant / len(top)


def reciprocal_rank(results: List[Dict], expected_sources: Iterable[str], expected_sections: Iterable[str]) -> float:
    for idx, result in enumerate(results, start=1):
        if is_relevant(result, expected_sources, expected_sections):
            return 1.0 / idx
    return 0.0


def evaluate_questions(question_rows: List[Dict], result_map: Dict[str, List[Dict]], ks=(3, 5)) -> Dict:
    rows = []
    for q in question_rows:
        results = result_map.get(q["id"], [])
        p = {f"precision_at_{k}": round(precision_at_k(results, q.get("expected_sources", []), q.get("expected_sections", []), k), 4) for k in ks}
        rows.append({
            "question_id": q["id"],
            "question": q["question"],
            "topic": q.get("topic"),
            "precision": p,
            "reciprocal_rank": round(reciprocal_rank(results, q.get("expected_sources", []), q.get("expected_sections", [])), 4),
            "results": results,
        })

    summary = {}
    for k in ks:
        values = [r["precision"][f"precision_at_{k}"] for r in rows]
        summary[f"mean_precision_at_{k}"] = round(sum(values) / len(values), 4) if values else 0.0
    rr = [r["reciprocal_rank"] for r in rows]
    summary["mean_reciprocal_rank"] = round(sum(rr) / len(rr), 4) if rr else 0.0
    return {"summary": summary, "questions": rows}


def compare_configs(named_reports: Dict[str, Dict]) -> List[Dict]:
    comparison = []
    for name, report in named_reports.items():
        comparison.append({"configuration": name, **report.get("summary", {})})
    return comparison
