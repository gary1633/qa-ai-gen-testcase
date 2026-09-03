# 🏦 QA Agentic Workflow — Toàn Bộ Sơ Đồ Kiến Trúc & Luồng Xử Lý (System Architecture Charts)

Tài liệu này tổng hợp toàn bộ các sơ đồ kiến trúc (Mermaid Diagrams), luồng tương tác đa Agent, cơ chế kiểm soát chất lượng (Quality Gate) và ma trận truy vết (Traceability) của hệ thống **QA Agentic Workflow**.

---

## 1. Kiến Trúc Tổng Quan Hệ Thống (End-to-End Multi-Agent Architecture)

Hệ thống hoạt động theo mô hình **LangGraph Multi-Agent Pipeline có Feedback Loop & Self-Correction Quality Gate**:

```mermaid
flowchart TD
    subgraph Input_Layer ["Input Layer - Đa Nguồn Tài Liệu"]
        I1["Jira Cloud / Server Ticket (REST API)"]
        I2["File Tài Liệu Nội Bộ (Word .docx / PDF / Markdown)"]
        I3["OpenAPI / Swagger Spec (JSON / YAML)"]
        I4["Interactive Text Prompt"]
    end

    subgraph Agentic_Pipeline ["Agentic Pipeline - LangGraph StateGraph"]
        A1["Node 1: Requirement Analyst Agent<br/>(Bộ 8 Kỹ năng & Ma trận RBT)"]
        A2["Node 2: Test Scenario Designer Agent<br/>(9 Kỹ thuật ISTQB & Business Flow, Pairwise Matrix)"]
        A3["Node 3: Test Case Generator Agent<br/>(Paced Batching & Field-Level Checklist)"]
        A4["Node 4: QA Gatekeeper & Reviewer Agent<br/>(Bidirectional Traceability & Linter)"]
    end

    subgraph Quality_Gate_Section ["Quality Gate & Feedback Loop"]
        QG{"Quality Gate Passed?<br/>Score từ 85 trở lên và không có Critical"}
        FB["Refinement Feedback & Linter Errors"]
    end

    subgraph Output_Layer ["Output & Integration Layer"]
        O1["Excel Exporter (14 Cột, Logo, Biểu đồ động)"]
        O2["Xray Test Management (JSON Payload)"]
        O3["Jira External System Import (CSV)"]
        O4["Slack Bot 24/7 (Real-time Thread & File Upload)"]
    end

    I1 --> A1
    I2 --> A1
    I3 --> A1
    I4 --> A1

    A1 -->|Structured Specs + RBT Matrix| A2
    A2 -->|30-50+ Scenarios Matrix| A3
    A3 -->|Draft Test Cases 14 Cột| A4
    A4 --> QG

    QG -->|No - Failed Gate| FB
    FB -->|Chỉ đạo khắc phục| A3
    QG -->|Yes - Approved| O1
    QG -->|Yes - Approved| O2
    QG -->|Yes - Approved| O3
    QG -->|Yes - Approved| O4
```

---

## 2. Node 1: Bộ 8 Kỹ Năng Phân Tích Yêu Cầu (Requirement Analysis Framework)

Cơ chế bóc tách yêu cầu chuyên sâu, chống suy diễn (Anti-Hallucination) và bao phủ 100% nghiệp vụ:

```mermaid
flowchart LR
    subgraph Input_Group ["Input Requirements"]
        RAW["Raw Story / PRD / API Spec"]
    end

    subgraph Skills_Group ["Bộ 8 Kỹ Năng Phân Tích Cốt Lõi"]
        K1["1. Explicit Grounding<br/>(Confirmed Facts vs Assumptions vs Gaps)"]
        K2["2. 360° Boundary Discovery<br/>(Min/Max, Bands, Leap Year, Lifecycle)"]
        K3["3. Multi-Stakeholder Analysis<br/>(Client, Ledger, Gateway, Compliance)"]
        K4["4. Business Invariants Extraction<br/>(Double-Entry, Zero Double-Debit)"]
        K5["5. Testability & Prerequisites<br/>(Mock Napas, Mock Core, Seed Data)"]
        K6["6. 100% Traceability Mapping<br/>(Gán mã chuẩn AC-xx, BR-xx)"]
        K7["7. RBT Product Risk Matrix<br/>(Likelihood x Impact = Risk Score)"]
        K8["8. Multi-Source Cross-Reference<br/>(Mapping US + BRD/SRS + Figma + API Spec)"]
    end

    subgraph Output_Group ["Output Báo Cáo Phân Tích"]
        OUT["RequirementAnalysis Schema<br/>- Feature & Domain<br/>- Business Objectives<br/>- Acceptance Criteria List<br/>- Product Risk Matrix<br/>- Questions to Resolve"]
    end

    RAW --> K1
    RAW --> K2
    RAW --> K3
    RAW --> K4
    RAW --> K5
    RAW --> K6
    RAW --> K7
    RAW --> K8

    K1 --> OUT
    K2 --> OUT
    K3 --> OUT
    K4 --> OUT
    K5 --> OUT
    K6 --> OUT
    K7 --> OUT
    K8 --> OUT
```

