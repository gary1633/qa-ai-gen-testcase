import json
import os
import re
from copy import copy
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.cell_range import MultiCellRange
from openpyxl.worksheet.worksheet import Worksheet

from src.core.clarification import PENDING_CLARIFICATION_MARKER
from src.core.llm import load_config
from src.core.models import RequirementAnalysis, TestCase

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FONT_FAMILY = "Be Vietnam Pro"
CODE_FONT = Font(name="Consolas", size=9, bold=False)
PENDING_FILL = PatternFill(start_color="FFFFF2CC", end_color="FFFFF2CC", fill_type="solid")

# Nhãn header cột trong template (dòng chứa "Testcase ID") -> field của TestCase được Agent điền.
# Template là nguồn chuẩn: exporter định vị cột theo nhãn, không theo vị trí cố định.
# Các cột theo dõi thực thi (Kết quả thực tế, Người tạo, Kế hoạch thực hiện, Ngày thực hiện) cố ý để trống.
ID_HEADER = "Testcase ID"
STATUS_HEADER = "Trạng thái test"
COLUMN_FIELDS: Dict[str, str] = {
    ID_HEADER: "testcase_id",
    "Tên testcase": "title",
    "Các bước thực hiện": "steps",
    "Kết quả mong đợi": "expected_result",
    "Dữ liệu test": "test_data",
    STATUS_HEADER: "test_status",
    "Mức độ ưu tiên": "priority",
    "Ghi chú": "note",
}
CENTERED_FIELDS = {"testcase_id", "test_status", "priority"}

# Khối "KẾT QUẢ KIỂM THỬ": dòng nhãn bắt đầu bằng "Total" ở cột A, công thức nằm ngay dòng dưới.
SUMMARY_TOTAL = "Total"
SUMMARY_STATUS_LABELS = ("Passed", "Failed", "Blocked", "Not Test")
SUMMARY_REMAINDER = "Not Executed"

# Nhãn metadata ở cột B phía trên header; giá trị ghi vào ô bên phải nhãn.
META_DOC_CODE = "Mã tài liệu"
META_APP = "Tên ứng dụng"
META_VERSION = "Phiên bản"
META_FEATURE = "Mô tả tính năng"
META_DOC_LINK = "Tài liệu"

JIRA_KEY_REGEX = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def format_cell_json_text(text: str) -> str:
    """Tự động phát hiện và format đẹp các đoạn JSON trong Steps, Expected Result, Test Data."""
    if not text or not isinstance(text, str):
        return text or ""

    text = text.strip()

    # 1. Nếu toàn bộ ô là JSON
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except Exception:
            pass

    # 2. Nếu là text có chứa đoạn JSON lồng bên trong
    def replacer(match):
        json_str = match.group(0)
        try:
            return json.dumps(json.loads(json_str), indent=2, ensure_ascii=False)
        except Exception:
            return json_str

    pattern = r'(\{(?:[^{}]|(?:\{[^{}]*\}))*\})'
    return re.sub(pattern, replacer, text)


def sanitize_filename(name: str) -> str:
    """Tạo tên file an toàn từ tên tính năng."""
    clean = re.sub(r'[\\/*?:\[\]"<>|]', '_', name)
    clean = clean.replace(" ", "_")
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean[:50] if clean else "TestSuite"


def sanitize_sheet_name(name: str) -> str:
    """Loại bỏ ký tự không hợp lệ trong Excel sheet name và giới hạn 30 ký tự."""
    clean = re.sub(r'[\\/*?:\[\]]', '_', name)
    clean = clean.strip()
    return clean[:30] if clean else "QA_TestSuite"


def get_default_template_path() -> str:
    """Template mặc định khai báo tại configs/config.yaml -> excel.template_path (tương đối theo thư mục dự án)."""
    configured = (load_config().get("excel") or {}).get("template_path")
    if not configured:
        raise ValueError("configs/config.yaml thiếu khóa excel.template_path (đường dẫn template Excel mặc định).")
    path = Path(configured)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def _find_testcase_sheet(wb: openpyxl.Workbook) -> Tuple[Worksheet, int]:
    """Trả về (sheet test case, dòng header) — sheet đầu tiên có ô cột A bằng 'Testcase ID'."""
    for ws in wb.worksheets:
        for row in range(1, ws.max_row + 1):
            if str(ws.cell(row, 1).value or "").strip() == ID_HEADER:
                return ws, row
    raise ValueError(f"Template không có sheet test case nào chứa header '{ID_HEADER}' ở cột A.")


def _map_columns(ws: Worksheet, header_row: int) -> Dict[str, int]:
    """field TestCase -> chỉ số cột, đọc từ nhãn header của template."""
    columns: Dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        label = str(ws.cell(header_row, col).value or "").strip()
        if label in COLUMN_FIELDS:
            columns[COLUMN_FIELDS[label]] = col
    missing = [label for label, field in COLUMN_FIELDS.items() if field not in columns]
    if missing:
        raise ValueError(f"Header template (dòng {header_row}) thiếu các cột: {', '.join(missing)}")
    return columns


