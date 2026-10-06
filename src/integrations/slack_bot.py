import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Optional, List, Dict
import requests
from dotenv import load_dotenv
from src.core.guardrail import validate_requirement_input
from src.core.session import QASession, SessionOptions, SessionStore, UserTurn, remote_upload_dir
from src.core.conversation import SuiteOutcome, run_session
from src.agents.reviewer import gate_failure_reasons
from src.integrations.jira_connector import extract_jira_key
load_dotenv()

# Phiên hội thoại theo luồng Slack: `channel:thread_ts` (channel / slash command), `dm:channel` (DM),
# `channel:thread_ts:group_key` (từng nhóm batch). Phiên sống suốt hội thoại: User trả lời câu hỏi,
# gửi thêm tài liệu hoặc feedback BẤT CỨ LÚC NÀO (kể cả khi Agent đang chạy) -> bộ test case được cập
# nhật ngay trong thread/DM đó, không cần tag lại bot.
_sessions = SessionStore()

# Các nhóm (group_key) của mỗi thread chạy `--batch`, dùng để định tuyến tin nhắn tiếp theo trong thread
# về ĐÚNG phiên của nhóm/ticket tương ứng.
_batch_threads: Dict[str, List[str]] = {}
_batch_lock = threading.Lock()

NEW_SESSION_ACK = "🧠 Đã nhận yêu cầu. Đang khởi chạy QA Agents..."
QUEUED_ACK = "📝 Đã nhận! Agent đang xử lý — thông tin này sẽ được áp dụng ngay ở bước kế tiếp, không cần gửi lại."
THREAD_HINT = "💬 _Trả lời câu hỏi, gửi thêm tài liệu hoặc feedback ngay trong thread này (không cần tag bot) — bộ test case sẽ được cập nhật tại chỗ._"
DM_HINT = "💬 _Trả lời câu hỏi, gửi thêm tài liệu hoặc feedback ngay trong DM này — bộ test case sẽ được cập nhật tại chỗ._"


def _register_batch_group(thread_key: str, group_key: str) -> None:
    with _batch_lock:
        groups = _batch_threads.setdefault(thread_key, [])
        if group_key not in groups:
            groups.append(group_key)


def _get_batch_groups(thread_key: str) -> List[str]:
    with _batch_lock:
        return list(_batch_threads.get(thread_key, []))


def download_slack_file(url_private: str, token: str, filename: str) -> str:
    """Tải file đính kèm từ Slack về thư mục upload dành riêng cho kênh từ xa."""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url_private, headers=headers, timeout=30)
    response.raise_for_status()
    
    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=remote_upload_dir()) as tmp:
        tmp.write(response.content)
        return tmp.name


def render_progress_text(steps_status: List[str], group_label: Optional[str] = None) -> str:
    """Tạo văn bản hiển thị tiến trình trực quan theo thời gian thực"""
    lines = ["🚀 *Tiến Trình Thực Thi QA Agentic Workflow (ISTQB & Banking RBT):*"]
    if group_label:
        lines.insert(0, f"🔹 *Nhóm: {group_label}*")
    lines.extend(steps_status)
    return "\n".join(lines)


