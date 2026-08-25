import os
import re
import json
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse
import requests
from dotenv import load_dotenv

load_dotenv()


def extract_jira_key(input_str: str) -> Optional[str]:
    """
    Trích xuất mã Jira Ticket từ chuỗi hoặc URL.
    Ví dụ: 'VWCBT-3800' hoặc 'https://galaxyfinx.atlassian.net/browse/VWCBT-3800' -> 'VWCBT-3800'
    """
    if not input_str:
        return None
    input_str = input_str.strip()
    match = re.search(r'([A-Z0-9]+-\d+)', input_str, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def extract_jira_server_url(input_str: str) -> Optional[str]:
    """
    Trích xuất Server URL từ link Jira nếu người dùng truyền vào cả URL.
    Ví dụ: 'https://galaxyfinx.atlassian.net/browse/VWCBT-3800' -> 'https://galaxyfinx.atlassian.net'
    """
    if not input_str:
        return None
    if "http://" in input_str or "https://" in input_str:
        parsed = urlparse(input_str.strip())
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


def parse_adf_to_markdown(node: Any) -> str:
    """
    Chuyển đổi Atlassian Document Format (ADF) của Jira Cloud sang Markdown.
    """
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return str(node)

    node_type = node.get("type", "")
    content = node.get("content", [])
    text = node.get("text", "")

    # Xử lý text node có marks (bold, italic, code, link)
    if node_type == "text":
        marks = node.get("marks", [])
        for mark in marks:
            m_type = mark.get("type")
            if m_type == "strong":
                text = f"**{text}**"
            elif m_type == "em":
                text = f"*{text}*"
            elif m_type == "code":
                text = f"`{text}`"
            elif m_type == "link":
                href = mark.get("attrs", {}).get("href", "")
                text = f"[{text}]({href})"
        return text

    # Xử lý các node con đệ quy
    inner_texts = [parse_adf_to_markdown(child) for child in content]
    inner_str = "".join(inner_texts)

    if node_type == "doc":
        return "\n\n".join([parse_adf_to_markdown(c) for c in content]).strip()
    elif node_type == "paragraph":
        return inner_str + "\n"
    elif node_type == "heading":
        level = node.get("attrs", {}).get("level", 2)
        return f"\n{'#' * level} {inner_str}\n"
    elif node_type == "bulletList":
        items = [f"- {parse_adf_to_markdown(item).strip()}" for item in content]
        return "\n" + "\n".join(items) + "\n"
    elif node_type == "orderedList":
        items = [f"{i}. {parse_adf_to_markdown(item).strip()}" for i, item in enumerate(content, 1)]
        return "\n" + "\n".join(items) + "\n"
    elif node_type == "listItem":
        return inner_str.strip()
    elif node_type == "codeBlock":
        lang = node.get("attrs", {}).get("language", "")
        return f"\n```{lang}\n{inner_str}\n```\n"
    elif node_type == "blockquote":
        return f"\n> {inner_str.strip()}\n"
    elif node_type == "table":
        rows = [parse_adf_to_markdown(row).strip() for row in content]
        return "\n" + "\n".join(rows) + "\n"
    elif node_type == "tableRow":
        cells = [parse_adf_to_markdown(cell).strip().replace("\n", " ") for cell in content]
        return "| " + " | ".join(cells) + " |"
    elif node_type in ["tableHeader", "tableCell"]:
        return inner_str.strip()
    elif node_type == "hardBreak":
        return "\n"
    elif node_type == "rule":
        return "\n---\n"
    
    return inner_str


class JiraConnector:
    """
    Kết nối Jira Cloud / Jira Server & Data Center để kéo User Story và Acceptance Criteria.
    """
    def __init__(
        self,
        server_url: Optional[str] = None,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        pat_token: Optional[str] = None
    ):
        self.server_url = (server_url or os.getenv("JIRA_SERVER_URL", "")).rstrip("/")
        self.email = (email or os.getenv("JIRA_EMAIL", "")).strip()
        self.api_token = (api_token or os.getenv("JIRA_API_TOKEN", "")).strip()
        self.pat_token = (pat_token or os.getenv("JIRA_PAT_TOKEN") or os.getenv("JIRA_BEARER_TOKEN", "")).strip()

    def is_configured(self) -> bool:
        return bool(self.server_url and (self.pat_token or (self.email and self.api_token)))

    def _get_auth_headers(self) -> Tuple[Optional[Tuple[str, str]], Dict[str, str]]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        auth = None
        if self.pat_token:
            headers["Authorization"] = f"Bearer {self.pat_token}"
        elif self.email and self.api_token:
            auth = (self.email, self.api_token)
        return auth, headers

    def fetch_issue(self, issue_key_or_url: str) -> Dict[str, Any]:
        """
        Lấy toàn bộ chi tiết Issue/User Story từ Jira API.
        """
        extracted_server = extract_jira_server_url(issue_key_or_url)
        if extracted_server:
            self.server_url = extracted_server

        if not self.is_configured():
            raise ValueError(
                "Jira chưa được cấu hình đầy đủ trong file .env!\n"
                f"• JIRA_SERVER_URL: {'Đã cấu hình' if self.server_url else 'CHƯA CẤU HÌNH'}\n"
                f"• JIRA_EMAIL: {self.email or 'CHƯA CẤU HÌNH'}\n"
                f"• JIRA_API_TOKEN: {'Đã cấu hình' if self.api_token else 'CHƯA CẤU HÌNH'}\n"
                "Vui lòng mở file .env và điền chính xác 3 thông số trên."
            )

        issue_key = extract_jira_key(issue_key_or_url)
        if not issue_key:
            raise ValueError(f"Không thể nhận diện mã Jira hợp lệ từ chuỗi: '{issue_key_or_url}'")

        auth, headers = self._get_auth_headers()
        
        # Gọi Jira REST API v2
        api_url_v2 = f"{self.server_url}/rest/api/2/issue/{issue_key}?expand=renderedFields,names,schema"
        
        try:
            resp = requests.get(api_url_v2, auth=auth, headers=headers, timeout=20)
            
            # Thử sang v3 nếu v2 404 (đối với một số tenant Jira Cloud mới)
            if resp.status_code == 404:
                api_url_v3 = f"{self.server_url}/rest/api/3/issue/{issue_key}?expand=renderedFields,names"
                resp = requests.get(api_url_v3, auth=auth, headers=headers, timeout=20)

            if resp.status_code == 401:
                raise PermissionError(
                    "Lỗi xác thực Jira (401 Unauthorized):\n"
                    f"• Email đang dùng: '{self.email}'\n"
                    "• Vui lòng kiểm tra lại JIRA_EMAIL và JIRA_API_TOKEN trong file .env.\n"
                    "• Lưu ý: JIRA_API_TOKEN phải được tạo từ https://id.atlassian.com/manage-profile/security/api-tokens (Không dùng mật khẩu đăng nhập cá nhân)."
                )
            elif resp.status_code == 403:
                raise PermissionError(
                    f"Lỗi phân quyền Jira (403 Forbidden):\n"
                    f"Tài khoản '{self.email}' không có quyền truy cập vào project hoặc ticket '{issue_key}' trên {self.server_url}."
                )
            elif resp.status_code == 404:
                # Phân tích body response từ Jira
                err_detail = ""
                try:
                    err_json = resp.json()
                    err_msgs = err_json.get("errorMessages", [])
                    if err_msgs:
                        err_detail = f"\nChi tiết từ Jira: {'; '.join(err_msgs)}"
                except Exception:
                    pass

                raise FileNotFoundError(
                    f"Jira trả về lỗi 404 Not Found cho ticket '{issue_key}' trên server '{self.server_url}'.{err_detail}\n"
                    f"📌 NGUYÊN NHÂN THƯỜNG GẶP TRÊN JIRA CLOUD:\n"
                    f"1. Tài khoản '{self.email}' chưa được cấp quyền xem Project chứa ticket '{issue_key}' (Jira Cloud bảo mật bằng cách trả về 404 thay vì 403 khi chưa có quyền).\n"
                    f"2. JIRA_API_TOKEN trong .env bị sai, hết hạn hoặc tạo từ tài khoản Atlassian khác.\n"
                    f"3. Mã ticket '{issue_key}' bị gõ sai hoặc chưa tồn tại."
                )
            
            resp.raise_for_status()
            data = resp.json()
            return self._parse_issue_payload(data, issue_key)
            
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Không thể kết nối đến Jira Server ({self.server_url}): {str(e)}")

    def _parse_issue_payload(self, data: Dict[str, Any], issue_key: str) -> Dict[str, Any]:
        fields = data.get("fields", {})
        rendered = data.get("renderedFields", {})
        names = data.get("names", {})

        summary = fields.get("summary", "")
        issue_type = fields.get("issuetype", {}).get("name", "Story")
        status = fields.get("status", {}).get("name", "Open")
        priority = fields.get("priority", {}).get("name", "Medium")
        
        components = [c.get("name") for c in fields.get("components", [])]
        labels = fields.get("labels", [])
        
        # 1. Trích xuất Description (Hỗ trợ cả ADF, Markdown và Rendered HTML)
        raw_desc = fields.get("description")
        description_text = ""
        if isinstance(raw_desc, dict) and raw_desc.get("type") == "doc":
            description_text = parse_adf_to_markdown(raw_desc)
        elif rendered.get("description"):
            description_text = re.sub(r'<br\s*/?>', '\n', rendered["description"])
            description_text = re.sub(r'</p>', '\n\n', description_text)
            description_text = re.sub(r'<[^>]+>', '', description_text)
        elif raw_desc:
            description_text = str(raw_desc)

        # 2. Quét các Custom Fields tìm Acceptance Criteria
        custom_ac_text = []
        for field_id, field_val in fields.items():
            if not field_id.startswith("customfield_") or not field_val:
                continue
            field_name = names.get(field_id, "").lower()
            if any(k in field_name for k in ["acceptance", "tiêu chí", "ac", "criteria", "uac"]):
                if isinstance(field_val, dict) and field_val.get("type") == "doc":
                    custom_ac_text.append(f"### {names.get(field_id, 'Acceptance Criteria')}:\n{parse_adf_to_markdown(field_val)}")
                else:
                    custom_ac_text.append(f"### {names.get(field_id, 'Acceptance Criteria')}:\n{str(field_val)}")

        # 3. Trích xuất Sub-tasks nếu có
        subtasks_text = []
        for st in fields.get("subtasks", []):
            st_key = st.get("key")
            st_summary = st.get("fields", {}).get("summary", "")
            st_status = st.get("fields", {}).get("status", {}).get("name", "")
            subtasks_text.append(f"- [{st_key}] {st_summary} (Status: {st_status})")

        # 4. Tạo nội dung Requirement hoàn chỉnh
        full_markdown_parts = [
            f"# [{issue_key}] {summary}",
            f"- **Issue Type:** {issue_type}",
            f"- **Status:** {status}",
            f"- **Priority:** {priority}",
            f"- **Components:** {', '.join(components) if components else 'N/A'}",
            f"- **Labels:** {', '.join(labels) if labels else 'N/A'}",
            f"- **Jira Link:** {self.server_url}/browse/{issue_key}",
            "\n## 1. Mô tả User Story (Description)",
            description_text.strip() or "Không có mô tả chi tiết."
        ]

        if custom_ac_text:
            full_markdown_parts.append("\n## 2. Acceptance Criteria (Custom Fields)")
            full_markdown_parts.extend(custom_ac_text)

        if subtasks_text:
            full_markdown_parts.append("\n## 3. Danh sách Sub-tasks")
            full_markdown_parts.extend(subtasks_text)

        formatted_requirement = "\n\n".join(full_markdown_parts)

        return {
            "key": issue_key,
            "summary": summary,
            "issue_type": issue_type,
            "status": status,
            "priority": priority,
            "jira_url": f"{self.server_url}/browse/{issue_key}",
            "formatted_requirement": formatted_requirement
        }

    def export_test_cases_to_xray_json(
        self,
        test_cases: list,
        project_key: Optional[str] = None,
        test_plan_key: Optional[str] = None
    ) -> str:
        """
        Xuất danh sách Test Case ra định dạng Xray Test JSON chuẩn để import vào Xray Test Management.
        """
        xray_payload = []
        for tc in test_cases:
            steps_list = []
            # Bóc tách từng bước trong steps
            raw_steps = tc.steps.split("\n")
            current_step = ""
            for line in raw_steps:
                if re.match(r"^\s*\d+[\.\)]", line) and current_step:
                    steps_list.append({"action": current_step.strip(), "data": tc.test_data, "result": ""})
                    current_step = line
                else:
                    current_step += ("\n" + line if current_step else line)
            if current_step:
                steps_list.append({"action": current_step.strip(), "data": tc.test_data, "result": tc.expected_result})

            tc_item = {
                "testType": "Manual",
                "fields": {
                    "summary": f"[{tc.testcase_id}] {tc.title}",
                    "description": f"**Preconditions:**\n{tc.preconditions}\n\n**Test Data:**\n```json\n{tc.test_data}\n```\n\n**Note / Trace:**\n{tc.note}",
                    "priority": {"name": tc.priority if tc.priority in ["Critical", "High", "Medium", "Low"] else "Medium"}
                },
                "steps": steps_list if steps_list else [{"action": tc.steps, "data": tc.test_data, "result": tc.expected_result}]
            }
            if project_key:
                tc_item["fields"]["project"] = {"key": project_key}
            xray_payload.append(tc_item)

        return json.dumps(xray_payload, ensure_ascii=False, indent=2)

    def export_test_cases_to_jira_csv(
        self,
        test_cases: list,
        output_path: str,
        issue_type: str = "Test"
    ) -> str:
        """
        Xuất danh sách Test Case ra file CSV chuẩn Jira/Xray ready-to-import.
        """
        import csv
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        headers = ["Issue Type", "Summary", "Description", "Priority", "Preconditions", "Manual Test Steps (Action)", "Manual Test Steps (Data)", "Manual Test Steps (Expected Result)", "Labels"]
        
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for tc in test_cases:
                writer.writerow([
                    issue_type,
                    f"[{tc.testcase_id}] {tc.title}",
                    f"Group: {tc.group_feature} > {tc.group_functional}\nNote: {tc.note}",
                    tc.priority,
                    tc.preconditions,
                    tc.steps,
                    tc.test_data,
                    tc.expected_result,
                    "QA-Agentic-Workflow"
                ])
        return output_path
