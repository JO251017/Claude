# FreeLLMAPI MCP 도구

[FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi)(MIT)는 여러 LLM 무료 티어를 OpenAI 호환 엔드포인트 하나로 묶는 셀프호스팅 라우터입니다. 이 저장소의 `.mcp.json`은 그 라우터의 MCP 엔드포인트(`/mcp`)를 Claude Code 프로젝트 도구로 등록합니다.

## 1. 라우터 실행

Docker 기준 (공식 설치 스크립트):

```bash
curl -fsSL https://freellmapi.co/install.sh | bash
```

또는 저장소를 클론한 뒤 `docker compose up -d`. Windows/macOS는 [Releases](https://github.com/tashfeenahmed/freellmapi/releases/latest)의 데스크톱 앱을 써도 됩니다.

## 2. 키 등록과 MCP 활성화

1. http://localhost:3001 에서 **Keys** 페이지에 제공자(Groq, Gemini 등) API 키를 추가합니다.
2. Keys 페이지 헤더의 **통합 API 키**(unified key)를 복사합니다.
3. 새로 설치한 경우 MCP는 기본으로 꺼져 있습니다. Keys 페이지 **Agent compatibility**에서 켭니다. 꺼져 있으면 `/mcp`가 403을 반환합니다.

## 3. 환경 변수 설정

키는 저장소에 커밋하지 않고 환경 변수로 넘깁니다.

```bash
export FREELLMAPI_API_KEY="freellmapi-..."           # 필수: 통합 API 키
export FREELLMAPI_URL="http://localhost:3001"        # 선택: 기본값 localhost:3001
```

## 4. 확인

저장소 루트에서 Claude Code를 실행하면 프로젝트 MCP 서버 `freellmapi` 승인 요청이 뜹니다. `/mcp`로 연결 상태를 확인합니다.

연결되면 Claude가 FreeLLMAPI 모델에 텍스트 작업을 맡기거나, 사용 가능한 모델, 제공자 상태, 사용량과 라우팅 전략을 조회할 수 있습니다.
