"""
텔레그램 봇 리스너
"번호" 라고 치면 이번주 추천번호를 자동으로 답장합니다.

실행방법 (Ubuntu 서버):
  nohup env PYTHONPATH=/home/ubuntu/lotto_number/lotto-doctor/src \
    python3 /home/ubuntu/lotto_number/lotto-doctor/scripts/bot_listener.py \
    > /home/ubuntu/lotto_listener.log 2>&1 &

중지:
  pkill -f bot_listener.py
"""

import time
import subprocess
import sys
import os
import requests
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
DB_PATH = ROOT / "data" / "lotto.db"

KEYWORDS = ["번호", "추천", "로또", "lotto", "번호줘", "번호알려줘"]

# 이번 주 캐시 (draw_no -> 메시지)
_cache: dict[int, str] = {}


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


def get_latest_draw_no() -> int | None:
    """DB에서 최신 회차 번호 조회"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def get_cached_recommendation(draw_no: int) -> str | None:
    """DB에 저장된 추천 결과 조회"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT id FROM recommendation_runs WHERE draw_no=? ORDER BY created_at DESC LIMIT 1",
            (draw_no,),
        ).fetchone()
        if not row:
            conn.close()
            return None
        run_id = row[0]
        games = conn.execute(
            "SELECT game_label, strategy, n1,n2,n3,n4,n5,n6 FROM recommendation_games WHERE run_id=? ORDER BY game_label",
            (run_id,),
        ).fetchall()
        candidates = conn.execute(
            "SELECT number FROM candidate_numbers WHERE run_id=? ORDER BY rank LIMIT 10",
            (run_id,),
        ).fetchall()
        conn.close()

        if not games:
            return None

        top10 = ", ".join(str(r[0]) for r in candidates)
        lines = [
            f"🎱 로또 제{draw_no}회 추천번호\n",
            f"📊 후보번호 TOP 10\n  {top10}\n",
            "🎯 추천 10게임",
        ]
        for g in games:
            label, strategy, n1, n2, n3, n4, n5, n6 = g
            nums = f"{n1:02d} - {n2:02d} - {n3:02d} - {n4:02d} - {n5:02d} - {n6:02d}"
            lines.append(f"  {label}게임 [{strategy}]  {nums}")

        lines.append("\n⚠️ 주의: 정상적인 로또에서 모든 6개 번호 조합의 1등 확률은 동일합니다. 이 추천은 통계적 분석일 뿐이며 당첨을 보장하지 않습니다.")
        return "\n".join(lines)
    except Exception as e:
        print(f"[ERROR] DB 캐시 조회 실패: {e}")
        return None


def generate_recommendation() -> str:
    """lotto-doctor recommend 실행 (타임아웃 300초)"""
    try:
        result = subprocess.run(
            ["lotto-doctor", "recommend"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            timeout=300,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            print(f"[ERROR] stderr: {result.stderr[:200]}")
        return output if output else "추천번호 생성에 실패했습니다. 잠시 후 다시 시도해주세요."
    except subprocess.TimeoutExpired:
        return "추천번호 생성 시간이 초과됐습니다. 잠시 후 다시 시도해주세요."
    except Exception as e:
        return f"오류 발생: {e}"


def get_recommendation() -> str:
    """DB 캐시 우선 조회 → 없으면 새로 생성"""
    draw_no = get_latest_draw_no()

    # 메모리 캐시 확인
    if draw_no and draw_no in _cache:
        print(f"[INFO] 메모리 캐시 사용 (회차 {draw_no})")
        return _cache[draw_no]

    # DB 캐시 확인
    if draw_no:
        cached = get_cached_recommendation(draw_no + 1)  # 다음 회차 추천
        if cached:
            print(f"[INFO] DB 캐시 사용 (회차 {draw_no + 1})")
            _cache[draw_no] = cached
            return cached

    # 새로 생성
    print(f"[INFO] 새 추천 생성 중...")
    msg = generate_recommendation()
    if draw_no and "오류" not in msg and "실패" not in msg:
        _cache[draw_no] = msg
    return msg


def main() -> None:
    if not TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN 환경변수가 없습니다.")
        sys.exit(1)

    print("[INFO] 텔레그램 봇 리스너 시작")
    print(f"[INFO] 키워드: {KEYWORDS}")
    print("[INFO] 봇 주소: https://t.me/Lotttttto_bot")

    # 시작 시 미리 캐시 준비
    draw_no = get_latest_draw_no()
    if draw_no:
        print(f"[INFO] DB 최신 회차: {draw_no}, 추천 캐시 준비 중...")
        cached = get_cached_recommendation(draw_no + 1)
        if cached:
            _cache[draw_no] = cached
            print(f"[INFO] 캐시 준비 완료")
        else:
            print(f"[INFO] 캐시 없음, 첫 요청 시 생성됩니다")

    offset = 0
    processing = False  # 중복 요청 방지

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

            if any(kw in text for kw in KEYWORDS):
                if processing:
                    send_text(chat_id, "⏳ 이미 생성 중이에요. 잠시만 기다려주세요!")
                    continue

                processing = True
                try:
                    # DB 캐시 있으면 바로 발송
                    draw_no = get_latest_draw_no()
                    if draw_no and draw_no in _cache:
                        send_text(chat_id, _cache[draw_no])
                        print("[INFO] 캐시 발송 완료")
                    else:
                        send_text(chat_id, "🎱 잠깐만요! 이번주 추천번호 가져오는 중...")
                        recommendation = get_recommendation()
                        send_text(chat_id, recommendation)
                        print("[INFO] 발송 완료")
                finally:
                    processing = False

        time.sleep(1)


if __name__ == "__main__":
    main()