---

## 3. Node 2: Thiết Kế Ma Trận Kịch Bản Đa Kỹ Thuật (9 ISTQB & Business-Flow Techniques + Pairwise Matrix)

Đảm bảo độ dày kịch bản kiểm thử đạt **30 đến 50+ Test Cases** cho mỗi tính năng:

```mermaid
flowchart TD
    REQ["Requirement Analysis & RBT Matrix"] --> SD["Node 2: Scenario Designer"]

    subgraph Techniques_Group ["Hệ Thống 9 Kỹ Thuật ISTQB & Business Flow"]
        T1["1. Equivalence Partitioning (EP)<br/>Whitelist Enum, Missing Fields, Type Mismatch"]
        T2["2. Boundary Value Analysis (BVA 2/3-Value)<br/>Min-1, Min, Max, Max+1, Overlap/Gap Bands"]
        T3["3. Decision Table & Pairwise Testing<br/>Rút gọn tổ hợp đa chiều (144 combos còn 16-20 combos)"]
        T4["4. State Transition Testing (STT)<br/>Draft -> Active -> Blocked -> Closed, Cron ngày 01"]
        T5["5. Concurrency & Idempotency<br/>Duplicate Request trong 50ms, Đua lệnh rút tiền"]
        T6["6. Error Guessing & Fault Injection<br/>Napas 504 Timeout -> Pending Recon, Rollback"]
        T7["7. Financial Calculation & Compliance<br/>Banker's Rounding, Lãi năm nhuận, QĐ 2345 (Nếu có quy định)"]
        T8["8. API Functional & RBAC Matrix<br/>Happy Path, Negative Validation, Auth 401/403, Pagination"]
        T9["9. Business Flow & End-to-End Impact<br/>Số dư/Sổ cái/Tồn kho thực tế, Hệ quả đa bên (Khách hàng/Sổ sách/Tích hợp/Pháp chế)"]
    end

    SD --> T1
    SD --> T2
    SD --> T3
    SD --> T4
    SD --> T5
    SD --> T6
    SD --> T7
    SD --> T8
    SD --> T9

    T1 --> MATRIX["High-Density Test Scenario Matrix (30 - 50+ Scenarios)<br/>Đầy đủ: Trace AC, Trace Risk, Group 14 Cột, Title có ngoặc kép"]
    T2 --> MATRIX
    T3 --> MATRIX
    T4 --> MATRIX
    T5 --> MATRIX
    T6 --> MATRIX
    T7 --> MATRIX
    T8 --> MATRIX
    T9 --> MATRIX
```

---

## 4. Node 3: Cơ Chế Sinh Test Case (Paced Batching & Field-Level Checklist)

Quy trình sinh Test Case 14 cột với cơ chế chia lô chống lỗi Rate Limit (429) và nhúng trực tiếp Body JSON:

```mermaid
flowchart TD
    SM["Danh sách 30 - 50+ Scenarios"] --> PB["Paced Batching Controller<br/>(Chia thành từng lô 8 - 10 Scenarios)"]

    subgraph Batch_Flow ["Batch Execution Flow"]
        B1["Batch 1 (Scenarios 01 - 10)"]
        W1["Sleep 2.5s (Cool-down)"]
        B2["Batch 2 (Scenarios 11 - 20)"]
        W2["Sleep 2.5s (Cool-down)"]
        B3["Batch 3 (Scenarios 21 - 30+)"]
    end

    subgraph Standard_Rules ["Quy Chuẩn Sinh Dữ Liệu Từng Test Case"]
        FC["Field-Level Validation Checklist<br/>(String, Email, Phone, Amount, DateTime, Nested Object)"]
        TD["Traceable Test Data Pattern<br/>auto_[module]_[tc_id]_[timestamp]"]
        JS["Pretty-Formatted JSON Body<br/>Nhúng trực tiếp vào Steps (Indent 2 spaces)"]
        TTL["Title chuẩn hóa có bọc ngoặc kép quanh field và value"]
    end

    PB --> B1
    B1 --> W1
    W1 --> B2
    B2 --> W2
    W2 --> B3

    B1 --> FC
    B2 --> TD
    B3 --> JS
    B3 --> TTL

    FC --> TCFULL["Draft Test Suite (14 Cột Đầy Đủ Chi Tiết)"]
    TD --> TCFULL
    JS --> TCFULL
    TTL --> TCFULL
```

---

## 5. Node 4: Cơ Chế Truy Vết 2 Chiều & Quality Gate (Bidirectional Traceability)

Hàng rào bảo vệ chất lượng kết hợp giữa Linter toán học và Semantic Review:

