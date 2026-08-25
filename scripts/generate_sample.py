#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
from src.core.models import (
    RequirementAnalysis,
    AcceptanceCriterion,
    ProductRisk,
    TestCase
)
from src.utils.excel_exporter import export_test_cases_to_excel

def main():
    # 1. Khởi tạo Requirement Analysis & RBT Matrix chi tiết
    analysis = RequirementAnalysis(
        feature_name="VWCBT-4102: Chuyển tiền nhanh Napas 24/7 & Xác thực Sinh trắc học",
        app_name="Branch Portal / Mobile Banking",
        version="UAT 3.1.0",
        jira_or_doc_link="https://galaxyfinx.atlassian.net/browse/VWCBT-4102",
        business_overview="Hệ thống cung cấp API và giao diện cho phép khách hàng cá nhân thực hiện chuyển tiền nhanh liên ngân hàng qua kênh Napas 24/7 (bằng Số tài khoản hoặc Số thẻ) với các quy tắc xác thực hạn mức giao dịch trong ngày và xác thực OTP/Sinh trắc học theo QĐ 2345/QĐ-NHNN.",
        acceptance_criteria=[
            AcceptanceCriterion(
                ac_id="AC-01",
                title="Chuyển tiền Napas 24/7 qua Số tài khoản",
                description="Tài khoản Active, đủ số dư, ngân hàng thụ hưởng liên kết Napas, phí bậc thang.",
                business_rules=["Miễn phí < 1M VND", "Phí 2,200 VND cho >= 1M VND"],
                risk_level="High"
            ),
            AcceptanceCriterion(
                ac_id="AC-02",
                title="Kiểm tra Hạn mức Giao dịch",
                description="Tối thiểu 10k/lần, tối đa 500M/lần, tối đa tích lũy 1.5 tỷ/ngày.",
                business_rules=["Báo lỗi ERR_MIN_AMOUNT khi < 10k", "Báo lỗi ERR_MAX_PER_TXN khi > 500M", "Báo lỗi ERR_DAILY_LIMIT_EXCEEDED khi vượt 1.5B/ngày"],
                risk_level="Critical"
            ),
            AcceptanceCriterion(
                ac_id="AC-03",
                title="Xác thực Sinh trắc học (QĐ 2345/QĐ-NHNN)",
                description="Bắt buộc FaceID khi > 10M/lần hoặc tích lũy ngày >= 20M.",
                business_rules=["Khóa 60 phút khi sai FaceID 3 lần liên tiếp"],
                risk_level="High"
            ),
            AcceptanceCriterion(
                ac_id="AC-04",
                title="Xử lý Ngoại lệ Gateway Timeout & Idempotency",
                description="Xử lý khi Napas Gateway 504 Timeout, đảm bảo Idempotency không trừ tiền 2 lần.",
                business_rules=["Trạng thái PENDING_RECONCILIATION khi timeout", "Khóa trùng lặp qua idempotency_key"],
                risk_level="Critical"
            )
        ],
        product_risks=[
            ProductRisk(
                risk_id="RSK-01",
                risk_title="Tính sai phí giao dịch bậc thang hoặc trừ tiền không đúng",
                risk_category="Financial Risk",
                likelihood=3,
                impact=5,
                risk_score=15,
                risk_level="High",
                linked_ac_id="AC-01",
                mitigation_test_focus="Kiểm thử chính xác điểm ranh giới 1,000,000 VND và số dư tài khoản sau khi trừ phí."
            ),
            ProductRisk(
                risk_id="RSK-02",
                risk_title="Lọt giao dịch vượt hạn mức ngày 1.5 tỷ hoặc dưới 10,000 VND",
                risk_category="Data Integrity & Boundary Risk",
                likelihood=4,
                impact=4,
                risk_score=16,
                risk_level="Critical",
                linked_ac_id="AC-02",
                mitigation_test_focus="Full Boundary Value Analysis (9,999đ, 10,000đ, 500M, 500,000,001đ, 1.5 tỷ)."
            ),
            ProductRisk(
                risk_id="RSK-03",
                risk_title="Bypass sinh trắc học cho giao dịch trên 10 triệu VND",
                risk_category="Security & Authentication Risk",
                likelihood=3,
                impact=5,
                risk_score=15,
                risk_level="High",
                linked_ac_id="AC-03",
                mitigation_test_focus="Kiểm tra bắt buộc biometric token và cơ chế khóa sau 3 lần sai."
            ),
            ProductRisk(
                risk_id="RSK-04",
                risk_title="Trừ tiền 2 lần khi Napas Timeout và Client retry",
                risk_category="Integration & Timeout Risk",
                likelihood=4,
                impact=5,
                risk_score=20,
                risk_level="Critical",
                linked_ac_id="AC-04",
                mitigation_test_focus="Kiểm thử Idempotency key và trạng thái đối soát PENDING_RECONCILIATION."
            )
        ]
    )

    # 2. Tạo 15 Test Cases chi tiết bao phủ 100% AC và RBT Risks
    test_cases = [
        # --- Nhóm 1: AC-01 Happy Path & Phí bậc thang ---
        TestCase(
            testcase_id="TC 01",
            group_feature="1. Chuyển tiền Napas 24/7 qua Số tài khoản (AC-01 - Risk: High)",
            group_functional="1.1. Luồng giao dịch thành công & Tính phí bậc thang (Tiered Fees)",
            title="Chuyển tiền thành công dưới 1,000,000 VND (Hệ thống miễn phí giao dịch)",
            preconditions="Tài khoản nguồn 1012345678 Active, số dư khả dụng >= 500,000 VND. Ngân hàng thụ hưởng Vietcombank (VCB) liên kết Napas.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 500,000 VND\n2. Kiểm tra HTTP Status Code và Response Body\n3. Kiểm tra biến động số dư tài khoản nguồn",
            expected_result="- HTTP Status: 200 OK\n- Response Body:\n{\n  \"status\": \"SUCCESS\",\n  \"trace_no\": \"NP20260824001\",\n  \"amount\": 500000,\n  \"fee\": 0,\n  \"total_debit\": 500000\n}\n- Số dư tài khoản nguồn bị trừ chính xác 500,000 VND.",
            actual_result="",
            test_data="{\n  \"from_account\": \"1012345678\",\n  \"to_account\": \"9988776655\",\n  \"to_bank_code\": \"VCB\",\n  \"amount\": 500000,\n  \"remark\": \"Chuyen tien tieu dung\"\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="High",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-01 | RSK-01 (Financial Risk)"
        ),
        TestCase(
            testcase_id="TC 02",
            group_feature="1. Chuyển tiền Napas 24/7 qua Số tài khoản (AC-01 - Risk: High)",
            group_functional="1.1. Luồng giao dịch thành công & Tính phí bậc thang (Tiered Fees)",
            title="Chuyển tiền thành công từ 1,000,000 VND trở lên (Thu phí 2,200 VND)",
            preconditions="Tài khoản nguồn 1012345678 Active, số dư khả dụng >= 2,002,200 VND.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 2,000,000 VND\n2. Kiểm tra phí giao dịch và tổng tiền trừ tài khoản",
            expected_result="- HTTP Status: 200 OK\n- Response Body:\n{\n  \"status\": \"SUCCESS\",\n  \"amount\": 2000000,\n  \"fee\": 2200,\n  \"total_debit\": 2002200\n}\n- Số dư bị trừ: 2,002,200 VND (Gốc 2M + Phí 2.2k).",
            actual_result="",
            test_data="{\n  \"from_account\": \"1012345678\",\n  \"to_account\": \"9988776655\",\n  \"to_bank_code\": \"VCB\",\n  \"amount\": 2000000\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="High",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-01 | RSK-01 (Financial Risk)"
        ),
        TestCase(
            testcase_id="TC 03",
            group_feature="1. Chuyển tiền Napas 24/7 qua Số tài khoản (AC-01 - Risk: High)",
            group_functional="1.2. Kiểm tra Ngân hàng thụ hưởng và Số tài khoản",
            title="Chuyển tiền tới Ngân hàng không nằm trong liên minh Napas 24/7",
            preconditions="Tài khoản nguồn hợp lệ. Mã ngân hàng thụ hưởng không hỗ trợ Napas (vd: FOREIGN_BANK).",
            steps="1. Gửi request POST /v1/transfer/napas247 với to_bank_code = 'FOREIGN_BANK'\n2. Kiểm tra mã lỗi trả về",
            expected_result="- HTTP Status: 400 Bad Request\n- Error Code: ERR_BANK_NOT_SUPPORTED\n- Error Message: 'Ngân hàng thụ hưởng không hỗ trợ kênh chuyển tiền nhanh 24/7.'",
            actual_result="",
            test_data="{\n  \"from_account\": \"1012345678\",\n  \"to_account\": \"11223344\",\n  \"to_bank_code\": \"FOREIGN_BANK\",\n  \"amount\": 100000\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="Medium",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-01"
        ),
        TestCase(
            testcase_id="TC 04",
            group_feature="1. Chuyển tiền Napas 24/7 qua Số tài khoản (AC-01 - Risk: High)",
            group_functional="1.2. Kiểm tra Ngân hàng thụ hưởng và Số tài khoản",
            title="Tài khoản nguồn không đủ số dư để thanh toán tiền chuyển và phí",
            preconditions="Tài khoản nguồn Active, số dư khả dụng = 100,000 VND.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 100,000 VND (Yêu cầu phí 2,200 VND, tổng 102,200 VND)\n2. Kiểm tra thông báo lỗi",
            expected_result="- HTTP Status: 400 Bad Request\n- Error Code: ERR_INSUFFICIENT_BALANCE\n- Error Message: 'Số dư khả dụng không đủ để thực hiện giao dịch và thanh toán phí.'",
            actual_result="",
            test_data="{\n  \"from_account\": \"1012345678\",\n  \"to_account\": \"9988776655\",\n  \"to_bank_code\": \"VCB\",\n  \"amount\": 1000000\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="High",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-01"
        ),

        # --- Nhóm 2: AC-02 Hạn mức BVA (Risk: Critical) ---
        TestCase(
            testcase_id="TC 05",
            group_feature="2. Kiểm tra Hạn mức Giao dịch (AC-02 - Risk: Critical - BVA)",
            group_functional="2.1. Phân tích giá trị biên Hạn mức trên 1 lần giao dịch (Min/Max Boundary)",
            title="[BVA-Min-1] Chuyển tiền dưới hạn mức tối thiểu (9,999 VND)",
            preconditions="Tài khoản nguồn Active, số dư khả dụng >= 100,000 VND.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 9999\n2. Kiểm tra mã lỗi và thông báo",
            expected_result="- HTTP Status: 400 Bad Request\n- Error Code: ERR_MIN_AMOUNT\n- Error Message: 'Số tiền chuyển tối thiểu là 10,000 VND'",
            actual_result="",
            test_data="{\n  \"amount\": 9999\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="Critical",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-02 | RSK-02 (Boundary Risk)"
        ),
        TestCase(
            testcase_id="TC 06",
            group_feature="2. Kiểm tra Hạn mức Giao dịch (AC-02 - Risk: Critical - BVA)",
            group_functional="2.1. Phân tích giá trị biên Hạn mức trên 1 lần giao dịch (Min/Max Boundary)",
            title="[BVA-Min] Chuyển tiền tại đúng giá trị biên tối thiểu (10,000 VND)",
            preconditions="Tài khoản nguồn Active, số dư khả dụng >= 10,000 VND.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 10000\n2. Kiểm tra giao dịch thành công",
            expected_result="- HTTP Status: 200 OK\n- Trạng thái giao dịch: SUCCESS\n- Số tiền trừ: 10,000 VND (Miễn phí).",
            actual_result="",
            test_data="{\n  \"amount\": 10000\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="High",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-02 | RSK-02 (Boundary Risk)"
        ),
        TestCase(
            testcase_id="TC 07",
            group_feature="2. Kiểm tra Hạn mức Giao dịch (AC-02 - Risk: Critical - BVA)",
            group_functional="2.1. Phân tích giá trị biên Hạn mức trên 1 lần giao dịch (Min/Max Boundary)",
            title="[BVA-Max] Chuyển tiền tại đúng giá trị biên tối đa 1 lần (500,000,000 VND)",
            preconditions="Tài khoản nguồn đủ số dư >= 500,002,200 VND. Đã xác thực sinh trắc học hợp lệ.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 500000000\n2. Kiểm tra giao dịch thành công",
            expected_result="- HTTP Status: 200 OK\n- Trạng thái giao dịch: SUCCESS\n- Phí: 2,200 VND\n- Tổng trừ: 500,002,200 VND.",
            actual_result="",
            test_data="{\n  \"amount\": 500000000,\n  \"biometric_token\": \"BIO_VALID_TOKEN_999\"\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="Critical",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-02 | RSK-02 (Boundary Risk)"
        ),
        TestCase(
            testcase_id="TC 08",
            group_feature="2. Kiểm tra Hạn mức Giao dịch (AC-02 - Risk: Critical - BVA)",
            group_functional="2.1. Phân tích giá trị biên Hạn mức trên 1 lần giao dịch (Min/Max Boundary)",
            title="[BVA-Max+1] Chuyển tiền vượt hạn mức tối đa 1 lần (500,000,001 VND)",
            preconditions="Tài khoản nguồn Active, số dư lớn.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 500000001\n2. Kiểm tra mã lỗi từ chối",
            expected_result="- HTTP Status: 400 Bad Request\n- Error Code: ERR_MAX_PER_TXN\n- Error Message: 'Số tiền vượt quá hạn mức tối đa 500,000,000 VND / lần.'",
            actual_result="",
            test_data="{\n  \"amount\": 500000001\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="Critical",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-02 | RSK-02 (Boundary Risk)"
        ),
        TestCase(
            testcase_id="TC 09",
            group_feature="2. Kiểm tra Hạn mức Giao dịch (AC-02 - Risk: Critical - BVA)",
            group_functional="2.2. Kiểm tra Hạn mức tích lũy trong ngày (Daily Cumulative Limit)",
            title="Giao dịch chạm đúng hạn mức tích lũy tối đa trong ngày (1.5 tỷ VND)",
            preconditions="Trong ngày đã chuyển tích lũy 1,000,000,000 VND. Số dư tài khoản khả dụng >= 500,002,200 VND.",
            steps="1. Thực hiện chuyển tiếp 500,000,000 VND (Tổng tích lũy đạt 1.5 tỷ VND)\n2. Kiểm tra kết quả giao dịch",
            expected_result="- HTTP Status: 200 OK\n- Giao dịch thành công\n- Tổng tích lũy trong ngày cập nhật: 1,500,000,000 VND.",
            actual_result="",
            test_data="{\n  \"amount\": 500000000\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="High",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-02"
        ),
        TestCase(
            testcase_id="TC 10",
            group_feature="2. Kiểm tra Hạn mức Giao dịch (AC-02 - Risk: Critical - BVA)",
            group_functional="2.2. Kiểm tra Hạn mức tích lũy trong ngày (Daily Cumulative Limit)",
            title="Giao dịch làm tổng tích lũy trong ngày vượt quá 1.5 tỷ VND",
            preconditions="Trong ngày đã chuyển tích lũy 1,490,000,000 VND.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 20,000,000 VND (Tổng tích lũy thành 1.51 tỷ)\n2. Kiểm tra mã lỗi từ chối",
            expected_result="- HTTP Status: 400 Bad Request\n- Error Code: ERR_DAILY_LIMIT_EXCEEDED\n- Error Message: 'Quý khách đã vượt quá hạn mức chuyển tiền trong ngày (1,500,000,000 VND).'",
            actual_result="",
            test_data="{\n  \"amount\": 20000000\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="Critical",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-02 | RSK-02"
        ),

        # --- Nhóm 3: AC-03 Sinh trắc học QĐ 2345 (Risk: High) ---
        TestCase(
            testcase_id="TC 11",
            group_feature="3. Xác thực Sinh trắc học theo QĐ 2345/QĐ-NHNN (AC-03 - Risk: High)",
            group_functional="3.1. Bắt buộc sinh trắc học theo ngưỡng giá trị giao dịch (>10M / lần)",
            title="Chuyển tiền > 10,000,000 VND không kèm Biometric Token (Bắt buộc Face matching)",
            preconditions="Tài khoản nguồn Active, số dư đủ. Request không truyền `biometric_token`.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 10,000,001 VND\n2. Kiểm tra phản hồi yêu cầu xác thực khuôn mặt",
            expected_result="- HTTP Status: 403 Forbidden\n- Error Code: ERR_BIOMETRIC_REQUIRED\n- Error Message: 'Giao dịch trên 10,000,000 VND bắt buộc xác thực sinh trắc học khuôn mặt.'",
            actual_result="",
            test_data="{\n  \"amount\": 10000001\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="High",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-03 | RSK-03 (Security Risk)"
        ),
        TestCase(
            testcase_id="TC 12",
            group_feature="3. Xác thực Sinh trắc học theo QĐ 2345/QĐ-NHNN (AC-03 - Risk: High)",
            group_functional="3.1. Bắt buộc sinh trắc học theo ngưỡng giá trị giao dịch (>10M / lần)",
            title="Chuyển tiền > 10,000,000 VND kèm Biometric Token hợp lệ (Thành công)",
            preconditions="Tài khoản nguồn Active. Đã Face matching thành công và nhận `biometric_token`.",
            steps="1. Gửi request POST /v1/transfer/napas247 kèm `biometric_token`\n2. Kiểm tra giao dịch thành công",
            expected_result="- HTTP Status: 200 OK\n- Status: SUCCESS\n- Biometric verified: TRUE.",
            actual_result="",
            test_data="{\n  \"amount\": 15000000,\n  \"biometric_token\": \"BIO_FACE_MATCH_PASS_01\"\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="High",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-03 | RSK-03"
        ),
        TestCase(
            testcase_id="TC 13",
            group_feature="3. Xác thực Sinh trắc học theo QĐ 2345/QĐ-NHNN (AC-03 - Risk: High)",
            group_functional="3.2. Xử lý vi phạm và Khóa xác thực (Security Lockout)",
            title="Xác thực sinh trắc học thất bại liên tiếp 3 lần (Khóa tính năng chuyển tiền 60 phút)",
            preconditions="Tài khoản nguồn Active. Đã xác thực Face matching sai 2 lần trước đó.",
            steps="1. Gửi request xác thực sinh trắc học lần thứ 3 với token không khớp\n2. Kiểm tra mã lỗi khóa tài khoản và thời gian chờ",
            expected_result="- HTTP Status: 403 Forbidden\n- Error Code: ERR_BIOMETRIC_LOCKED\n- Error Message: 'Quý khách đã xác thực không thành công 3 lần. Tính năng chuyển tiền tạm khóa trong 60 phút.'\n- Cờ `transfer_locked_until` được gán = NOW + 60 phút.",
            actual_result="",
            test_data="{\n  \"amount\": 12000000,\n  \"biometric_token\": \"BIO_FACE_FAIL_3\"\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="Critical",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-03 | RSK-03 (Security Lockout)"
        ),

        # --- Nhóm 4: AC-04 Timeout & Idempotency (Risk: Critical) ---
        TestCase(
            testcase_id="TC 14",
            group_feature="4. Xử lý Ngoại lệ Gateway Timeout & Tính Idempotency (AC-04 - Risk: Critical)",
            group_functional="4.1. Gateway Timeout và Chuyển trạng thái Đối soát",
            title="Napas Gateway phản hồi HTTP 504 Gateway Timeout (Chuyển PENDING_RECONCILIATION)",
            preconditions="Mock Napas Gateway giả lập timeout 30s.",
            steps="1. Gửi request POST /v1/transfer/napas247\n2. Napas Gateway trả về 504 Timeout sau 30s\n3. Kiểm tra trạng thái giao dịch trên Core Banking",
            expected_result="- HTTP Status: 202 Accepted\n- Response Body:\n{\n  \"status\": \"PENDING_RECONCILIATION\",\n  \"message\": \"Giao dịch đang được xử lý đối soát, vui lòng không chuyển lại.\"\n}\n- Tiền chưa bị trừ vĩnh viễn, được phong tỏa tạm thời (HOLD).",
            actual_result="",
            test_data="{\n  \"amount\": 5000000,\n  \"idempotency_key\": \"IDEMP_TIMEOUT_001\"\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="Critical",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-04 | RSK-04 (Timeout Risk)"
        ),
        TestCase(
            testcase_id="TC 15",
            group_feature="4. Xử lý Ngoại lệ Gateway Timeout & Tính Idempotency (AC-04 - Risk: Critical)",
            group_functional="4.2. Kiểm tra tính Idempotency khi Client Retry request",
            title="Gửi 2 request trùng `idempotency_key` trong cùng 1 tích tắc (Tránh trừ tiền 2 lần)",
            preconditions="Tài khoản nguồn có 10,000,000 VND. Gửi 2 request đồng thời qua đa luồng (Concurrency test).",
            steps="1. Gửi đồng thời 2 request POST /v1/transfer/napas247 với cùng 1 `idempotency_key`\n2. Kiểm tra phản hồi của Request 1 và Request 2\n3. Kiểm tra số dư tài khoản nguồn",
            expected_result="- Request 1: HTTP 200 OK (Giao dịch thành công)\n- Request 2: HTTP 409 Conflict hoặc trả về kết quả đã cached của Request 1\n- Tài khoản nguồn CHỈ BỊ TRỪ TIỀN 1 LẦN DUY NHẤT (5,002,200 VND).",
            actual_result="",
            test_data="{\n  \"amount\": 5000000,\n  \"idempotency_key\": \"DUPLICATE_KEY_TEST_2026\"\n}",
            creator="QA Agent (RBT)",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="Critical",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-04 | RSK-04 (Idempotency Risk)"
        )
    ]

    # 3. Xuất ra file Excel mới trong thư mục outputs/
    sample_output_path = "outputs/Testsuite_VWCBT-4102_Napas_247_Transfer.xlsx"
    out_file = export_test_cases_to_excel(
        analysis=analysis,
        test_cases=test_cases,
        template_path="EF_TestCases.xlsx",
        output_path=sample_output_path,
        target_sheet_name="Napas_247_Transfer"
    )

    print(f"Generated sample file successfully: {out_file}")
    print("File size:", os.path.getsize(out_file), "bytes")

if __name__ == "__main__":
    main()
