from src import setup_keys


def test_clean_and_write(tmp_path):
    answers = iter([' "abc" ', "def ", "0100x", "AQAAx", " 590256 "])
    p = tmp_path / ".env"
    setup_keys.main(str(p), ask=lambda _: next(answers))
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines == ["NAVER_CLIENT_ID=abc", "NAVER_CLIENT_SECRET=def", "NAVER_AD_API_KEY=0100x",
                     "NAVER_AD_SECRET_KEY=AQAAx", "NAVER_AD_CUSTOMER_ID=590256"]
