import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Optional, List, Dict
import requests
from dotenv import load_dotenv
from src.utils.file_parsers import extract_input_content, merge_multiple_sources, is_safe_local_file
from src.core.guardrail import validate_requirement_input, get_help_guide
from src.agents.requirement_analyst import analyze_requirements
from src.agents.scenario_designer import design_test_scenarios
from src.agents.testcase_generator import generate_test_cases
from src.agents.reviewer import review_and_lint_test_suite, gate_failure_reasons
from src.utils.excel_exporter import export_test_cases_to_excel
load_dotenv()

# Bộ nhớ ngữ cảnh theo luồng hội thoại (Thread-Context Memory):
# Khi Agent phải dừng lại hỏi làm rõ (Clarification Gate), nội dung tài liệu đã gộp tại thời điểm
# đó được ghi nhớ theo key của luồng hội thoại. Khi User trả lời trong thread (hoặc nhắn tiếp trong
# DM), câu trả lời được GỘP vào ĐÚNG tài liệu/ticket gốc thay vì bị xử lý như 1 yêu cầu rời rạc mới
# (khắc phục bug "hỏi xong là quên mất ticket ban đầu").
_pending_thread_context: Dict[str, str] = {}
_pending_thread_lock = threading.Lock()


def _get_pending_context(key: str) -> Optional[str]:
    with _pending_thread_lock:
        return _pending_thread_context.get(key)


def _set_pending_context(key: str, content: str):
    with _pending_thread_lock:
        _pending_thread_context[key] = content


def _clear_pending_context(key: str):
    with _pending_thread_lock:
        _pending_thread_context.pop(key, None)



