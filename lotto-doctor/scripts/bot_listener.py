"""
텔레그램 봇 리스너
"번호" 라고 치면 이번주 추천번호를 자동으로 답장합니다.

실행방법 (Ubuntu 서버):
  nohup python3 ~/lotto_number/lotto-doctor/scripts/bot_listener.py > ~/lotto_listener.log 2>&1 &

중지:
  pkill -f bot_listener.py
"""

import time
import subprocess
import sys
import os
import requests
from pathlib import Path

# lotto-doctor 패키지 경로 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

KEYWORDS = ["번호", "추천", "로또", "lotto", "번호줘", "번호알려줘"]


def get_updates(offset: int) -> list:
    try:
        resp = requests.get(
            f"{BASE_URL}/getUpdates",
            params={"timeout": 30, "offset": offset},
            timeout=40,
        )
        data = resp.json()
        if data.get("ok"):
            return data["result"]
    except Exception as e:
        print(f"[ERROR] getUpdates 실패: {e}")
    return []


def send_text(chat_id: int | str, text: str) -> None:
    try:
        requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[ERROR] sendMessage 실패: {e}")


def get_recommendation() -> str:
    """lotto-doctor recommend 실행해서 메시지 텍스트 반환"""
    try:
        result = subprocess.run(
            ["lotto-doctor", "recommend"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env={**os.environ},
            timeout=120,
        )
        output = result.stdout.strip()
        if output:
            return output
        return "추천번호 생성에 실패했습니다. 잠시 후 다시 시도해주세요."
    except Exception as e:
        return f"오류 발생: {e}"


def main() -> None:
    if not TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN 환경변수가 없습니다.")
        sys.exit(1)

    print(f"[INFO] 텔레그램 봇 리스너 시작")
    print(f"[INFO] 키워드: {KEYWORDS}")
    print(f"[INFO] 봇 주소: https://t.me/Lotttttto_bot")

    offset = 0
    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message") or update.get("channel_post")
            if not msg:
                continue

            text = msg.get("text", "").strip()
            chat_id = msg["chat"]["id"]
            user = msg.get("from", {}).get("first_name", "")

            print(f"[MSG] {user}({chat_id}): {text}")

            # 키워드 감지
            if any(kw in text for kw in KEYWORDS):
                print(f"[INFO] 키워드 감지 → 추천번호 생성 중...")
                send_text(chat_id, "🎱 잠깐만요! 이번주 추천번호 가져오는 중...")
                recommendation = get_recommendation()
                send_text(chat_id, recommendation)
                print(f"[INFO] 발송 완료")

        time.sleep(1)


if __name__ == "__main__":
    main()
