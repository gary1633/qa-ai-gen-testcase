FROM python:3.12-slim

WORKDIR /app

# Cài đặt các gói hệ thống cần thiết
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy mã nguồn và cài đặt dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache \
    langchain-core \
    langchain-google-genai \
    langchain-openai \
    langchain-anthropic \
    langgraph \
    pydantic \
    openpyxl \
    pillow \
    python-docx \
    pypdf \
    rich \
    pyyaml \
    python-dotenv \
    requests \
    slack-bolt \
    slack-sdk

COPY . .

# Mặc định chạy Slack Bot
CMD ["python", "slack_run.py"]
