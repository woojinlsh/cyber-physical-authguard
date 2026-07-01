from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import requests
import os
import time

app = FastAPI(title="Verkada Helix Middleware")

# 환경 변수 로드
VERKADA_MASTER_KEY = os.getenv("VERKADA_MASTER_KEY")
VERKADA_ORG_ID = os.getenv("VERKADA_ORG_ID")
CAMERA_ID = os.getenv("CAMERA_ID")
EVENT_TYPE_UID = os.getenv("EVENT_TYPE_UID")

# 🔒 토큰 캐싱 변수
cached_token = None
token_expires_at = 0

def get_verkada_token():
    global cached_token, token_expires_at
    current_time = time.time()

    if cached_token and current_time < token_expires_at:
        return cached_token

    # flush=True를 붙여 로그가 즉시 보이도록 강제합니다.
    print("🔄 [Token] 토큰 갱신 시도 중...", flush=True)

    token_url = "https://api.verkada.com/token"
    headers = {"accept": "application/json", "x-api-key": VERKADA_MASTER_KEY}

    try:
        response = requests.post(token_url, headers=headers, timeout=5)
        if response.status_code == 200:
            res_data = response.json()
            token = res_data.get("token") or res_data.get("api_token")
            if token:
                cached_token = token
                token_expires_at = current_time + 1500
                print("✅ [Token] 토큰 발급 성공", flush=True)
                return cached_token
        
        # 🔴 토큰 발급 에러 시 상세 내용을 무조건 출력
        print(f"❌ [Token Error] 코드: {response.status_code}, 내용: {response.text}", flush=True)
        return None
    except Exception as e:
        print(f"❌ [Token Exception] 오류: {str(e)}", flush=True)
        return None

@app.post("/webhook/linux-log")
async def handle_linux_log(request: Request):
    # 🔴 1. 환경변수 누락으로 인한 500 에러 추적 로그
    if not all([VERKADA_MASTER_KEY, VERKADA_ORG_ID, CAMERA_ID, EVENT_TYPE_UID]):
        missing = [k for k, v in {"VERKADA_MASTER_KEY": VERKADA_MASTER_KEY, "VERKADA_ORG_ID": VERKADA_ORG_ID, "CAMERA_ID": CAMERA_ID, "EVENT_TYPE_UID": EVENT_TYPE_UID}.items() if not v]
        print(f"❌ [500 Error] 필수 환경변수 누락됨: {missing}", flush=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": f"Missing env vars: {missing}"}
        )

    # 🔴 2. 토큰 갱신 실패로 인한 500 에러 추적 로그
    api_token = get_verkada_token()
    if not api_token:
        print("❌ [500 Error] Verkada 토큰 인증 실패로 요청을 중단합니다.", flush=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "Token generation failed"}
        )

    linux_data = await request.json()
    print(f"📥 [Webhook] 로그 수신: {linux_data.get('user')} ({linux_data.get('status')})", flush=True)
    
    helix_url = f"https://api.verkada.com/cameras/v1/video_tagging/event?org_id={VERKADA_ORG_ID}"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-verkada-auth": api_token
    }
    
    verkada_payload = {
        "attributes": {
            "Hostname": linux_data.get("hostname", "unknown"),
            "LoginType": linux_data.get("login_type", "unknown"),
            "Status": linux_data.get("status", "unknown"),
            "User": linux_data.get("user", "unknown")
        },
        "event_type_uid": EVENT_TYPE_UID,
        "camera_id": CAMERA_ID,
        "time_ms": linux_data.get("timestamp_ms")
    }
    
    try:
        response = requests.post(helix_url, headers=headers, json=verkada_payload, timeout=5)
        print(f"📦 [Helix API] Verkada 전송 완료 - 응답 코드: {response.status_code}", flush=True)
        
        if response.status_code == 200:
            return {"status": "success"}
        else:
            # 🔴 3. Verkada가 200이 아닌 다른 코드를 줄 때의 로그
            print(f"❌ [502 Error] Verkada 거절 코드: {response.status_code}, 내용: {response.text}", flush=True)
            return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"status": "fail"})
    except Exception as e:
        print(f"❌ [500 Error] 전송 중 예외 발생: {str(e)}", flush=True)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"status": "error"})
