from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import APPROVED_DOCUMENT_IDS, MAX_QUERY_LENGTH, MAX_TOP_K


def test_retrieval_scope_is_restricted_to_approved_documents():
    assert APPROVED_DOCUMENT_IDS == {"HTN-NG136", "HTN-PDA-2019"}


def test_api_limits_are_bounded():
    assert MAX_QUERY_LENGTH == 1000
    assert MAX_TOP_K == 10
