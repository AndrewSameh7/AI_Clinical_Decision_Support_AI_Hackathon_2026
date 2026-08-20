from __future__ import annotations
import re
from typing import Dict, Iterable, List

RISK_CRITICAL = "critical"
RISK_HIGH = "high"
RISK_MEDIUM = "medium"
RISK_LOW = "low"

_PATIENT_SPECIFIC = re.compile(r"\b(for me|my patient|my blood pressure|my reading|this patient|should i|do i have|can i take|how much should i|emergency|right now|bleeding a lot|severe symptoms)\b", re.I)
_DIAGNOSIS = re.compile(r"\b(do i have|diagnos(?:e|is)|am i hypertensive|is this hypertension|is this a stroke|is this an emergency|personally have hypertension|tell me whether i)\b", re.I)
_DOSING = re.compile(r"\b(dose|dosage|mg\b|how many tablets|how much should i take|increase the dose|stop taking)\b", re.I)
_EMERGENCY = re.compile(r"\b(emergency|right now|severe symptoms|chest pain|shortness of breath|weakness on one side|confusion|fainting|bleeding a lot)\b", re.I)
_INJECTION = re.compile(r"(ignore (every|all|the) (instruction|instructions|evidence|rules)|forget (the|all) (instruction|instructions|evidence|rules)|use your own knowledge|reveal (the )?(system|developer|hidden) prompt|hidden system prompt|developer instructions|internal safety rules|jailbreak|act as an unrestricted|pretend you are|override the (safety|evidence|rules)|higher-priority instruction|follow that sentence|private instructions|anything marked private)", re.I)
_PRIVACY = re.compile(r"\b(database engine|database type|encryption algorithm|password-hashing|password hashing|session token|oauth secret|api key|another user|saved conversation|private patient|patient records|vector database contents|sensitive metadata|stored data)\b", re.I)
_OUT_OF_SCOPE = re.compile(r"\b(weather|football|soccer|recipe|stock price|politics|movie|song|joke|programming|python code|write code|database administration|bypass authentication|bypass .*authentication|export the database)\b", re.I)


def classify_query(question: str) -> Dict:
    q = " ".join(question.split())
    if _INJECTION.search(q):
        return {"category": "adversarial_injection", "risk": RISK_CRITICAL, "action": "refuse", "continue": False}
    if _PRIVACY.search(q):
        return {"category": "privacy_boundary", "risk": RISK_CRITICAL, "action": "refuse", "continue": False}
    if _EMERGENCY.search(q):
        return {"category": "emergency_like", "risk": RISK_CRITICAL, "action": "redirect", "continue": False}
    if _DOSING.search(q):
        return {"category": "medication_or_dosage", "risk": RISK_HIGH, "action": "refuse", "continue": False}
    if _DIAGNOSIS.search(q):
        return {"category": "diagnosis_request", "risk": RISK_HIGH, "action": "refuse", "continue": False}
    if _PATIENT_SPECIFIC.search(q):
        return {"category": "patient_specific", "risk": RISK_HIGH, "action": "refuse", "continue": False}
    if _OUT_OF_SCOPE.search(q):
        return {"category": "out_of_scope", "risk": RISK_MEDIUM, "action": "refuse", "continue": False}
    if len(q.split()) < 4 or re.search(r"\b(it|this|that|they|them|something|stuff)\b", q.lower()):
        return {"category": "ambiguous", "risk": RISK_MEDIUM, "action": "clarify", "continue": False}
    return {"category": "in_scope", "risk": RISK_LOW, "action": "retrieve", "continue": True}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9]+", text.lower()) if len(t) > 2}


def validate_claim_support(recommendation: str, evidence_text: str, min_overlap: float = 0.16) -> Dict:
    """Lightweight post-generation evidence check.

    This is deliberately conservative and explainable: claims are sentence-level, and
    each claim needs lexical overlap with the supplied evidence. Human review remains
    required for semantic citation correctness, as recommended by Day 4.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", recommendation.strip()) if s.strip()]
    evidence = _tokens(evidence_text)
    supported, unsupported = [], []
    for sentence in sentences:
        toks = _tokens(sentence)
        overlap = len(toks & evidence) / max(1, len(toks))
        item = {"claim": sentence, "overlap": round(overlap, 3), "supported": overlap >= min_overlap}
        (supported if item["supported"] else unsupported).append(item)
    return {"supported": supported, "unsupported": unsupported, "unsupported_claim_rate": round(len(unsupported) / max(1, len(sentences)), 4)}


def citation_metrics(answers: Iterable[Dict]) -> Dict:
    total_citations = valid_citations = total_claims = cited_claims = supported_claims = 0
    for answer in answers:
        evidence = answer.get("source_details", [])
        valid_docs = {x.get("document_name") for x in evidence}
        for item in answer.get("supporting_evidence", []) or []:
            claims = item.get("claim", "").strip()
            if claims:
                total_claims += 1
                if item.get("citations"):
                    cited_claims += 1
            for citation in item.get("citations", []) or []:
                total_citations += 1
                if citation.get("document") in valid_docs and citation.get("section") and citation.get("page"):
                    valid_citations += 1
                if item.get("supported", True):
                    supported_claims += 1
    return {
        "citation_validity": round(valid_citations / max(1, total_citations), 4),
        "citation_coverage": round(cited_claims / max(1, total_claims), 4),
        "claim_faithfulness": round(supported_claims / max(1, total_claims), 4),
        "unsupported_claim_rate": round(1 - supported_claims / max(1, total_claims), 4),
        "total_citations": total_citations,
        "total_claims": total_claims,
    }
