from src import web


def test_day4_storage_limit_and_no_daily_question_limit():
    assert web.USER_STORAGE_LIMIT_BYTES == 2 * 1024 * 1024
    assert not hasattr(web, "DAILY_QUESTION_LIMIT")
    assert not hasattr(web, "_reserve_daily_question")