def download_slack_file(url_private: str, token: str, filename: str) -> str:
    """Tải file đính kèm từ Slack về thư mục tạm"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url_private, headers=headers, timeout=30)
    response.raise_for_status()
    
    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(response.content)
        return tmp.name


def render_progress_text(steps_status: List[str]) -> str:
    """Tạo văn bản hiển thị tiến trình trực quan theo thời gian thực"""
    lines = ["🚀 *Tiến Trình Thực Thi QA Agentic Workflow (ISTQB & Banking RBT):*"]
    lines.extend(steps_status)
    return "\n".join(lines)


def run_workflow_in_background(client, channel_id: str, thread_ts: str, raw_sources: List[str], context_key: Optional[str] = None):
    """Thực thi QA Agentic Workflow và cập nhật trực tiếp tiến trình theo thời gian thực lên Slack.

    `raw_sources`: các nguồn tài liệu thô (Jira key/link, đường dẫn file tạm vừa tải về, hoặc raw text)
    sẽ được gộp thành 1 tài liệu phân tích duy nhất (giống cơ chế `-e/--extra` của CLI). `context_key`
    (nếu có) ghi nhớ ngữ cảnh của luồng hội thoại này để lần User trả lời làm rõ tiếp theo được nối
    tiếp đúng vào ticket/tài liệu gốc.
    """
    progress_ts = None
    try:
        # 1. Trích xuất & gộp nội dung input (tự động dọn file tạm ngay sau khi trích xuất)
        resolved_sources = []
        for src in raw_sources:
            if src and is_safe_local_file(src) and os.path.exists(src):
                file_content, _ = extract_input_content(src)
                resolved_sources.append(file_content)
                try:
                    os.remove(src)
                except Exception:
                    pass
            elif src:
                resolved_sources.append(src)
        content, _, _ = merge_multiple_sources(resolved_sources)
        if not content or len(content.strip()) < 5:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="⚠️ Nội dung yêu cầu quá ngắn hoặc không hợp lệ. Vui lòng cung cấp nội dung User Story/PRD hoặc đính kèm file (.docx, .pdf, .md)!"
            )
            return

        # 2. Tạo tin nhắn Progress ban đầu
        steps = [
            "• ⏳ *[1/5] Node 1: Đang phân tích nghiệp vụ & Bóc tách rủi ro (RBT Matrix)...*",
            "• ⚪ [2/5] Node 2: Thiết kế kịch bản kiểm thử (BVA, Idempotency, QĐ 2345)",
            "• ⚪ [3/5] Node 3: Sinh Test Case chi tiết theo Template 14 cột",
            "• ⚪ [4/5] Node 4: QA Quality Gate Reviewer & Banking Linter",
            "• ⚪ [5/5] Node 5: Xuất Excel chuẩn Template có Logo & Biểu đồ"
        ]
        res = client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=render_progress_text(steps)
        )
        progress_ts = res.get("ts")

        # --- NODE 1: Requirement Analysis ---
        analysis = analyze_requirements(raw_content=content)
        
        # Kiểm tra nếu Requirement có điểm chưa rõ bắt buộc phải hỏi lại User
        if analysis.needs_user_clarification and analysis.clarification_questions:
            steps[0] = f"• ❓ *[1/5] Node 1: Tạm dừng - Cần làm rõ {len(analysis.clarification_questions)} điểm trong yêu cầu*"
            client.chat_update(channel=channel_id, ts=progress_ts, text=render_progress_text(steps))
            
            q_mrkdwn = "\n".join([f"*{i}.* {q}" for i, q in enumerate(analysis.clarification_questions, 1)])
            clarification_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"❓ CÂU HỎI LÀM RÕ YÊU CẦU: {analysis.feature_name[:100]}",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "⚠️ *Yêu cầu hiện tại có một số điểm chưa rõ ràng hoặc thiếu thông tin quan trọng.*\n"
                            "Để đảm bảo đúng bản chất nghiệp vụ và *tránh suy diễn sai tính năng*, vui lòng bổ sung thông tin cho các câu hỏi sau:\n\n"
                            f"{q_mrkdwn}\n\n"
                            "_💡 Sau khi làm rõ, bạn có thể tag bot kèm thông tin bổ sung để tiến hành sinh Test Case hoàn chỉnh._"
                        )
                    }
                }
            ]
            if context_key:
                _set_pending_context(context_key, content)
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                blocks=clarification_blocks,
                text=f"Cần làm rõ {len(analysis.clarification_questions)} điểm trong yêu cầu trước khi viết test case!"
            )
            return

        steps[0] = f"• ✅ *[1/5] Node 1: Phân tích xong* (Bóc tách {len(analysis.acceptance_criteria)} ACs, {len(analysis.product_risks)} Rủi ro RBT - _{analysis.banking_domain}_)"
        steps[1] = "• ⏳ *[2/5] Node 2: Đang thiết kế ma trận kịch bản kiểm thử (ISTQB & Banking)...*"
        client.chat_update(channel=channel_id, ts=progress_ts, text=render_progress_text(steps))
        # --- NODE 2: Scenario Design ---
        scenarios = design_test_scenarios(analysis=analysis)
        
        steps[1] = f"• ✅ *[2/5] Node 2: Thiết kế xong* (Thiết kế {len(scenarios)} kịch bản: BVA, Idempotency, QĐ 2345)"
        steps[2] = "• ⏳ *[3/5] Node 3: Đang sinh Test Case chi tiết 14 cột với Payload Core Banking...*"
        client.chat_update(channel=channel_id, ts=progress_ts, text=render_progress_text(steps))

        # --- NODE 3: Test Case Generation & Feedback Loop ---
        max_iterations = 4
        current_iter = 0
        review_result = None
        test_cases = []
        pending_clarifications: List[str] = []

        while current_iter < max_iterations:
            gen = generate_test_cases(
                analysis=analysis,
                scenarios=scenarios,
                review_feedback=review_result
            )
            test_cases = gen.test_cases
            pending_clarifications = gen.clarification_questions
            
            steps[2] = f"• ✅ *[3/5] Node 3: Đã sinh {len(test_cases)} Test Cases chi tiết* (Lần {current_iter + 1})"
            steps[3] = f"• ⏳ *[4/5] Node 4: QA Quality Gate & Linter đang thẩm định chất lượng (Vòng {current_iter + 1}/{max_iterations})...*"
            client.chat_update(channel=channel_id, ts=progress_ts, text=render_progress_text(steps))

            # --- NODE 4: Reviewer & Linter ---
            review_result = review_and_lint_test_suite(
                analysis=analysis,
                test_cases=test_cases,
                raw_content=content
            )

            if review_result.passed:
                steps[3] = f"• ✅ *[4/5] Node 4: QA Quality Gate: ĐẠT {review_result.score}/100 Điểm (PASSED ✅)*"
                break
            else:
                current_iter += 1
                if current_iter < max_iterations:
                    steps[3] = f"• 🔄 *[4/5] Node 4: Điểm {review_result.score}/100 (< 95) -> Tự động sinh bổ sung & sửa {len(review_result.issues)} lỗi (Vòng {current_iter + 1}/{max_iterations})...*"
                    client.chat_update(channel=channel_id, ts=progress_ts, text=render_progress_text(steps))
                else:
                    steps[3] = f"• ⚠️ *[4/5] Node 4: QA Gate hoàn tất ({review_result.score}/100 Điểm)*"
        steps[4] = "• ⏳ *[5/5] Node 5: Đang xuất file Excel chuẩn Template có Logo & Biểu đồ...*"
        client.chat_update(channel=channel_id, ts=progress_ts, text=render_progress_text(steps))

        # --- NODE 5: Excel Export ---
        output_excel_path = export_test_cases_to_excel(
            analysis=analysis,
            test_cases=test_cases,
            template_path="EF_TestCases.xlsx",
            pending_clarifications=pending_clarifications
        )

        steps[4] = f"• ✅ *[5/5] Node 5: Đã xuất file Excel thành công!*"
        final_summary_text = (
            f"🎉 *HOÀN THÀNH TOÀN BỘ QUY TRÌNH KIỂM THỬ CHO: {analysis.feature_name}*\n" +
            "\n".join(steps)
        )
        client.chat_update(channel=channel_id, ts=progress_ts, text=final_summary_text)

        if pending_clarifications:
            if context_key:
                _set_pending_context(context_key, content)
            q_mrkdwn = "\n".join([f"*{i}.* {q}" for i, q in enumerate(pending_clarifications, 1)])
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=(
                    f"⚠️ *Còn {len(pending_clarifications)} điểm chưa có dữ kiện (API sample / message) - Agent KHÔNG tự bịa:*\n"
                    f"{q_mrkdwn}\n\n"
                    "_Các test case bị ảnh hưởng đã tô vàng & ghi chú PENDING CLARIFICATION. "
                    "Tag bot kèm thông tin bổ sung để sinh lại đầy đủ - Bot vẫn nhớ ticket/tài liệu gốc, không cần nhắc lại._"
                )
            )
        elif context_key:
            _clear_pending_context(context_key)

        # 4. Tạo tin nhắn tổng hợp Block Kit
        if review_result and review_result.passed:
            review_status_text = "ĐẠT CHUẨN (PASSED ✅)"
        elif review_result:
            review_status_text = f"CHƯA ĐẠT ({'; '.join(gate_failure_reasons(review_result))}) ⚠️"
        else:
            review_status_text = "N/A"
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📋 BÁO CÁO TEST SUITE: {analysis.feature_name[:100]}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*🏛️ Phân hệ Banking:* {analysis.banking_domain}"},
                    {"type": "mrkdwn", "text": f"*📱 Ứng dụng:* {analysis.app_name} (v{analysis.version})"},
                    {"type": "mrkdwn", "text": f"*📋 Tiêu chí AC:* {len(analysis.acceptance_criteria)} tiêu chí"},
                    {"type": "mrkdwn", "text": f"*🧪 Số lượng Test Cases:* {len(test_cases)} cases"},
                    {"type": "mrkdwn", "text": f"*🛡️ QA Gate Score:* {review_result.score if review_result else 'N/A'}/100"},
                    {"type": "mrkdwn", "text": f"*⚡ Trạng thái Review:* {review_status_text}"}
                ]
            }
        ]
        # Thêm ma trận rủi ro RBT
        if analysis and analysis.product_risks:
            rbt_text = "*🎯 Ma trận Rủi ro RBT (Product Risks Matrix):*\n"
            for rsk in analysis.product_risks[:4]:
                rbt_text += f"• *[{rsk.risk_id}]* `{rsk.risk_level}` (Score: {rsk.risk_score}) - {rsk.risk_title}\n"
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": rbt_text}
            })

        # Gửi summary blocks vào thread
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            blocks=blocks,
            text=f"Đã tạo thành công {len(test_cases)} test cases!"
        )

        # 5. Upload file Excel trực tiếp vào Slack thread
        if output_excel_path and os.path.exists(output_excel_path):
            filename = Path(output_excel_path).name
            client.files_upload_v2(
                channel=channel_id,
                thread_ts=thread_ts,
                file=output_excel_path,
                filename=filename,
                title=f"Testsuite_{analysis.feature_name[:40]}.xlsx",
                initial_comment="📥 *Tải file Test Suite Excel hoàn chỉnh tại đây (Có Logo, Biểu đồ & Công thức liên kết):*"
            )

    except Exception as e:
        err_msg = f"❌ *Lỗi trong quá trình thực thi Workflow:* `{str(e)}`"
        if progress_ts:
            client.chat_update(channel=channel_id, ts=progress_ts, text=err_msg)
        else:
            client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=err_msg)


def create_slack_app():
    """Khởi tạo Slack Bolt App và đăng ký các events"""
    from slack_bolt import App
    
    token = os.getenv("SLACK_BOT_TOKEN")
    signing_secret = os.getenv("SLACK_SIGNING_SECRET")
    
    if not token:
        raise ValueError("Chưa cấu hình SLACK_BOT_TOKEN trong file .env!")
        
    app = App(token=token, signing_secret=signing_secret)

    @app.event("app_mention")
    def handle_app_mentions(body, say, client):
        """Xử lý khi người dùng tag @Bot trong bất kỳ channel nào"""
        event = body.get("event", {})
        channel_id = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")
        text = event.get("text", "")
        files = event.get("files", [])
        cleaned_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        # Ghi nhớ luồng hội thoại theo (channel, thread gốc): nếu còn câu hỏi làm rõ đang treo,
        # tin nhắn này được nối vào ĐÚNG ticket/tài liệu gốc thay vì bị coi là yêu cầu hoàn toàn mới.
        context_key = f"{channel_id}:{thread_ts}"
        existing_context = _get_pending_context(context_key)

        file_path = None
        if files:
            first_file = files[0]
            file_url = first_file.get("url_private_download") or first_file.get("url_private")
            file_name = first_file.get("name", "document.txt")
            say(channel=channel_id, thread_ts=thread_ts, text=f"📥 Đã nhận file đính kèm: *{file_name}*. Đang bắt đầu xử lý...")
            file_path = download_slack_file(file_url, token, file_name)
            new_source = file_path
        else:
            if existing_context is None:
                # Guardrail chống spam / câu hỏi vô nghĩa chỉ áp cho yêu cầu MỚI, không áp cho câu trả lời làm rõ.
                is_valid, reason, guide = validate_requirement_input(cleaned_text)
                if not is_valid:
                    say(channel=channel_id, thread_ts=thread_ts, text=f"⚠️ *{reason}*\n\n{guide}")
                    return
                say(channel=channel_id, thread_ts=thread_ts, text="🧠 Đã nhận User Story / Mã Jira. Đang khởi chạy QA Agents...")
            else:
                say(channel=channel_id, thread_ts=thread_ts, text="🧠 Đã nhận thông tin làm rõ. Đang gộp vào ticket/tài liệu gốc và phân tích lại...")
            new_source = cleaned_text

        raw_sources = ([existing_context] if existing_context else []) + [new_source]

        threading.Thread(
            target=run_workflow_in_background,
            args=(client, channel_id, thread_ts, raw_sources, context_key)
        ).start()

    @app.event("message")
    def handle_direct_messages(body, say, client):
        """Xử lý khi người dùng nhắn tin trực tiếp (DM) cho Bot"""
        event = body.get("event", {})
        if event.get("channel_type") != "im" or event.get("bot_id"):
            return

        channel_id = event.get("channel")
        thread_ts = event.get("ts")
        text = event.get("text", "")
        files = event.get("files", [])

        # 1 kênh DM = 1 hội thoại liên tục (User không cần bấm "Reply in thread"), nên context được
        # ghi nhớ theo cả kênh DM, không đòi hỏi khớp đúng thread_ts như trong channel.
        context_key = f"dm:{channel_id}"
        existing_context = _get_pending_context(context_key)

        file_path = None
        if files:
            first_file = files[0]
            file_url = first_file.get("url_private_download") or first_file.get("url_private")
            file_name = first_file.get("name", "document.txt")
            say(channel=channel_id, thread_ts=thread_ts, text=f"📥 Đã nhận file đính kèm: *{file_name}*. Đang phân tích...")
            file_path = download_slack_file(file_url, token, file_name)
            new_source = file_path
        else:
            if existing_context is None:
                # Guardrail chống spam / câu hỏi vô nghĩa chỉ áp cho yêu cầu MỚI, không áp cho câu trả lời làm rõ.
                is_valid, reason, guide = validate_requirement_input(text)
                if not is_valid:
                    say(channel=channel_id, thread_ts=thread_ts, text=f"⚠️ *{reason}*\n\n{guide}")
                    return
                say(channel=channel_id, thread_ts=thread_ts, text="🧠 Đang phân tích yêu cầu của bạn...")
            else:
                say(channel=channel_id, thread_ts=thread_ts, text="🧠 Đã nhận thông tin làm rõ. Đang gộp vào ticket/tài liệu gốc và phân tích lại...")
            new_source = text

        raw_sources = ([existing_context] if existing_context else []) + [new_source]

        threading.Thread(
            target=run_workflow_in_background,
            args=(client, channel_id, thread_ts, raw_sources, context_key)
        ).start()

    @app.command("/qa-testcase")
    def handle_slash_command(ack, body, client):
        """Xử lý Slash Command: /qa-testcase <User story text>"""
        ack()
        channel_id = body.get("channel_id")
        text = body.get("text", "")
        user_id = body.get("user_id")

        # Kiểm tra Guardrail
        is_valid, reason, guide = validate_requirement_input(text)
        if not is_valid:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=f"⚠️ *{reason}*\n\n{guide}"
            )
            return

        res = client.chat_postMessage(
            channel=channel_id,
            text=f"🚀 <@{user_id}> vừa yêu cầu sinh Test Suite bằng lệnh `/qa-testcase`..."
        )
        thread_ts = res.get("ts")

        threading.Thread(
            target=run_workflow_in_background,
            args=(client, channel_id, thread_ts, [text], f"{channel_id}:{thread_ts}")
        ).start()

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
    print("🤖 Bot đã sẵn sàng nhận tin nhắn qua Mentions, Direct Messages và lệnh /qa-testcase!")
    handler.start()
