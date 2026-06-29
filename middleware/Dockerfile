FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# 🔥 컨테이너 내부 노출 포트를 9001로 변경
EXPOSE 9001

# 🔥 uvicorn 구동 포트를 9001로 변경
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9001"]
