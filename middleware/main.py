from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import requests
import os
import sys
import time

app = FastAPI(title="Verkada Helix Middleware - Auto Token Lifecycle")

# Coolify 환경 변수에서 변수 로드
VERKADA_MASTER_KEY = os.getenv("VERKADA_MASTER_KEY") # 어드민 콘솔의 고정된 마스터 API Key 인입
VERKADA_ORG_ID = os.getenv("VERKADA_ORG_ID")
CAMERA_ID = os.getenv("CAMERA_ID")
EVENT_TYPE_UID = os.getenv("EVENT_TYPE_UID")

# 🔒 단기 토큰 자동 관리를 위한 인메모리 캐시 변수
cached_token = None
token_expires_at = 0  # 토큰 만료 시점 타임스탬프 (초 단위)

def get_verkada_token():
    """
    마스터 API 키를 사용하여 Verkada로부터 30분짜리 단기 토큰을 가져옵니다.
    안전하게 만료 5분 전(발급 후 25분 경과)에 알아서 새 토큰을 받아오는 구조입니다.
    """
    global cached_token, token_expires_at
    current_time = time.time()

    # 1. 유효한 캐시 토큰이 남아있다면 그대로 재사용
    if cached_token and current_time < token_expires_at:
        return cached_token

    # 2. 토큰이 없거나 만료(25분 경과)되었다면 새로 발급 시도
    print("🔄 [Token Lifecycle] 단기 인증 토큰이 만료되었거나 없어 새로 발급을 요청합니다.")
    sys.stdout.flush()

    token_url = "https://api.verkada.com/token"
    headers = {
        "accept": "application/json",
        "x-api-key": VERKADA_MASTER_KEY  # 마스터 키 인증 헤더 규격
    }

    try:
        response = requests.post(token_url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            res_data = response.json()
            # 응답 구조에서 토큰 문자열 추출
            token = res_data.get("token") or res_data.get("api_token")
            
            if not token:
                print(f"❌ [Token Lifecycle Error] 응답 본문에 토큰 필드가 없습니다: {res_data}")
                sys.stdout.flush()
                return None

            # 토큰 및 만료 시간 캐싱 처리
            cached_token = token
            # 30분(1800초) 만료이지만, 안전을 위해 25분(1500초)을 생명주기로 설정
            token_expires_at = current_time + 1500 
            
            print("✅ [Token Lifecycle] 새로운 30분짜리 단기 인증 토큰 발급 및 캐싱 완료.")
            sys.stdout.flush()
            return cached_token
        else:
            print(f"❌ [Token Lifecycle Error] 토큰 발급 거절 - 코드: {response.status_code}, 내용: {response.text}")
            sys.stdout.flush()
            return None
            
    except Exception as e:
        print(f"❌ [Token Lifecycle Error] 외부 인증 서버 통신 오류: {str(e)}")
        sys.stdout.flush()
        return None


@app.post("/webhook/linux-log")
async def handle_linux_log(request: Request):
    # 환경변수 세팅 여부 기본 점검
    if not all([VERKADA_MASTER_KEY, VERKADA_ORG_ID, CAMERA_ID, EVENT_TYPE_UID]):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "Coolify 환경변수(MASTER_KEY, ORG_ID 등)를 확인해주세요."}
        )

    # 🔑 라이프사이클 함수를 호출하여 유효한 단기 토큰 자동 획득
    api_token = get_verkada_token()
    if not api_token:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "Verkada 단기 인증 토큰 갱신에 실패했습니다."}
        )

    # 리눅스로부터 넘어온 웹훅 파싱
    linux_data = await request.json()
    print(f"📥 [Webhook] Linux VM으로부터 로그 수신 완료")
    sys.stdout.flush()
    
    # 템플릿 맞춤 설정 구성
    helix_url = f"https://api.verkada.com/cameras/v1/video_tagging/event?org_id={VERKADA_ORG_ID}"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-verkada-auth": api_token  # 자동으로 관리되는 단기 토큰 주입
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
        print(f"📦 [Helix API] Verkada 전송 완료 - 응답 코드: {response.status_code}")
        sys.stdout.flush()
        
        if response.status_code == 200:
            return {"status": "success"}
        else:
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY, 
                content={"status": "fail", "detail": f"Verkada API returned {response.status_code}"}
            )
    except Exception as e:
        print(f"❌ [Helix API Error] 전송 중 오류 발생: {str(e)}")
        sys.stdout.flush()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            content={"status": "error", "message": "Internal transport error"}
        )
