"""결과 엑셀의 보기 좋은 서식. 셀 위치·라벨·열 순서는 바꾸지 않고 서식만 입힌다(승인 가져오기가 라벨로 칸을 찾음)."""
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

FONT = "맑은 고딕"
NAVY, INK, MUTED, LINE = "1F3A5F", "222B36", "6B7785", "D9DEE5"
BAND, INPUT = "F3F6FA", "FFF8DC"
VERDICT = {  # 판정 -> (배경, 글자)
    "통과": ("DDF2E3", "17653A"),
    "보류": ("FFF1C7", "7A5600"),
    "탈락": ("FBDCDC", "9B1C1C"),
    "입력 오류": ("E4E7EB", "4A5560"),
}
SECTIONS = {"처리 수치", "탈락·보류 사유 분포", "이상 징후", "결정 요청", "승인 입력"}

_thin = Side(style="thin", color=LINE)
BOX = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
BOTTOM = Border(bottom=_thin)


def _fill(hex_):
    return PatternFill("solid", fgColor=hex_)


def _font(**kw):
    kw.setdefault("name", FONT)
    kw.setdefault("size", 10)
    kw.setdefault("color", INK)
    return Font(**kw)


def style_summary(ws):
    ws.sheet_view.showGridLines = False
    for col, w in (("A", 34), ("B", 84), ("C", 44)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=3):
        for c in row:
            c.font = _font()
            c.alignment = Alignment(vertical="center", wrap_text=True)
    ws["A1"].font = _font(size=16, bold=True, color=NAVY)
    ws["A1"].alignment = Alignment(vertical="center", wrap_text=False)
    ws.row_dimensions[1].height = 30
    for r in range(2, 4):
        ws.cell(r, 1).font = _font(color=MUTED)
        ws.cell(r, 2).font = _font(color=MUTED)

    section = None
    for r in range(1, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if a == "결정 요청":                      # 같은 줄에 안내문이 있으므로 밝은 밴드로 표시
            section = a
            for col in (1, 2, 3):
                ws.cell(r, col).fill = _fill("E8F0FA")
            ws.cell(r, 1).font = _font(bold=True, color=NAVY, size=11)
            ws.cell(r, 2).font = _font(color=INK)
            ws.cell(r, 2).alignment = Alignment(vertical="center", wrap_text=True)
            ws.row_dimensions[r].height = 38
            continue
        if a in SECTIONS:
            section = a
            for col in (1, 2, 3):
                ws.cell(r, col).fill = _fill(NAVY)
            ws.cell(r, 1).font = _font(bold=True, color="FFFFFF")
            ws.row_dimensions[r].height = 22
            continue
        if a == "결론":
            for col in (1, 2, 3):
                ws.cell(r, col).fill = _fill("E8F0FA")
            ws.cell(r, 1).font = _font(bold=True, color=NAVY, size=11)
            ws.cell(r, 2).font = _font(bold=True, size=12, color=NAVY)
            ws.row_dimensions[r].height = 40
        elif a and str(a).startswith("근거"):
            ws.cell(r, 1).font = _font(bold=True, color=MUTED)
            ws.cell(r, 3).font = _font(color=MUTED, size=9)
            ws.row_dimensions[r].height = 20
        elif section == "처리 수치" and a:
            bg, fg = VERDICT.get(a, (BAND, INK))
            ws.cell(r, 1).fill = _fill(bg)
            ws.cell(r, 1).font = _font(bold=True, color=fg)
            ws.cell(r, 2).font = _font(bold=True, size=12, color=fg)
            ws.cell(r, 2).alignment = Alignment(horizontal="left", vertical="center")
            for col in (1, 2):
                ws.cell(r, col).border = BOTTOM
            ws.row_dimensions[r].height = 22
        elif section in ("탈락·보류 사유 분포", "이상 징후") and a:
            for col in (1, 2, 3):
                ws.cell(r, col).border = BOTTOM
            ws.cell(r, 2).alignment = Alignment(horizontal="left", vertical="center")
            v = ws.cell(r, 3).value
            if section == "탈락·보류 사유 분포" and v in VERDICT:
                ws.cell(r, 3).font = _font(bold=True, color=VERDICT[v][1])
            if section == "이상 징후" and ws.cell(r, 2).value:
                ws.cell(r, 1).font = _font(bold=True, color=VERDICT["보류"][1])
            if section == "이상 징후":
                ws.cell(r, 3).font = _font(color=MUTED, size=9)
        if a in ("실행 승인", "승인 메모"):
            ws.cell(r, 1).font = _font(bold=True)
            ws.cell(r, 2).fill = _fill(INPUT)
            ws.cell(r, 2).border = BOX
            ws.row_dimensions[r].height = 24 if a == "실행 승인" else 40
            ws.cell(r, 3).value = "드롭다운: 승인 / 반려 / 보류" if a == "실행 승인" else "선택 입력"
            ws.cell(r, 3).font = _font(color=MUTED, size=9)
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _header(ws, height=34):
    for c in ws[1]:
        c.font = _font(bold=True, color="FFFFFF")
        c.fill = _fill(NAVY)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOX
    ws.row_dimensions[1].height = height


def _verdict_cell(c):
    bg, fg = VERDICT.get(c.value, (BAND, INK))
    c.fill = _fill(bg)
    c.font = _font(bold=True, color=fg)
    c.alignment = Alignment(horizontal="center", vertical="center")


def style_candidates(ws, col_idx):
    """col_idx: 헤더명 -> 열 번호."""
    ws.sheet_view.showGridLines = False
    _header(ws, 44)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    wrap_cols = {col_idx["사유"], col_idx["경고"], col_idx["구분 라벨"]}
    center_cols = {col_idx["판매처 수"], col_idx["항목 승인(O/X)"]}
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font = _font()
            c.border = BOX
            c.alignment = Alignment(vertical="center", wrap_text=c.column in wrap_cols,
                                    horizontal="center" if c.column in center_cols else None)
        row[0].font = _font(bold=True)
        ws.row_dimensions[row[0].row].height = 32
        _verdict_cell(row[col_idx["판정"] - 1])
        row[col_idx["구분 라벨"] - 1].font = _font(size=8, color=MUTED)
        row[col_idx["경고"] - 1].font = _font(size=9, color=VERDICT["보류"][1])
        row[col_idx["사유"] - 1].font = _font(size=9)
        row[col_idx["항목 승인(O/X)"] - 1].fill = _fill(INPUT)
        row[col_idx["항목 승인(O/X)"] - 1].font = _font(bold=True)
        for h in ("순이익(세전: 부가세·소득세 미반영)", "보수 순이익"):
            c = row[col_idx[h] - 1]
            if isinstance(c.value, (int, float)) and c.value < 0:
                c.font = _font(bold=True, color=VERDICT["탈락"][1])
        for h in ("시장 기준가", "클릭 증가율", "순이익(세전: 부가세·소득세 미반영)"):
            c = row[col_idx[h] - 1]
            if isinstance(c.value, str):                    # 조회 실패/미확인/미입력 문구는 약하게
                c.font = _font(size=9, italic=True, color=MUTED)
                c.alignment = Alignment(horizontal="center", vertical="center")
    for col, w in {"키워드": 22, "도매처": 10, "시장 기준가": 12, "판매처 수": 9, "클릭 증가율": 11, "원가": 10,
                   "도매 배송비": 10, "순이익(세전: 부가세·소득세 미반영)": 16, "이익률": 9, "보수 순이익": 12,
                   "광고비 손익분기율": 12, "판정": 9, "사유": 42, "경고": 32, "구분 라벨": 30,
                   "항목 승인(O/X)": 11}.items():
        ws.column_dimensions[ws.cell(1, col_idx[col]).column_letter].width = w
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def style_rejects(ws):
    ws.sheet_view.showGridLines = False
    _header(ws, 30)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font = _font()
            c.border = BOX
            c.alignment = Alignment(vertical="center", wrap_text=c.column in (5, 6))
        row[0].font = _font(bold=True)
        _verdict_cell(row[2])
        row[3].number_format = "#,##0"
        row[3].alignment = Alignment(horizontal="right", vertical="center")
        row[4].font = _font(size=9)
        ws.row_dimensions[row[0].row].height = 30
    for col, w in zip("ABCDEF", (22, 10, 10, 13, 52, 44)):
        ws.column_dimensions[col].width = w
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
