import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv()

import requests
from src.integrations.jira_connector import JiraConnector, extract_jira_key

def main():
    print("=" * 60)
    print("🔍 KIỂM TRA KẾT NỐI JIRA API VÀ XÁC THỰC TÀI KHOẢN")
    print("=" * 60)

    server_url = os.getenv("JIRA_SERVER_URL", "").rstrip("/")
    email = os.getenv("JIRA_EMAIL", "").strip()
    api_token = os.getenv("JIRA_API_TOKEN", "").strip()
    pat_token = os.getenv("JIRA_PAT_TOKEN") or os.getenv("JIRA_BEARER_TOKEN", "")

    print(f"1. Server URL:  {server_url or '[CHƯA CÓ TRONG .ENV]'}")
    print(f"2. Email:       {email or '[CHƯA CÓ TRONG .ENV]'}")
    print(f"3. API Token:   {'*' * len(api_token) if api_token else '[CHƯA CÓ TRONG .ENV]'}")
    print("-" * 60)

    if not server_url or (not pat_token and (not email or not api_token)):
        print("❌ LỖI: File .env chưa được điền đầy đủ JIRA_SERVER_URL, JIRA_EMAIL, JIRA_API_TOKEN.")
        print("Vui lòng mở file .env và cập nhật.")
        sys.exit(1)

    # Bước 1: Test xác thực danh tính với endpoint /myself
    print("⏳ Bước 1: Đang kiểm tra xác thực tài khoản với Jira (/rest/api/3/myself)...")
    
    headers = {"Accept": "application/json"}
    auth = None
    if pat_token:
        headers["Authorization"] = f"Bearer {pat_token}"
    else:
        auth = (email, api_token)

    try:
        resp = requests.get(f"{server_url}/rest/api/3/myself", auth=auth, headers=headers, timeout=15)
        if resp.status_code == 404:
            # Thử lại với v2
            resp = requests.get(f"{server_url}/rest/api/2/myself", auth=auth, headers=headers, timeout=15)

        if resp.status_code == 200:
            user_data = resp.json()
            display_name = user_data.get("displayName", "N/A")
            account_id = user_data.get("accountId", "N/A")
            email_address = user_data.get("emailAddress", email)
            print(f"✅ XÁC THỰC THÀNH CÔNG!")
            print(f"   • Họ tên: {display_name}")
            print(f"   • Email Jira nhận diện: {email_address}")
            print(f"   • Account ID: {account_id}")
        elif resp.status_code == 401:
            print("❌ THẤT BẠI (401 Unauthorized):")
            print("   • Email hoặc API Token không chính xác.")
            print("   • Hãy tạo lại API Token tại: https://id.atlassian.com/manage-profile/security/api-tokens")
            sys.exit(1)
        elif resp.status_code == 403:
            print("❌ THẤT BẠI (403 Forbidden):")
            print("   • Tài khoản bị chặn truy cập API hoặc cần phân quyền.")
            sys.exit(1)
        else:
            print(f"❌ THẤT BẠI (HTTP {resp.status_code}): {resp.text}")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Không thể kết nối tới server {server_url}: {e}")
        sys.exit(1)

    # Bước 2: Test lấy Ticket VWCBT-3800 (hoặc ticket truyền vào)
    target_ticket = sys.argv[1] if len(sys.argv) > 1 else "VWCBT-3800"
    target_key = extract_jira_key(target_ticket) or "VWCBT-3800"
    
    print(f"\n⏳ Bước 2: Đang kiểm tra quyền đọc Ticket '{target_key}'...")
    try:
        connector = JiraConnector()
        data = connector.fetch_issue(target_key)
        print(f"✅ LẤY TICKET THÀNH CÔNG!")
        print(f"   • Mã Ticket: {data['key']}")
        print(f"   • Tiêu đề: {data['summary']}")
        print(f"   • Loại: {data['issue_type']} | Trạng thái: {data['status']}")
        print(f"   • Chi tiết độ dài mô tả: {len(data['formatted_requirement'])} ký tự.")
        print("\n🎉 MỌI THỨ ĐÃ SẴN SÀNG! Bạn có thể chạy: python run.py " + target_key)
    except Exception as e:
        print(f"❌ LỖI KHI LẤY TICKET '{target_key}':\n{e}")

if __name__ == "__main__":
    main()