class SlackReporter:
    """Hiển thị tiến trình / câu hỏi / kết quả của một phiên lên đúng thread (hoặc DM) Slack."""

    def __init__(self, client, channel_id: str, thread_ts: Optional[str], group_label: Optional[str] = None, hint: str = THREAD_HINT):
        self.client = client
        self.channel_id = channel_id
        self.thread_ts = thread_ts
        self.group_label = group_label
        self.prefix = f"[{group_label}] " if group_label else ""
        self.hint = hint
        self._progress_ts: Optional[str] = None
        self._progress_lines: List[str] = []

    def _post(self, **kwargs) -> dict:
        if self.thread_ts:
            kwargs["thread_ts"] = self.thread_ts
        return self.client.chat_postMessage(channel=self.channel_id, **kwargs)

    def _update_progress(self, text: str) -> None:
        if self._progress_ts:
            self.client.chat_update(channel=self.channel_id, ts=self._progress_ts, text=text)
        else:
            self._progress_ts = self._post(text=text).get("ts")

    def progress(self, lines: List[str], new: bool = False) -> None:
        if new:
            self._progress_ts = None
        self._progress_lines = list(lines)
        self._update_progress(render_progress_text(lines, self.group_label))

    def notify(self, text: str) -> None:
        self._post(text=f"{self.prefix}{text}")

    def ask(self, session: QASession, questions: List[str], stage: str) -> None:
        feature = session.analysis.feature_name if session.analysis else "Yêu cầu"
        q_mrkdwn = "\n".join(f"*{i}.* {q}" for i, q in enumerate(questions, 1))
        self._post(
            blocks=[
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"❓ CÂU HỎI LÀM RÕ YÊU CẦU: {self.prefix}{feature[:100]}", "emoji": True},
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "⚠️ *Yêu cầu hiện tại có điểm chưa rõ ràng hoặc thiếu thông tin quan trọng.*\n"
                            "Để đúng bản chất nghiệp vụ và *không suy diễn sai tính năng*, vui lòng trả lời các câu hỏi sau "
                            "(trả lời tự do, có thể trả lời từng phần hoặc gộp nhiều câu):\n\n"
                            f"{q_mrkdwn}\n\n{self.hint}"
                        ),
                    },
                },
            ],
            text=f"{self.prefix}Cần làm rõ {len(questions)} điểm trong yêu cầu trước khi viết test case!",
        )

    def deliver(self, session: QASession, outcome: SuiteOutcome) -> None:
        analysis = session.analysis
        review = session.review_result
        test_cases = session.test_cases
        title = "♻️ ĐÃ CẬP NHẬT BỘ TEST CASE" if outcome.updated else "🎉 HOÀN THÀNH TOÀN BỘ QUY TRÌNH KIỂM THỬ"
        self._update_progress(f"{title} {self.prefix}CHO: {analysis.feature_name}\n" + "\n".join(self._progress_lines))

        if review and review.passed:
            review_status_text = "ĐẠT CHUẨN (PASSED ✅)"
        elif review:
            review_status_text = f"CHƯA ĐẠT ({'; '.join(gate_failure_reasons(review))}) ⚠️"
        else:
            review_status_text = "N/A"
        header = "♻️ CẬP NHẬT TEST SUITE" if outcome.updated else "📋 BÁO CÁO TEST SUITE"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"{header}: {self.prefix}{analysis.feature_name[:100]}", "emoji": True}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*🏛️ Phân hệ:* {analysis.banking_domain}"},
                    {"type": "mrkdwn", "text": f"*📱 Ứng dụng:* {analysis.app_name} (v{analysis.version})"},
                    {"type": "mrkdwn", "text": f"*📋 Tiêu chí AC:* {len(analysis.acceptance_criteria)} tiêu chí"},
                    {"type": "mrkdwn", "text": f"*🧪 Số lượng Test Cases:* {len(test_cases)} cases"},
                    {"type": "mrkdwn", "text": f"*🛡️ QA Gate Score:* {review.score if review else 'N/A'}/100"},
                    {"type": "mrkdwn", "text": f"*⚡ Trạng thái Review:* {review_status_text}"},
                ],
            },
        ]
        if outcome.updated:
            changes = outcome.change_summary or ["Không có thay đổi nào được áp dụng."]
            changes_text = "*✏️ Thay đổi trong lượt cập nhật này (mã TC trước khi đánh số lại):*\n" + "\n".join(f"• {c}" for c in changes[:15])
            if len(changes) > 15:
                changes_text += f"\n_... và {len(changes) - 15} thay đổi khác._"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": changes_text}})
        elif analysis.product_risks:
            rbt_text = "*🎯 Ma trận Rủi ro RBT (Product Risks Matrix):*\n"
            for rsk in analysis.product_risks[:4]:
                rbt_text += f"• *[{rsk.risk_id}]* `{rsk.risk_level}` (Score: {rsk.risk_score}) - {rsk.risk_title}\n"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": rbt_text}})

        # Chi tiết issue Critical/Major CHƯA xử lý sau khi hết vòng lặp sửa lỗi -> User biết cần sửa/hỏi gì.
        if review and not review.passed and review.issues:
            unresolved = [i for i in review.issues if i.severity in ("Critical", "Major")] or review.issues
            issues_text = f"*🚫 Chi tiết {len(unresolved)} Issue Chưa Xử Lý (Quality Gate CHƯA ĐẠT sau {outcome.iterations} vòng lặp):*\n"
            for iss in unresolved[:6]:
                sev_emoji = "🔴" if iss.severity == "Critical" else "🟠"
                issues_text += (
                    f"{sev_emoji} *[{iss.target_tc_id or 'All Suite'}]* `{iss.severity}` - {iss.issue_type}\n"
                    f"   _{iss.description[:200]}_\n"
                    f"   -> *Đề xuất sửa:* {iss.suggested_fix[:200]}\n"
                )
            if len(unresolved) > 6:
                issues_text += f"_... và {len(unresolved) - 6} issue khác, xem đầy đủ trong file Excel đính kèm._\n"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": issues_text}})
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": self.hint}]})

        self._post(blocks=blocks, text=f"{self.prefix}{'Đã cập nhật' if outcome.updated else 'Đã tạo thành công'} {len(test_cases)} test cases!")

        if session.open_questions:
            q_mrkdwn = "\n".join(f"*{i}.* {q}" for i, q in enumerate(session.open_questions, 1))
            self._post(
                text=(
                    f"⚠️ *{self.prefix}Còn {len(session.open_questions)} điểm chưa có dữ kiện — Agent KHÔNG tự bịa:*\n"
                    f"{q_mrkdwn}\n\n"
                    "_Các test case bị ảnh hưởng đã tô vàng & ghi chú PENDING CLARIFICATION._\n"
                    f"{self.hint}"
                )
            )

        output_path = session.output_excel_path
        if output_path and os.path.exists(output_path):
            upload_kwargs = {"thread_ts": self.thread_ts} if self.thread_ts else {}
            self.client.files_upload_v2(
                channel=self.channel_id,
                file=output_path,
                filename=Path(output_path).name,
                title=f"Testsuite_{analysis.feature_name[:40]}.xlsx",
                initial_comment=f"📥 *{self.prefix}{'File Test Suite đã cập nhật' if outcome.updated else 'Tải file Test Suite Excel hoàn chỉnh tại đây'}:*",
                **upload_kwargs,
            )

    def fail(self, session: QASession, text: str) -> None:
        err_msg = f"❌ *{self.prefix}Lỗi:* {text}"
        if self._progress_ts:
            self.client.chat_update(channel=self.channel_id, ts=self._progress_ts, text=err_msg)
        else:
            self._post(text=err_msg)


