"""AI 에이전트용 MCP 서버(읽기 전용 도구). Claude와 ChatGPT가 같은 서버를 쓴다.
  Claude(로컬):  python -m src.mcp_server                      (stdio)
  ChatGPT(원격): python -m src.mcp_server --transport http     (http://127.0.0.1:8000/mcp)
                 ChatGPT는 공개 HTTPS 주소가 필요하다 -> 터널/배포는 사용자가 결정(docs/ai_trade_design.md 8장).
설정 파일은 환경변수 PROFIT_CONFIG(기본 config.yaml)."""
import argparse
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from src import service

server = MCPServer(
    name="profit-candidates",
    instructions=("순이익 후보 평가 도구. 읽기 전용이며 승인·주문·결제를 하지 않는다. "
                  "순이익은 세전(부가세·소득세 미반영). 네이버 파생값은 응답에서 제외된다(DEC-008). "
                  "실행 대상은 사람이 승인한 후보(list_approved_candidates)뿐이다."),
)
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


@server.tool(annotations=READ_ONLY, structured_output=True,
             description="도매 원가 C, 도매 배송비 S, 시장 기준가 M(고객 총지불액, 배송비 포함)으로 "
                         "T_min·순이익·보수 순이익·광고비 손익분기율·판정(통과/보류/탈락)을 계산한다. "
                         "customer_ship(F)이 없으면 S를 쓴다.")
def evaluate_candidate(cost: float, ship: float, market: float, customer_ship: float | None = None) -> dict[str, Any]:
    return service.evaluate_candidate(cost, ship, market, customer_ship)


@server.tool(annotations=READ_ONLY, structured_output=True,
             description="run_id의 실행 요약(결론, 판정별 건수)과 통과·보류 후보 목록을 돌려준다. "
                         "성장률 등 네이버 파생값은 제외된다.")
def get_run_summary(run_id: str) -> dict[str, Any]:
    return service.get_run_summary(run_id)


@server.tool(annotations=READ_ONLY, structured_output=True,
             description="run_id에서 사람이 승인한 후보만 돌려준다(실행 승인=승인 AND 항목 O). "
                         "AI 거래 상대는 이 목록에 있는 항목만 실행 대상으로 삼아야 한다.")
def list_approved_candidates(run_id: str) -> dict[str, Any]:
    return service.list_approved_candidates(run_id)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m src.mcp_server")
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument("--host", default="127.0.0.1", help="기본은 이 컴퓨터에서만 접속 가능")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    if args.transport == "stdio":
        server.run()
    else:
        server.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
