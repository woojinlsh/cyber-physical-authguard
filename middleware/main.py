from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

# Coolify의 Environment Variables(환경변수) 기능으로 관리하면 안전합니다.
VERKADA_API_KEY = os.getenv("VERKADA_API_KEY", "YOUR_VERKADA_API_KEY")
CAMERA_ID = os.getenv("CAMERA_ID", "YOUR_VERKADA_CAMERA_ID")
EVENT_TYPE_UID = os.getenv("EVENT_TYPE_UID", "YOUR_HELIX_EVENT_TYPE_UID")

@app.post("/webhook/linux-log")
async def handle_linux_log(request: Request):
    linux_data = await request.json()
    
    helix_url = "https://api.verkada.com/cameras/v1/video_tagging/event"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-api-key": VERKADA_API_KEY
    }
    
    # Verkada Helix 속성에 'Status' 추가
    verkada_payload = {
        "camera_id": CAMERA_ID,
        "event_type_uid": EVENT_TYPE_UID,
        "time_ms": linux_data["timestamp_ms"],
        "flagged": True if linux_data["status"] == "failed" else False, # 실패 로그는 UI에서 자동으로 플래그(강조) 표시
        "attributes": {
            "User": linux_data["user"],
            "LoginType": linux_data["login_type"],
            "Status": linux_data["status"],
            "Hostname": linux_data["hostname"]
        }
    }
    
    try:
        res = requests.post(helix_url, headers=headers, json=verkada_payload, timeout=5)
        return {"status": "success", "verkada_status_code": res.status_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}