def dispatch_turn(
    client,
    channel_id: str,
    thread_ts: Optional[str],
    session_key: str,
    turn: UserTurn,
    group_label: Optional[str] = None,
    hint: str = THREAD_HINT,
    background: bool = True,
) -> bool:
    """Đưa lượt nhắn vào phiên `session_key`. Nếu phiên chưa có worker -> khởi chạy worker (thread nền
    hoặc đồng bộ khi `background=False`) và trả về True; nếu worker đang chạy -> lượt nhắn được hấp thụ
    ở điểm kiểm tra kế tiếp, trả về False."""
    session = _sessions.get_or_create(session_key, SessionOptions(local_file_root=remote_upload_dir()))
    if not session.submit(turn):
        return False
    reporter = SlackReporter(client, channel_id, thread_ts, group_label=group_label, hint=hint)
    if background:
        threading.Thread(target=run_session, args=(session, reporter), daemon=True).start()
    else:
        run_session(session, reporter)
    return True


def resolve_batch_reply_group_key(group_keys: List[str], reply_text: str, awaiting_keys: List[str]) -> Optional[str]:
    """Xác định CHÍNH XÁC nhóm batch nào trong thread mà tin nhắn tiếp theo thuộc về.

    Ưu tiên khớp mã Jira được nhắc lại trong tin nhắn (không phân biệt hoa/thường). Không nhắc mã nào:
    thread chỉ có 1 nhóm -> nhóm đó; hoặc chỉ ĐÚNG 1 nhóm đang chờ User trả lời câu hỏi -> nhóm đó
    (trường hợp phổ biến nhất). Còn lại trả về None để caller yêu cầu User nhắc lại mã ticket - TUYỆT ĐỐI
    không đoán bừa và gộp nhầm sang nhóm khác.
    """
    found_key = extract_jira_key(reply_text)
    if found_key:
        for gk in group_keys:
            if gk.lower() == found_key.lower():
                return gk
    if len(group_keys) == 1:
        return group_keys[0]
    if len(awaiting_keys) == 1:
        return awaiting_keys[0]
    return None


