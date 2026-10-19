"""Claude용 MCP 서버(읽기 전용 도구). 실행: python -m src.mcp_server  (stdio)
설정 파일은 환경변수 PROFIT_CONFIG(기본 config.yaml)."""
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from src import service

server = MCPServer(
    name="profit-candidates",
    instructions=("순이익 후보 평가 도구. 읽기 전용이며 승인·주문·결제를 하지 않는다. "
                  "순이익은 세전(부가세·소득세 미반영). 네이버 파생값은 응답에서 제외된다(DEC-008)."),
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


if __name__ == "__main__":
    server.run()
