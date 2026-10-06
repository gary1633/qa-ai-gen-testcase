#!/usr/bin/env python3
"""
QA Agentic Workflow - Web GUI Runner
Mở giao diện web (chat) để tạo bộ test case mà không cần dùng dòng lệnh hay Slack.
"""
import argparse
import os
import socket
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv()


def lan_ip() -> str:
    """IP của máy trong mạng nội bộ (UDP connect không gửi gói tin nào, chỉ để hệ điều hành chọn interface)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main():
    parser = argparse.ArgumentParser(description="Chạy Web GUI của QA Agentic Workflow")
    parser.add_argument("--host", default=os.getenv("WEB_HOST", "127.0.0.1"),
                        help="Địa chỉ lắng nghe (mặc định 127.0.0.1; dùng 0.0.0.0 để cả team trong mạng nội bộ truy cập)")
    parser.add_argument("--port", type=int, default=int(os.getenv("WEB_PORT") or os.getenv("PORT") or "8000"),
                        help="Cổng (mặc định 8000; trên Render tự dùng biến PORT)")
    args = parser.parse_args()

    on_render = bool(os.getenv("RENDER"))
    if on_render and not os.getenv("WEB_ACCESS_PASSWORD"):
        sys.exit("⛔ Đang chạy trên Render (Internet công khai) nhưng chưa đặt WEB_ACCESS_PASSWORD — từ chối khởi động "
                 "để người lạ không dùng được quota LLM/Jira và đọc lịch sử. Đặt biến này ở Render Dashboard > Environment.")

    import uvicorn
    from src.integrations.web_app import create_web_app

    if os.getenv("WEB_ACCESS_PASSWORD"):
        print("🔒 Đã bật mật khẩu truy cập (WEB_ACCESS_PASSWORD).")
    print(f"🌐 QA Agent Web GUI trên máy này: http://localhost:{args.port}")
    if args.host in ("0.0.0.0", "::") and not on_render:
        print(f"👥 Đồng nghiệp cùng mạng nội bộ mở: http://{lan_ip()}:{args.port}")
        if sys.platform == "darwin":
            print("   (macOS: nếu đồng nghiệp không vào được, Firewall đang chặn Python — xem README mục Web GUI > Khắc phục sự cố)")
            framework_app = Path(sys.base_prefix).resolve() / "Resources" / "Python.app"
            firewall_app = framework_app if framework_app.exists() else Path(sys.executable).resolve()
            print(f"   Ứng dụng cần cho phép trong Firewall: {firewall_app}")
    uvicorn.run(create_web_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