def _find_label_cell(ws: Worksheet, label: str, column: int, last_row: int) -> Optional[int]:
    for row in range(1, last_row):
        if str(ws.cell(row, column).value or "").strip() == label:
            return row
    return None


def _fill_metadata(ws: Worksheet, header_row: int, analysis: RequirementAnalysis) -> None:
    link = analysis.jira_or_doc_link or ""
    values = {
        META_DOC_CODE: ", ".join(dict.fromkeys(JIRA_KEY_REGEX.findall(link))),
        META_APP: analysis.app_name,
        META_VERSION: analysis.version,
        META_FEATURE: analysis.feature_name,
        META_DOC_LINK: link or "N/A",
    }
    for label, value in values.items():
        row = _find_label_cell(ws, label, 2, header_row)
        if row is None:
            raise ValueError(f"Template thiếu nhãn metadata '{label}' ở cột B phía trên header.")
        ws.cell(row, 3).value = value


def _write_summary_formulas(ws: Worksheet, header_row: int, columns: Dict[str, int], first_row: int, last_row: int) -> None:
    label_row = _find_label_cell(ws, SUMMARY_TOTAL, 1, header_row)
    if label_row is None:
        raise ValueError(f"Template thiếu khối thống kê có nhãn '{SUMMARY_TOTAL}' ở cột A.")
    formula_row = label_row + 1
    id_range = f"{get_column_letter(columns['testcase_id'])}{first_row}:{get_column_letter(columns['testcase_id'])}{last_row}"
    status_letter = get_column_letter(columns["test_status"])
    status_range = f"{status_letter}{first_row}:{status_letter}{last_row}"

    label_cols: Dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        label = str(ws.cell(label_row, col).value or "").strip()
        if label:
            label_cols[label] = col

    total_col = label_cols[SUMMARY_TOTAL]
    total_ref = f"{get_column_letter(total_col)}{formula_row}"
    ws.cell(formula_row, total_col).value = f'=COUNTIF({id_range},"TC*")'
    status_refs = []
    for status in SUMMARY_STATUS_LABELS:
        if status in label_cols:
            col = label_cols[status]
            ws.cell(formula_row, col).value = f'=COUNTIF({status_range},"{status}")'
            status_refs.append(f"{get_column_letter(col)}{formula_row}")
    if SUMMARY_REMAINDER in label_cols and status_refs:
        ws.cell(formula_row, label_cols[SUMMARY_REMAINDER]).value = f"={total_ref}-SUM({','.join(status_refs)})"


def _row_styles(ws: Worksheet, row: int, last_col: int) -> Dict[int, object]:
    return {col: copy(ws.cell(row, col)._style) for col in range(1, last_col + 1)}


def _render_steps(tc: TestCase) -> str:
    """Template không có cột 'Điều kiện tiên quyết' -> ghi preconditions ở đầu cột 'Các bước thực hiện'."""
    steps = format_cell_json_text(tc.steps)
    preconditions = (tc.preconditions or "").strip()
    if not preconditions:
        return steps
    return f"Điều kiện tiên quyết:\n{preconditions}\n\nCác bước:\n{steps}"


def _id_formula(columns: Dict[str, int], header_row: int, row: int) -> str:
    """ID tự đánh số lại khi xóa/chèn dòng: đếm các ô 'TC*' phía trên trong cột ID (bỏ qua dòng banner).
    Mốc đầu khóa ở dòng header để vùng đếm không bao giờ chứa chính ô hiện tại (tránh tham chiếu vòng)."""
    id_col = get_column_letter(columns["testcase_id"])
    title_col = get_column_letter(columns["title"])
    return (
        f'=IF({title_col}{row}<>"","TC "&TEXT(COUNTIF({id_col}${header_row}:{id_col}{row - 1},"TC*")+1,"00"),"")'
    )


def _cell_values(tc: TestCase, id_formula: str) -> Dict[str, str]:
    return {
        "testcase_id": id_formula,
        "title": tc.title,
        "steps": _render_steps(tc),
        "expected_result": format_cell_json_text(tc.expected_result),
        "test_data": format_cell_json_text(tc.test_data),
        "test_status": tc.test_status or "Not Test",
        "priority": tc.priority or "High",
        "note": tc.note or "",
    }


