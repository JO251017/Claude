# Claude 플러그인·커넥터 설치 체크리스트 (PC에서 진행)

기준일: 2026-10-18 / 출처: 각 공식 문서·GitHub (설치 전 최신 README 재확인 권장)

## 0. 먼저 알아둘 것
- 인스타 영상(lazy_owen)의 "클로드 플러그인 10개" 중 사진에 보이는 8개만 정리함. 나머지 2개는 확인 필요.
- 대부분 "커넥터"가 아니라 플러그인/스킬/CLI라서 PC 터미널에서 설치해야 함.
- 설치 명령은 외부 코드를 내 PC에서 실행함. 실행 전 README 확인.

## 1. claude.ai에서 클릭으로 연결 (Settings → Connectors / Customize)
| 항목 | 방법 |
|---|---|
| Higgsfield | Add custom connector → 이름 `Higgsfield`, URL `https://mcp.higgsfield.ai/mcp` → Connect → 로그인 승인. 유료 구독 필요, API 키 불필요 |
| Katana (Higgsfield 편집 스킬) | 별도 설치 없음. Higgsfield 연결 후 `/katana` 또는 `/katana/<프리셋>` 입력 |
| HyperFrames (HeyGen) | 커넥터 디렉터리에서 "HyperFrames by HeyGen" 검색 → Connect |
| Remotion | Customize → Plugins에서 "Remotion" 활성화 (Anthropic Directory) |

HyperFrames 주의: 커넥터(`compose`, `render_video`)는 claude.ai 웹·데스크톱용. PC의 Claude Code/Cursor에서는 비활성화되며, 대신 `npx skills add heygen-com/hyperframes` 스킬(`/hyperframes`)을 쓰라고 안내함. 커넥터는 HeyGen 클라우드 프로젝트(공유·클라우드 렌더), 스킬은 로컬 HTML 파일 생성.

확인: 새 대화에서 "내 Higgsfield 크레딧 잔액 알려줘". 오류 시 Disconnect 후 재연결.
Katana 주의: 채팅 첨부 파일은 전달 안 됨 → 대화 안 Higgsfield 업로드 창 또는 미디어 직링크 사용.
참고: Katana MRP(재고관리 SaaS)를 뜻한 거라면 https://support.katanamrp.com/en/articles/15518371-how-to-connect-katana-to-claude-mcp (확인 필요)

## 2. Claude Code 터미널 (플러그인)
```
# Remotion
claude plugin marketplace add remotion-dev/claude-code-plugin
claude plugin install remotion@remotion

# HyperFrames
claude plugin marketplace add heygen-com/hyperframes
claude plugin install hyperframes@hyperframes

# Impeccable
/plugin marketplace add pbakaus/impeccable

# Taste
/plugin marketplace add Leonxlnx/taste-skill
/plugin install taste-skill@taste-skill

# prompts.chat
/plugin marketplace add f/prompts.chat
/plugin install prompts.chat@prompts.chat

# ECC (Everything Claude Code)
/plugin marketplace add affaan-m/everything-claude-code
/plugin install everything-claude-code@everything-claude-code
```
- ECC는 최근 `ecc@ecc`로 바뀐 듯함 → 안 되면 https://github.com/affaan-m/ecc 설치 마법사 (확인 필요)

## 3. 스킬 / CLI
```
# AgentBrowser (Vercel)
npm install -g agent-browser
agent-browser install
npx skills add vercel-labs/agent-browser

# Agent Reach (크롤링)
npx skills add Panniantong/Agent-Reach@agent-reach

# Graphify (지식 그래프로 토큰 절약)
pip install graphifyy
graphify install
```
- Agent Reach: 원격 install.md를 에이전트가 읽고 실행하는 방식은 검토 없이 쓰지 말 것.

## 4. MarkItDown (MCP)
```
pip install markitdown-mcp
claude mcp add markitdown -- markitdown-mcp
```
- Claude Desktop: `claude_desktop_config.json`에 `"markitdown": {"command": "markitdown-mcp"}` 추가
- 인증 없음 + 내 계정 권한으로 실행 → 공유 환경 금지.
- 대체: Adobe 커넥터(연결됨)의 `pdf_to_markdown`

## 5. 이미 연결된 커넥터 (대체 가능)
- Firecrawl: 웹 검색·크롤링 (Agent Reach 대체 가능)
- Adobe: PDF→마크다운 등
- 미연결 대체 후보: TinyFish, Tavily, Nimble (크롤링/브라우저)

## 6. 진행 체크
- [ ] Higgsfield 연결 + 잔액 조회 확인
- [ ] Katana `/katana` 동작 확인
- [ ] HyperFrames 커넥터 연결
- [ ] Remotion 플러그인 활성화
- [ ] Impeccable / Taste / prompts.chat / ECC
- [ ] AgentBrowser / Agent Reach / Graphify
- [ ] MarkItDown
- [ ] 영상 속 나머지 2개 확인

## 출처
- https://higgsfield.ai/blog/higgsfield-katana
- https://higgsfield.ai/creator-hub/help-center/integrations/how-do-i-connect-higgsfield-to-ai-agent
- https://www.remotion.dev/docs/ai/claude-code-plugin
- https://hyperframes.heygen.com/guides/plugins
- https://github.com/pbakaus/impeccable
- https://github.com/leonxlnx/taste-skill
- https://github.com/f/prompts.chat/blob/main/CLAUDE-PLUGIN.md
- https://github.com/affaan-m/ecc
- https://agent-browser.dev/installation
- https://github.com/Panniantong/Agent-Reach/blob/main/docs/README_en.md
- https://github.com/Graphify-Labs/graphify
- https://www.aibuilderclub.com/blog/markitdown-microsoft-convert-files-markdown-llm