def parse_batch_groups(text: str) -> List[List[str]]:
    """Phân tích cú pháp Batch Mode gốc Slack (`--batch`).

    Quy ước bắt buộc (khác quy ước argv của CLI `run.py --batch`, vì shell quoting để giữ 1 token
    liền mạch qua khoảng trắng không áp dụng được cho text phẳng của Slack - ghi chú bổ sung tiếng
    Việt tự nhiên thường xuyên chứa CẢ khoảng trắng LẪN dấu phẩy):

    1. Tin nhắn phải BẮT ĐẦU bằng token `--batch` (không phân biệt hoa/thường) để kích hoạt Batch
       Mode. Không có token này -> KHÔNG phải batch, trả về [] để caller giữ nguyên 100% hành vi
       yêu cầu đơn hiện tại.
    2. Sau khi bỏ `--batch`, tách phần còn lại theo DẤU XUỐNG DÒNG (`\\n`, phím Shift+Enter): mỗi
       dòng = 1 nhóm/ticket ĐỘC LẬP, sinh ra 1 bộ Test Suite riêng.
    3. Trong CÙNG 1 dòng, tách theo ` | ` (dấu pipe, đã trim khoảng trắng 2 bên) thành danh sách
       nguồn CỦA RIÊNG dòng đó (mã/ticket + các ghi chú bổ sung của CHÍNH nó). Chọn pipe thay vì dấu
       phẩy vì văn xuôi tiếng Việt gần như không bao giờ chứa ký tự `|`, giữ việc gán tài liệu bổ
       sung -> đúng ticket hoàn toàn tường minh, xác định 100% từ cấu trúc tin nhắn, không suy đoán.
    """
    stripped = (text or "").strip()
    if not stripped or not stripped.lower().startswith("--batch"):
        return []

    remainder = stripped[len("--batch"):]
    groups: List[List[str]] = []
    for line in remainder.split("\n"):
        line = line.strip()
        if not line:
            continue
        sources = [part.strip() for part in line.split(" | ")]
        sources = [s for s in sources if s]
        if sources:
            groups.append(sources)
    return groups