```mermaid
flowchart TD
    TC["Draft Test Suite (14 Cột)"] --> REV["Node 4: QA Gatekeeper & Reviewer"]
    
    subgraph Layer1_Linter ["Tầng 1: Deterministic Static Linter"]
        L1["Banned Words Check (Cấm 'verify it works', 'chờ một chút')"]
        L2["Placeholder Check (Cấm 'some data', 'dữ liệu bất kỳ')"]
        L3["Expected Result Determinism (Định lượng rõ mã HTTP, JSON, số dư)"]
        L4["Numbered Steps Check (Bắt buộc đánh số 1. 2. 3.)"]
        L5["Banking Domain Linter (Kiểm tra Idempotency & QĐ 2345)"]
    end

    subgraph Layer2_Traceability ["Tầng 2: Bidirectional Traceability & Drift Detection"]
        TR1["Forward Traceability<br/>100% AC có cả Positive & Negative Test Cases"]
        TR2["Backward Traceability<br/>100% TC map đúng AC gốc (Zero Orphan TCs)"]
        TR3["Requirement Drift Detection<br/>So khớp chéo số tiền, hạn mức, mã lỗi gốc"]
        TR4["RBT Mitigation Check<br/>Rủi ro Critical/High bắt buộc có TC trực diện"]
    end

    REV --> L1
    REV --> L2
    REV --> L3
    REV --> L4
    REV --> L5

    REV --> TR1
    REV --> TR2
    REV --> TR3
    REV --> TR4

    L1 --> CALC["Chấm điểm Tổng Hợp Quality Score (0 - 100)<br/>Trừ điểm: Critical (-15), Major (-10), Minor (-5)"]
    L2 --> CALC
    L3 --> CALC
    L4 --> CALC
    L5 --> CALC
    TR1 --> CALC
    TR2 --> CALC
    TR3 --> CALC
    TR4 --> CALC
    
    CALC --> GATE{"Quality Gate<br/>Score từ 85 trở lên và không có Critical?"}
    GATE -->|Passed| REP_PASS["Xuất Báo Cáo Traceability Matrix & Cho Phép Xuất File"]
    GATE -->|Failed| REP_FAIL["Tạo Actionable Feedback & Kích Hoạt Vòng Lặp Sửa Lỗi"]
```

---

## 6. Sơ Đồ Tích Hợp Kỹ Năng Từ Vikki Framework (.agent)

Bản đồ kế thừa các kỹ năng tuyển chọn từ `/Users/hai.vu/Documents/Finx/vikki-auto-framework/.agent`:

```mermaid
flowchart LR
    subgraph Vikki_Framework ["Vikki Framework (.agent)"]
        V1["test_data_generator<br/>(Checklist từng loại field & Traceable Data)"]
        V2["cross_module_test_plan<br/>(Thuật toán Pairwise Combinatorial)"]
        V3["generate_api_tests_from_swagger<br/>(Ma trận 7 chiều API & Security OWASP)"]
        V4["jira_integration & Xray<br/>(Xray JSON & Jira CSV Exporters)"]
    end

    subgraph QA_Agentic_Nodes ["QA Agentic Workflow Nodes"]
        N1["prompts/01_requirement_analyst.md"]
        N2["prompts/02_scenario_designer.md"]
        N3["prompts/03_testcase_generator.md"]
        N4["prompts/04_qa_reviewer.md & linter.py"]
        N5["src/integrations/jira_connector.py"]
    end

    V3 --> N1
    V2 --> N2
    V3 --> N2
    V1 --> N3
    V1 --> N4
    V4 --> N5
```

---

## 7. Kiến Trúc Triển Khai & Vận Hành (Deployment Architecture)

Mô hình hỗ trợ đa phương thức tương tác: CLI Local, Slack Bot 24/7 và Docker Container:

```mermaid
flowchart TD
    subgraph Interaction_Channels ["User Interaction Channels"]
        U1["QA / Tester (Terminal CLI)"]
        U2["Team QA / BA / Dev (Slack Channel / DM)"]
        U3["CI/CD Pipeline (Automated Trigger)"]
    end

    subgraph App_Core ["Application Core"]
        APP["python run.py / slack_run.py"]
        DOCKER["Docker Compose (Containerized 24/7)"]
        PROMPTS["Prompt-as-Code (prompts/*.md)"]
    end

    subgraph External_Services ["External Integrations"]
        JIRA["Jira Cloud / Server REST API"]
        LLM["Multi-LLM Provider (Gemini / OpenAI / Claude / DeepSeek / Ollama)"]
        SLACK_API["Slack Socket Mode Gateway"]
    end

    U1 --> APP
    U2 --> SLACK_API
    SLACK_API --> APP
    U3 --> APP
    DOCKER --> APP
    PROMPTS -.->|Hot Reload / LRU Cache| APP
    APP <--> JIRA
    APP <--> LLM
    APP --> OUT_DIR["outputs/ (Excel 14 Cột, Jira CSV, Xray JSON)"]
```
