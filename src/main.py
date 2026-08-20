from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

from src.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CLINICAL_SCOPE,
    CLINICAL_TEST_QUESTIONS_PATH,
    DAY2_CHUNK_CONFIGS,
    EMBEDDING_MODEL,
    OUTPUT_DIR,
    TOP_K,
    TOP_K_OPTIONS,
    DAY4_EVAL_SET_PATH,
)
from src.evaluation import evaluate_questions, is_relevant, compare_configs
from src.ingestion import load_documents
from src.llm import generate_grounded_answer
from src.vector_store import build_vector_store, retrieve, index_ready
from src.day4_safety import classify_query, citation_metrics


def load_test_questions() -> List[Dict]:
    try:
        data = json.loads(CLINICAL_TEST_QUESTIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid evaluation JSON at {CLINICAL_TEST_QUESTIONS_PATH}: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise ValueError("Clinical evaluation set must be a non-empty JSON list.")
    for item in data:
        if not item.get("id") or not item.get("question"):
            raise ValueError("Each evaluation item requires id and question fields.")
    return data


def index(chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP, config_name: str = "B_850_150"):
    chunks = load_documents(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    print(f"Parsed + chunked: {len(chunks)} chunks")
    store = build_vector_store(chunks, config_name=config_name)
    print(f"Indexed: {store.name}")
    print(f"scope={CLINICAL_SCOPE}")
    print(f"chunk_size={chunk_size} characters, overlap={chunk_overlap} characters")
    print(f"embedding={EMBEDDING_MODEL}")
    return len(chunks)


def index_day2():
    for name, cfg in DAY2_CHUNK_CONFIGS.items():
        print(f"\n=== Building Day-2 configuration {name} ===")
        index(cfg["chunk_size"], cfg["chunk_overlap"], name)
    print("\nDay-2 indexes are ready. No generation prompt tuning is performed here.")


def search(query: str, top_k: int = TOP_K, strategy: str = "semantic", config_name: str = "B_850_150", rerank: bool = False):
    rows = retrieve(query, top_k=top_k, strategy=strategy, config_name=config_name, rerank=rerank)
    print(f"\nQuestion: {query}")
    print(f"Configuration: {config_name} | Strategy: {strategy} | K={top_k} | rerank={rerank}\n")
    for r in rows:
        m = r["metadata"]
        print(f"Rank {r['rank']} | Page {m['page_number']} | Score {r['similarity']:.4f} | {m['chunk_id']}")
        print(f"Document: {m['document_name']}")
        print(f"Section: {m['section']}")
        print(f"Method: {r.get('retrieval_method')}")
        print(f"Text: {r['text'][:700]}\n")
    return rows


def _load_manual_labels() -> Dict:
    path = OUTPUT_DIR / "day2_manual_labels.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def review_labels():
    questions = load_test_questions()
    OUTPUT_DIR.mkdir(exist_ok=True)
    labels = _load_manual_labels()
    print("Day-2 relevance review. Each unique retrieved chunk is shown once per question.")
    print("The review pool combines both chunk configurations and semantic/keyword/hybrid retrieval.")
    print("Use y = relevant, n = not relevant, s = skip. This is the authoritative human-labeling step.\n")

    for q in questions:
        pool = {}
        for config_name in DAY2_CHUNK_CONFIGS:
            for strategy in ("semantic", "keyword", "hybrid"):
                rows = retrieve(q["question"], top_k=5, strategy=strategy, config_name=config_name)
                for row in rows:
                    pool[row["metadata"]["chunk_id"]] = row

        labels[q["id"]] = {"question": q["question"], "relevant": {}}
        print("\n" + "=" * 88)
        print(f"{q['id']}: {q['question']} | {len(pool)} unique chunks to review")
        for row in pool.values():
            m = row["metadata"]
            print("-" * 88)
            print(f"{m['chunk_id']} | {m['document_name']} | p.{m['page_number']} | {m['section']}")
            print(row["text"][:900])
            while True:
                answer = input("Relevant? [y/n/s=skip]: ").strip().lower()
                if answer in {"y", "n", "s"}:
                    break
            if answer != "s":
                labels[q["id"]]["relevant"][m["chunk_id"]] = answer == "y"

    path = OUTPUT_DIR / "day2_manual_labels.json"
    path.write_text(json.dumps(labels, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved manual labels to {path}")


def _apply_labels(question: Dict, rows: List[Dict], labels: Dict) -> List[Dict]:
    qlabel = labels.get(question["id"], {})
    relevant = qlabel.get("relevant", {})
    if not relevant:
        for row in rows:
            row["relevant"] = is_relevant(row, question.get("expected_sources", []), question.get("expected_sections", []))
            row["label_source"] = "metadata_proxy"
        return rows
    for row in rows:
        cid = row["metadata"]["chunk_id"]
        row["relevant"] = bool(relevant.get(cid, False))
        row["label_source"] = "human"
    return rows


def _evaluate_with_labels(questions: List[Dict], config_name: str, strategy: str, max_k: int = 10):
    labels = _load_manual_labels()
    report_rows = []
    for q in questions:
        rows = retrieve(q["question"], top_k=max_k, strategy=strategy, config_name=config_name)
        rows = _apply_labels(q, rows, labels)
        per_k = {}
        for k in TOP_K_OPTIONS:
            top = rows[:k]
            per_k[f"precision_at_{k}"] = round(sum(bool(x["relevant"]) for x in top) / len(top), 4) if top else 0.0
        first = next((i + 1 for i, x in enumerate(rows) if x["relevant"]), None)
        rr = round(1 / first, 4) if first else 0.0
        report_rows.append({"question_id": q["id"], "question": q["question"], "topic": q.get("topic"), "precision": per_k, "reciprocal_rank": rr, "label_source": sorted({x["label_source"] for x in rows}), "results": rows})
    summary = {}
    for k in TOP_K_OPTIONS:
        key = f"precision_at_{k}"
        vals = [r["precision"][key] for r in report_rows]
        summary[f"mean_{key}"] = round(sum(vals) / len(vals), 4) if vals else 0.0
    rr = [r["reciprocal_rank"] for r in report_rows]
    summary["mean_reciprocal_rank"] = round(sum(rr) / len(rr), 4) if rr else 0.0
    summary["label_mode"] = "human" if any("human" in r["label_source"] for r in report_rows) else "metadata_proxy"
    return {"summary": summary, "questions": report_rows}


def evaluate_day2():
    questions = load_test_questions()
    OUTPUT_DIR.mkdir(exist_ok=True)
    config_reports = {}
    strategy_reports = {}

    # Both official chunk experiments.
    for config_name in DAY2_CHUNK_CONFIGS:
        if not index_ready(config_name):
            raise RuntimeError(f"Missing Day-2 index {config_name}. Run `python -m src.main index-day2` first.")
        config_reports[config_name] = _evaluate_with_labels(questions, config_name, "semantic", max_k=10)

    # Compare retrieval strategies on the chosen Day-2 baseline candidate.
    for strategy in ("semantic", "keyword", "hybrid"):
        strategy_reports[strategy] = _evaluate_with_labels(questions, "B_850_150", strategy, max_k=10)

    comparison = compare_configs(config_reports)
    strategy_comparison = compare_configs(strategy_reports)
    best_config = max(comparison, key=lambda x: x.get("mean_precision_at_5", 0.0))
    best_strategy = max(strategy_comparison, key=lambda x: x.get("mean_precision_at_5", 0.0))

    payload = {
        "day": 2,
        "scope": CLINICAL_SCOPE,
        "evaluation_questions": len(questions),
        "chunk_experiments": config_reports,
        "chunk_comparison": comparison,
        "strategy_experiments": strategy_reports,
        "strategy_comparison": strategy_comparison,
        "provisional_choice_by_precision_at_5": {
            "chunk_configuration": best_config["configuration"],
            "strategy": best_strategy["configuration"],
        },
        "methodology": "One variable at a time. Same labeled question set across configurations. Precision@3 and Precision@5 are primary Day-2 metrics.",
    }
    path = OUTPUT_DIR / "day2_retrieval_report.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved Day-2 report: {path}")
    print("\nChunk comparison:")
    for row in comparison:
        print(row)
    print("\nStrategy comparison on B_850_150:")
    for row in strategy_comparison:
        print(row)
    print(f"\nProvisional best by Precision@5: {best_config['configuration']} + {best_strategy['configuration']}")
    if best_config.get("mean_precision_at_5", 0) == 0 and best_strategy.get("mean_precision_at_5", 0) == 0:
        print("WARNING: review labels are likely incomplete; run `python -m src.main review` before treating metrics as final.")



def load_day4_questions() -> List[Dict]:
    data = json.loads(DAY4_EVAL_SET_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) < 20:
        raise ValueError("Day-4 evaluation set must contain at least 20 cases.")
    return data


def evaluate_day4():
    questions = load_day4_questions()
    retrieval_cases = [q for q in questions if q.get("expected_sources")]
    safety_cases = [q for q in questions if not q.get("expected_sources")]
    retrieval_hits = []
    for q in retrieval_cases:
        rows = retrieve(q["question"], top_k=5, strategy="hybrid", config_name="B_850_150", rerank=True)
        expected_sources = set(q.get("expected_sources", []))
        expected_sections = set(q.get("expected_sections", []))
        relevant = [r for r in rows if r.get("metadata", {}).get("document_id") in expected_sources and (not expected_sections or r.get("metadata", {}).get("section") in expected_sections)]
        retrieval_hits.append({"id": q["id"], "precision_at_5": round(len(relevant) / max(1, len(rows)), 4), "hit": bool(relevant)})
    safety_results = []
    for q in safety_cases:
        predicted = classify_query(q["question"])["action"]
        expected = q.get("expected_behavior", "")
        if expected in {"clarify"}: expected_action = "clarify"
        elif expected in {"answer"}: expected_action = "retrieve"
        else: expected_action = "refuse"
        safety_results.append({"id": q["id"], "expected": expected_action, "predicted": predicted, "correct": predicted == expected_action})
    report = {
        "day": 4,
        "scope": CLINICAL_SCOPE,
        "evaluation_set_size": len(questions),
        "retrieval_metric": {
            "name": "Precision@5 proxy",
            "mean": round(sum(x["precision_at_5"] for x in retrieval_hits) / max(1, len(retrieval_hits)), 4),
            "hit_rate": round(sum(x["hit"] for x in retrieval_hits) / max(1, len(retrieval_hits)), 4),
        },
        "safety_metric": {
            "name": "Input-risk classification accuracy",
            "accuracy": round(sum(x["correct"] for x in safety_results) / max(1, len(safety_results)), 4),
        },
        "retrieval_cases": retrieval_hits,
        "safety_cases": safety_results,
        "citation_faithfulness_metric": "Run after human/LLM answer review using outputs/day4_answer_review.json; citation validity, coverage, faithfulness and unsupported-claim rate are calculated with citation_metrics().",
    }
    review = OUTPUT_DIR / "day4_answer_review.json"
    if review.exists():
        answers = json.loads(review.read_text(encoding="utf-8"))
        report["citation_faithfulness"] = citation_metrics(answers)
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / "day4_evaluation_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved Day-4 evaluation report: {path}")
    print(json.dumps({k:v for k,v in report.items() if k.endswith("metric") or k=="citation_faithfulness"}, indent=2))

def answer(question: str, top_k: int = 5):
    rows = search(question, top_k=top_k, strategy="hybrid", config_name="B_850_150", rerank=True)
    print("\nGrounded answer:\n")
    print(generate_grounded_answer(question, rows))


def main():
    parser = argparse.ArgumentParser(description="Clinical RAG Day 4 - Adult Hypertension safety and evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="Build the Day-1 baseline index (850/150)")
    sub.add_parser("index-day2", help="Build both official Day-2 chunk configurations")

    p_search = sub.add_parser("search", help="Retrieve evidence")
    p_search.add_argument("question", nargs="+")
    p_search.add_argument("--top-k", type=int, choices=TOP_K_OPTIONS, default=TOP_K)
    p_search.add_argument("--strategy", choices=("semantic", "keyword", "hybrid"), default="semantic")
    p_search.add_argument("--config", default="B_850_150", choices=tuple(DAY2_CHUNK_CONFIGS))
    p_search.add_argument("--rerank", action="store_true")

    sub.add_parser("review", help="Manually label retrieved chunks for the Day-2 evaluation set")
    sub.add_parser("evaluate-day2", help="Compare chunking and retrieval strategies using the evaluation set")
    sub.add_parser("evaluate-day4", help="Run Day-4 safety and retrieval evaluation")

    p_answer = sub.add_parser("answer", help="Retrieve evidence and generate a grounded answer")
    p_answer.add_argument("question", nargs="+")
    p_answer.add_argument("--top-k", type=int, choices=TOP_K_OPTIONS, default=TOP_K)

    args = parser.parse_args()
    try:
        if args.command == "index":
            index()
        elif args.command == "index-day2":
            index_day2()
        elif args.command == "search":
            search(" ".join(args.question), args.top_k, args.strategy, args.config, args.rerank)
        elif args.command == "review":
            review_labels()
        elif args.command == "evaluate-day2":
            evaluate_day2()
        elif args.command == "evaluate-day4":
            evaluate_day4()
        elif args.command == "answer":
            answer(" ".join(args.question), args.top_k)
    except (ImportError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        if isinstance(exc, ImportError):
            print("Run: python -m pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
