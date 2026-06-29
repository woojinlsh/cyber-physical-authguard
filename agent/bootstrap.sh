#!/bin/bash
export DEBIAN_FRONTEND=noninteractive

# Vagrant가 호스트 폴더를 마운트하는 내부 경로
HOST_CONFIG="/vagrant/config.sh"

echo "📁 0. 환경 설정 파일 로드 시도..."
if [ -f "$HOST_CONFIG" ]; then
    # 외부 설정 파일을 현재 쉘로 불러옵니다 (source)
    source "$HOST_CONFIG"
    echo "✅ 설정을 성공적으로 불러왔습니다. 목적지: $MIDDLEWARE_URL"
else
    echo "❌ 에러: $HOST_CONFIG 파일이 없습니다!"
    echo "config.sh.example 파일을 복사하여 config.sh를 만들고 주소를 입력해주세요."
    exit 1
fi

echo "🔄 1. 패키지 업데이트 및 필수 도구 설치..."
apt-get update -y
apt-get install -y python3 python3-pip curl

echo "📂 2. 로그 시퍼(Log Shipper) 앱 배포 공간 생성..."
mkdir -p /opt/log_shipper

echo "📜 3. Python 에이전트 소스코드 작성..."
cat << EOF > /opt/log_shipper/log_shipper.py
import time
import os
import re
import requests

LOG_FILE = "/var/log/auth.log"
# 분리된 파일에서 가져온 변수가 여기에 자연스럽게 대입됩니다.
MIDDLEWARE_URL = "${MIDDLEWARE_URL}"

opened_pattern = re.compile(r'(sshd|login)\[\d+\]: pam_unix\(\1:session\): session opened for user (\w+)')
ssh_fail_pattern = re.compile(r'sshd\[\d+\]: Failed password for (?:invalid user )?(\w+) from')
local_fail_pattern = re.compile(r'login\[\d+\]: FAILED LOGIN \(\d+\) on \'\S+\' FOR \'(\w+)\'')

print("🚀 Linux Log Shipper 에이전트 시작...")

try:
    with open(LOG_FILE, "r") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
                
            user = None
            login_type = "unknown"
            status = "unknown"
            
            match_success = opened_pattern.search(line)
            if match_success:
                login_type = "local" if match_success.group(1) == "login" else "remote"
                user = match_success.group(2)
                status = "success"
                
            match_ssh_fail = ssh_fail_pattern.search(line)
            if match_ssh_fail:
                login_type = "remote"
                user = match_ssh_fail.group(1)
                status = "failed"
                
            match_local_fail = local_fail_pattern.search(line)
            if match_local_fail:
                login_type = "local"
                user = match_local_fail.group(1)
                status = "failed"
            
            if user:
                payload = {
                    "user": user,
                    "login_type": login_type,
                    "status": status,
                    "hostname": os.uname()[1],
                    "timestamp_ms": int(time.time() * 1000)
                }
                try:
                    requests.post(MIDDLEWARE_URL, json=payload, timeout=3)
                except Exception as e:
                    print(f"전송 실패: {e}")
except Exception as e:
    print(f"오류 발생: {e}")
EOF

echo "⚙️ 4. 백그라운드 상시 구동을 위한 Systemd 서비스 등록..."
cat << 'EOF' > /etc/systemd/system/log-shipper.service
[Unit]
Description=Linux Log Shipper for Verkada Demo
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /opt/log_shipper/log_shipper.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "▶️ 5. 서비스 활성화 및 시작..."
systemctl daemon-reload
systemctl enable log-shipper.service
systemctl start log-shipper.service

echo "✅ 모든 배포가 완료되었습니다!"
