from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

# Coolify 환경 변수 매핑
VERKADA_API_KEY = os.getenv("VERKADA_API_KEY", "YOUR_VERKADA_API_KEY")
VERKADA_ORG_ID = os.getenv("VERKADA_ORG_ID", "61b8824a-14bd-4642-9165-1e7d7b173167")
CAMERA_ID = os.getenv("CAMERA_ID", "YOUR_VERKADA_CAMERA_ID")
EVENT_TYPE_UID = os.getenv("EVENT_TYPE_UID", "7a8f4903-434d-4674-adf9-83b4dcafbc67")

def get_verkada_api_token():
    """Verkada 공식 문서에 따라 단기 Bearer 토큰을 발급받습니다."""
    token_url = "https://api.verkada.com/token"
    headers = {
        "accept": "application/json",
        "x-verkada-auth": VERKADA_API_KEY
    }
    try:
        response = requests.post(token_url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("token") or data.get("api_token")
        else:
            print(f"❌ [토큰 발급 실패] 코드: {response.status_code}, 내용: {response.text}")
            return None
    except Exception as e:
        print(f"❌ [토큰 발급 중 예외 발생]: {str(e)}")
        return None

@app.post("/webhook/linux-log")
async def handle_linux_log(request: Request):
    linux_data = await request.json()
    
    # 1. 단기 Bearer 토큰 가져오기
    api_token = get_verkada_api_token()
    if not api_token:
        return {"status": "error", "message": "Verkada Authentication Failed"}
    
    # 2. Helix API 명세서 규격 조립
    helix_url = f"https://api.verkada.com/cameras/v1/video_tagging/event?org_id={VERKADA_ORG_ID}"
    headers = {
        "content-type": "application/json",
        "Authorization": f"Bearer {api_token}"
    }
    
    verkada_payload = {
        "attributes": {
            "Hostname": linux_data["hostname"],
            "LoginType": linux_data["login_type"],
            "Status": linux_data["status"],
            "User": linux_data["user"]
        },
        "event_type_uid": EVENT_TYPE_UID,
        "camera_id": CAMERA_ID,
        "time_ms": linux_data["timestamp_ms"]
    }
    
    try:
        res = requests.post(helix_url, headers=headers, json=verkada_payload, timeout=5)
        print(f"🟢 [Helix 전송 결과] 코드: {res.status_code} | 응답: {res.text}")
        return {"status": "success", "verkada_status_code": res.status_code}
    except Exception as e:
        print(f"🔴 [Helix 전송 실패] 에러: {str(e)}")
        return {"status": "error", "message": str(e)}