def export_test_cases_to_excel(
    analysis: RequirementAnalysis,
    test_cases: List[TestCase],
    template_path: Optional[str] = None,
    output_path: Optional[str] = None,
    target_sheet_name: Optional[str] = None,
    *,
    pending_clarifications: Optional[List[str]] = None
) -> str:
    """
    Tạo một file Excel MỚI (mặc định trong thư mục outputs/) từ template phiếu kiểm thử:
    - Sheet test case (sheet có header 'Testcase ID') được đổi tên theo tính năng, giữ nguyên logo,
      style, dropdown và các sheet phụ khác của template (vd: DRAW_BUG).
    - Metadata, khối thống kê và cột dữ liệu được định vị theo NHÃN trong template.
    - Dòng banner nhóm L1/L2 và dòng dữ liệu dùng lại style của các dòng mẫu ngay dưới header.
    """
    actual_template = template_path or get_default_template_path()
    if not os.path.exists(actual_template):
        raise FileNotFoundError(f"Không tìm thấy file template tại: {actual_template}")

    # 1. Xác định đường dẫn file đích
    if output_path:
        dest_path = output_path
    else:
        dest_path = os.path.join("outputs", f"Testsuite_{sanitize_filename(analysis.feature_name)}.xlsx")
    parent_dir = os.path.dirname(dest_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # 2. Định vị cấu trúc template
    wb = openpyxl.load_workbook(actual_template)
    ws, header_row = _find_testcase_sheet(wb)
    columns = _map_columns(ws, header_row)
    last_col = max(col for col in range(1, ws.max_column + 1) if ws.cell(header_row, col).value not in (None, ""))

    # 3. Đổi tên sheet test case (tại chỗ để giữ logo/dropdown/autofilter của template)
    desired_name = target_sheet_name or sanitize_sheet_name(analysis.feature_name)
    other_names = {s for s in wb.sheetnames if s != ws.title}
    final_sheet_name = desired_name
    counter = 1
    while final_sheet_name in other_names:
        final_sheet_name = f"{desired_name[:26]}_{counter}"
        counter += 1
    ws.title = final_sheet_name

    # 4. Metadata phía trên header (Ngày thực hiện / Người duyệt / Ngày duyệt để trống cho người thực thi)
    _fill_metadata(ws, header_row, analysis)

    # 5. Lấy style 3 dòng mẫu (banner L1, banner L2, dữ liệu) rồi xóa toàn bộ dữ liệu mẫu dưới header
    l1_styles = _row_styles(ws, header_row + 1, last_col)
    l2_styles = _row_styles(ws, header_row + 2, last_col)
    data_styles = _row_styles(ws, header_row + 3, last_col)
    if ws.max_row > header_row:
        ws.delete_rows(header_row + 1, ws.max_row - header_row)

    # 6. Đổ dữ liệu Test Case có gom nhóm L1 / L2
    banner_col = columns["title"]
    first_row = header_row + 1
    current_row = first_row
    current_group_feature = None
    current_group_functional = None

    def write_banner(row: int, text: str, styles: Dict[int, object]) -> None:
        for col in range(1, last_col + 1):
            ws.cell(row, col)._style = copy(styles[col])
        cell = ws.cell(row, banner_col)
        cell.value = text
        cell.alignment = Alignment(vertical="center", horizontal="left")

    for tc in test_cases:
        if tc.group_feature and tc.group_feature != current_group_feature:
            current_group_feature = tc.group_feature
            current_group_functional = None
            write_banner(current_row, current_group_feature, l1_styles)
            current_row += 1

        if tc.group_functional and tc.group_functional != current_group_functional:
            current_group_functional = tc.group_functional
            write_banner(current_row, current_group_functional, l2_styles)
            current_row += 1

        is_pending = PENDING_CLARIFICATION_MARKER in (tc.note or "")
        for col in range(1, last_col + 1):
            ws.cell(current_row, col)._style = copy(data_styles[col])
        for field, value in _cell_values(tc, _id_formula(columns, header_row, current_row)).items():
            cell = ws.cell(current_row, columns[field])
            cell.value = value
            cell.alignment = Alignment(
                vertical="top",
                horizontal="center" if field in CENTERED_FIELDS else "left",
                wrap_text=True,
            )
            if field == "expected_result" and "{" in value:
                cell.font = CODE_FONT
        if is_pending:
            for col in range(1, last_col + 1):
                ws.cell(current_row, col).fill = PENDING_FILL
        current_row += 1

    last_row = max(current_row - 1, first_row)

    # 7. Công thức thống kê, dropdown và autofilter theo đúng vùng dữ liệu mới
    _write_summary_formulas(ws, header_row, columns, first_row, last_row)
    for dv in ws.data_validations.dataValidation:
        letters = sorted({get_column_letter(rng.min_col) for rng in dv.sqref.ranges})
        dv.sqref = MultiCellRange(" ".join(f"{letter}{first_row}:{letter}{last_row}" for letter in letters))
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(last_col)}{last_row}"

    if pending_clarifications:
        q_ws = wb.create_sheet(title="Cần làm rõ (Pending)")
        q_ws.cell(1, 1).value = f"CÂU HỎI CẦN USER / PO / BA LÀM RÕ - {analysis.feature_name}"
        q_ws.cell(1, 1).font = Font(name=FONT_FAMILY, size=11, bold=True)
        q_ws.cell(2, 1).value = (
            "Các test case được tô màu vàng và có ghi chú PENDING CLARIFICATION trong sheet test case "
            "đang thiếu API sample / message chính xác. KHÔNG dùng làm bản chính thức trước khi chốt các câu hỏi dưới đây."
        )
        for i, q in enumerate(pending_clarifications, start=1):
            cell = q_ws.cell(3 + i, 1)
            cell.value = f"{i}. {q}"
            cell.font = Font(name=FONT_FAMILY, size=10)
            cell.alignment = Alignment(vertical="top", horizontal="left", wrap_text=True)
        q_ws.column_dimensions["A"].width = 140

    wb.active = wb.worksheets.index(ws)
    wb.save(dest_path)
    return dest_path
