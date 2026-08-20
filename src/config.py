from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_DIR = ROOT / "chroma_db"
OUTPUT_DIR = ROOT / "outputs"

# Day-1 baseline retained for comparison.
CHUNK_SIZE = 850
CHUNK_OVERLAP = 150

# Day-2 experiments from the official agenda.
DAY2_CHUNK_CONFIGS = {
    "A_500_75": {"chunk_size": 500, "chunk_overlap": 75},
    "B_850_150": {"chunk_size": 850, "chunk_overlap": 150},
}
TOP_K_OPTIONS = (3, 5, 10)
TOP_K = 5
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
COLLECTION_NAME = "hypertension_guidelines"

DOCUMENTS = [
    {
        "path": DATA_DIR / "hypertension_nice_ng136.pdf",
        "document_id": "HTN-NG136",
        "title": "Hypertension in adults: diagnosis and management (NG136)",
        "source": "NICE",
        "url": "https://www.nice.org.uk/guidance/ng136/resources/hypertension-in-adults-diagnosis-and-managementpdf-66141722710213",
        "publisher": "National Institute for Health and Care Excellence",
        "publication_date": "2019-08-28",
        "last_updated": "2026-02-26",
        "version": "Published 2019-08-28; last updated 2026-02-26",
    },
    {
        "path": DATA_DIR / "hypertension_patient_decision_aid.pdf",
        "document_id": "HTN-PDA-2019",
        "title": "How do I control my blood pressure? Lifestyle options and choice of medicines",
        "source": "NICE",
        "url": "https://www.nice.org.uk/guidance/ng136/resources/how-do-i-control-my-blood-pressure-lifestyle-options-and-choice-of-medicines-patient-decision-aid-pdf-6899918221",
        "publisher": "National Institute for Health and Care Excellence",
        "publication_date": "2019-08-28",
        "last_updated": "2019-08",
        "version": "Published 2019-08-28; PDF last updated August 2019",
    },
]

APPROVED_DOCUMENT_IDS = {d["document_id"] for d in DOCUMENTS}
CLINICAL_SCOPE = "Adult Hypertension"
CLINICAL_TEST_QUESTIONS_PATH = DATA_DIR / "clinical_test_questions.json"
SCOPE_APPROVAL_STATUS = "PENDING_MENTOR_APPROVAL"
AI_REUSE_STATUS = "PENDING_EXPLICIT_CONFIRMATION"
MAX_QUERY_LENGTH = 1000
MAX_TOP_K = 10
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 60

TOP1_MIN_SIMILARITY = float(__import__("os").getenv("TOP1_MIN_SIMILARITY","0.35"))
DAY4_EVAL_SET_PATH = DATA_DIR / "day4_evaluation_questions.json"