def run_batch_workflow_in_background(client, channel_id: str, thread_ts: str, groups: List[List[str]]):
    """Chạy TUẦN TỰ (thứ tự & cách ly quan trọng hơn tốc độ; tiến trình của nhiều nhóm chạy đồng thời
    trong cùng 1 thread sẽ chèn lẫn lộn) từng nhóm nguồn ĐỘC LẬP (mỗi dòng sau `--batch`), mỗi nhóm là
    1 phiên hội thoại riêng `channel:thread_ts:group_key`, rồi đăng 1 tin nhắn tổng kết TOÀN BỘ batch."""
    thread_key = f"{channel_id}:{thread_ts}"
    total = len(groups)
    per_group: List[tuple] = []

    for idx, group_sources in enumerate(groups, 1):
        group_key = next((k for k in (extract_jira_key(s) for s in group_sources) if k), None) or f"g{idx}"
        client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=f"📦 *Đang xử lý Nhóm {idx}/{total}: {group_key}*")
        session_key = f"{thread_key}:{group_key}"
        _register_batch_group(thread_key, group_key)
        dispatch_turn(
            client, channel_id, thread_ts, session_key, UserTurn(sources=list(group_sources)),
            group_label=group_key, background=False,
        )
        per_group.append((group_key, _sessions.get(session_key)))

    success_count = 0
    summary_lines = []
    for group_key, session in per_group:
        feature = session.analysis.feature_name if session and session.analysis else "N/A"
        if session is None or session.error:
            status = f"❌ Lỗi: {session.error if session else 'không khởi tạo được phiên'}"
        elif not session.suite_ready:
            status = "⏳ Chờ làm rõ (đã hỏi User trong thread)"
        else:
            success_count += 1
            status = f"✅ {session.output_excel_path or 'Hoàn thành'}"
            if session.open_questions:
                status += f" (còn {len(session.open_questions)} câu hỏi mở)"
        review = session.review_result if session else None
        gate = f"{'PASSED' if review.passed else 'FAILED'} ({review.score}/100)" if review else "N/A"
        summary_lines.append(f"*{group_key}* — _{feature}_\n   Kết quả: {status}\n   QA Gate: {gate}")

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"📦 TỔNG KẾT BATCH ({total} Nhóm/Ticket)", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n\n".join(summary_lines)}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": (
            "💬 _Trả lời / gửi tài liệu / feedback ngay trong thread này cho từng ticket — nhắc mã ticket ở đầu "
            "tin nhắn khi batch có nhiều ticket._"
        )}]},
    ]
    client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        blocks=blocks,
        text=f"✅ {success_count}/{total} nhóm hoàn thành thành công.",
    )


BATCH_FILES_UNSUPPORTED = (
    "⚠️ *Batch mode (`--batch`) hiện chưa hỗ trợ đính kèm file* (không thể xác định "
    "file đính kèm thuộc về nhóm/ticket nào một cách tường minh).\n"
    "Vui lòng gửi ticket đó riêng lẻ (không dùng `--batch`), hoặc đưa nội dung bổ sung "
    "vào dạng text ngay trên dòng của ticket đó theo cú pháp `TICKET | ghi chú bổ sung`."
)


