"""키 입력 도우미: 항목 이름을 하나씩 묻고 .env에 저장한다. 공백·따옴표는 자동 제거. 값은 화면에 다시 출력하지 않는다."""
import os

ASK = [
    ("NAVER_CLIENT_ID", "[1/5] 네이버 개발자센터 앱의 Client ID"),
    ("NAVER_CLIENT_SECRET", "[2/5] 네이버 개발자센터 앱의 Client Secret"),
    ("NAVER_AD_API_KEY", "[3/5] 검색광고 '엑세스라이선스'"),
    ("NAVER_AD_SECRET_KEY", "[4/5] 검색광고 '비밀키'"),
    ("NAVER_AD_CUSTOMER_ID", "[5/5] 검색광고 CUSTOMER ID (숫자)"),
]


def clean(v: str) -> str:
    return v.strip().strip('"').strip("'").strip()


def write_env(path: str, values: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for k, _ in ASK:
            f.write(f"{k}={values.get(k, '')}\n")


def main(path: str = ".env", ask=input) -> None:
    print("각 항목을 복사해서 붙여 넣고 Enter를 누르세요. 모르면 그냥 Enter(건너뛰기).\n")
    values = {}
    for key, label in ASK:
        values[key] = clean(ask(label + ": "))
    write_env(path, values)
    print("\n저장했습니다(값은 화면에 다시 표시하지 않습니다).")


if __name__ == "__main__":
    main()