def create_slack_app():
    """Khởi tạo Slack Bolt App và đăng ký các events"""
    from slack_bolt import App
    
    token = os.getenv("SLACK_BOT_TOKEN")
    signing_secret = os.getenv("SLACK_SIGNING_SECRET")
    
    if not token:
        raise ValueError("Chưa cấu hình SLACK_BOT_TOKEN trong file .env!")
        
    app = App(token=token, signing_secret=signing_secret)

    def _say(say, channel_id: str, thread_ts: Optional[str], text: str) -> None:
        if thread_ts:
            say(channel=channel_id, thread_ts=thread_ts, text=text)
        else:
            say(channel=channel_id, text=text)

    def _download_all(say, channel_id: str, thread_ts: Optional[str], files: List[dict]) -> List[str]:
        if not files:
            return []
        names = [f.get("name", "document.txt") for f in files]
        _say(say, channel_id, thread_ts, f"📥 Đã nhận {len(files)} file đính kèm: *{', '.join(names)}*")
        return [
            download_slack_file(f.get("url_private_download") or f.get("url_private"), token, name)
            for f, name in zip(files, names)
        ]

    def _start_batch(say, client, channel_id: str, thread_ts: str, batch_groups: List[List[str]], files: List[dict]) -> None:
        if files:
            _say(say, channel_id, thread_ts, BATCH_FILES_UNSUPPORTED)
            return
        _say(say, channel_id, thread_ts, f"📦 Đã nhận yêu cầu Batch với *{len(batch_groups)} nhóm*. Đang xử lý tuần tự từng nhóm...")
        threading.Thread(target=run_batch_workflow_in_background, args=(client, channel_id, thread_ts, batch_groups), daemon=True).start()

    def _route_batch_reply(say, client, channel_id: str, thread_ts: str, text: str, files: List[dict]) -> bool:
        """Tin nhắn trong thread `--batch` -> định tuyến về phiên của đúng nhóm. False nếu không phải thread batch."""
        thread_key = f"{channel_id}:{thread_ts}"
        group_keys = _get_batch_groups(thread_key)
        if not group_keys:
            return False
        awaiting = [g for g in group_keys if (s := _sessions.get(f"{thread_key}:{g}")) and s.awaiting_user]
        matched = resolve_batch_reply_group_key(group_keys, text, awaiting)
        if matched is None:
            _say(say, channel_id, thread_ts, f"⚠️ *Thread này có nhiều ticket:* {', '.join(group_keys)}. Vui lòng nhắc lại mã ticket ở đầu tin nhắn.")
            return True
        sources = _download_all(say, channel_id, thread_ts, files)
        started = dispatch_turn(
            client, channel_id, thread_ts, f"{thread_key}:{matched}",
            UserTurn(text=text, sources=sources, delete_sources_after_read=True), group_label=matched,
        )
        _say(say, channel_id, thread_ts, f"🧠 Đã nhận cho *{matched}*. Đang xử lý..." if started else f"[{matched}] {QUEUED_ACK}")
        return True

    def _converse(say, client, channel_id: str, reply_thread_ts: Optional[str], session_key: str, text: str, files: List[dict], hint: str) -> None:
        """Lượt nhắn trong 1 hội thoại: yêu cầu mới (qua Guardrail) hoặc tiếp nối phiên đang có."""
        session = _sessions.get(session_key)
        is_new = session is None or not session.documents
        if is_new and not files:
            # Guardrail chống spam / câu vô nghĩa chỉ áp cho yêu cầu MỚI, không áp cho câu trả lời/feedback.
            is_valid, reason, guide = validate_requirement_input(text)
            if not is_valid:
                _say(say, channel_id, reply_thread_ts, f"⚠️ *{reason}*\n\n{guide}")
                return
        sources = _download_all(say, channel_id, reply_thread_ts, files)
        if is_new:
            _say(say, channel_id, reply_thread_ts, NEW_SESSION_ACK)
        started = dispatch_turn(
            client, channel_id, reply_thread_ts, session_key,
            UserTurn(text=text, sources=sources, delete_sources_after_read=True), hint=hint,
        )
        if not is_new and not started:
            _say(say, channel_id, reply_thread_ts, QUEUED_ACK)

    @app.event("app_mention")
    def handle_app_mentions(body, say, client):
        """Tag @Bot trong channel: bắt đầu yêu cầu mới, hoặc tiếp nối phiên của thread hiện tại."""
        event = body.get("event", {})
        channel_id = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")
        cleaned_text = re.sub(r"<@[A-Z0-9]+>", "", event.get("text", "")).strip()
        files = event.get("files", [])

        batch_groups = parse_batch_groups(cleaned_text)
        if batch_groups:
            _start_batch(say, client, channel_id, thread_ts, batch_groups, files)
            return
        if _route_batch_reply(say, client, channel_id, thread_ts, cleaned_text, files):
            return
        _converse(say, client, channel_id, thread_ts, f"{channel_id}:{thread_ts}", cleaned_text, files, THREAD_HINT)

    @app.event("message")
    def handle_messages(body, say, client, context):
        """DM với Bot (1 kênh DM = 1 hội thoại liên tục) và tin nhắn trả lời KHÔNG tag bot trong thread
        channel đang có phiên (cần event `message.channels`/`message.groups` + scope `*:history`)."""
        event = body.get("event", {})
        if event.get("bot_id") or event.get("subtype") not in (None, "file_share"):
            return
        channel_id = event.get("channel")
        text = event.get("text", "") or ""
        files = event.get("files", [])

        if event.get("channel_type") == "im":
            root_ts = event.get("thread_ts") or event.get("ts")
            batch_groups = parse_batch_groups(text)
            if batch_groups:
                _start_batch(say, client, channel_id, root_ts, batch_groups, files)
                return
            if event.get("thread_ts") and _route_batch_reply(say, client, channel_id, root_ts, text, files):
                return
            _converse(say, client, channel_id, None, f"dm:{channel_id}", text, files, DM_HINT)
            return

        thread_ts = event.get("thread_ts")
        bot_user_id = (context or {}).get("bot_user_id")
        if not thread_ts or (bot_user_id and f"<@{bot_user_id}>" in text):
            return  # Tin nhắn ngoài thread, hoặc có tag bot (đã xử lý bởi app_mention).
        if _route_batch_reply(say, client, channel_id, thread_ts, text, files):
            return
        session = _sessions.get(f"{channel_id}:{thread_ts}")
        if session is None or not session.documents:
            return  # Thread không có phiên QA nào -> bot không xen vào hội thoại của người khác.
        _converse(say, client, channel_id, thread_ts, f"{channel_id}:{thread_ts}", text, files, THREAD_HINT)

    @app.command("/qa-testcase")
    def handle_slash_command(ack, body, client):
        """Xử lý Slash Command: /qa-testcase <User story text>"""
        ack()
        channel_id = body.get("channel_id")
        text = body.get("text", "")
        user_id = body.get("user_id")
        files = body.get("files", [])

        batch_groups = parse_batch_groups(text)
        if batch_groups:
            if files:
                client.chat_postEphemeral(channel=channel_id, user=user_id, text=BATCH_FILES_UNSUPPORTED)
                return
            res = client.chat_postMessage(
                channel=channel_id,
                text=f"📦 <@{user_id}> vừa yêu cầu sinh Batch Test Suite (*{len(batch_groups)} nhóm*) bằng lệnh `/qa-testcase --batch`..."
            )
            thread_ts = res.get("ts")
            threading.Thread(target=run_batch_workflow_in_background, args=(client, channel_id, thread_ts, batch_groups), daemon=True).start()
            return

        is_valid, reason, guide = validate_requirement_input(text)
        if not is_valid:
            client.chat_postEphemeral(channel=channel_id, user=user_id, text=f"⚠️ *{reason}*\n\n{guide}")
            return

        res = client.chat_postMessage(
            channel=channel_id,
            text=f"🚀 <@{user_id}> vừa yêu cầu sinh Test Suite bằng lệnh `/qa-testcase`...\n{THREAD_HINT}"
        )
        thread_ts = res.get("ts")
        dispatch_turn(client, channel_id, thread_ts, f"{channel_id}:{thread_ts}", UserTurn(text=text))

    return app


def start_slack_bot():
    """Khởi động Slack Bot qua Socket Mode"""
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    
    slack_app_token = os.getenv("SLACK_APP_TOKEN")
    slack_bot_token = os.getenv("SLACK_BOT_TOKEN")
    
    if not slack_app_token or not slack_bot_token:
        print("❌ LỖI: Chưa cấu hình SLACK_BOT_TOKEN hoặc SLACK_APP_TOKEN trong file .env!")
        print("Vui lòng xem hướng dẫn thiết lập Slack App trong tài liệu.")
        return
        
    print("⚡ Khởi động QA Agentic Slack Bot (Socket Mode)...")
    app = create_slack_app()
    handler = SocketModeHandler(app, slack_app_token)
    print("🤖 Bot đã sẵn sàng: Mentions, trả lời trong thread (không cần tag), Direct Messages và lệnh /qa-testcase!")
    handler.start()
