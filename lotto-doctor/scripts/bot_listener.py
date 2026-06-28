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

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
DB_PATH = ROOT / "data" / "lotto.db"

KEYWORDS = ["번호", "추천", "로또", "lotto", "번호줘", "번호알려줘"]

# 회차별 캐시: {draw_no: 메시지}
_cache: dict[int, str] = {}


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

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
        print(f"[ERROR] getUpdates: {e}")
    return []


def send_text(chat_id: int | str, text: str) -> None:
    try:
        requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[ERROR] sendMessage: {e}")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_latest_draw_no() -> int | None:
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def get_latest_recommendation_from_db() -> tuple[int, str] | None:
    """DB에서 가장 최근 추천 결과를 (draw_no, 메시지) 형태로 반환."""
    try:
        conn = sqlite3.connect(str(DB_PATH))

        # 가장 최근 추천 run
        row = conn.execute(
            "SELECT id, draw_no FROM recommendation_runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            conn.close()
            return None

        run_id, draw_no = row

        games = conn.execute(
            "SELECT game_label, strategy, n1,n2,n3,n4,n5,n6 "
            "FROM recommendation_games WHERE run_id=? ORDER BY game_label",
            (run_id,),
        ).fetchall()

        candidates = conn.execute(
            "SELECT number FROM candidate_numbers WHERE run_id=? ORDER BY rank LIMIT 10",
            (run_id,),
        ).fetchall()

        total_draws = conn.execute("SELECT COUNT(*) FROM draws").fetchone()[0]

        # 직전 회차 날짜로 추첨일 계산 (로또는 매주 토요일)
        prev_row = conn.execute(
            "SELECT draw_date FROM draws WHERE draw_no=? LIMIT 1",
            (draw_no - 1,),
        ).fetchone()
        conn.close()

        if not games or len(games) < 10:
            return None

        # 추첨일 계산: 직전 회차 날짜 + 7일
        from datetime import datetime, timedelta
        if prev_row and prev_row[0]:
            try:
                prev_date = datetime.strptime(str(prev_row[0]), "%Y-%m-%d")
                draw_date = prev_date + timedelta(days=7)
                date_str = draw_date.strftime("%Y년 %m월 %d일")
            except Exception:
                date_str = "날짜 미상"
        else:
            date_str = "날짜 미상"

        top10 = "  " + "  ".join(str(r[0]) for r in candidates)
        lines = [
            f"🎱 로또 제{draw_no}회 추천번호",
            f"📅 추첨일: {date_str} (토요일)\n",
            f"📊 후보번호 TOP 10\n{top10}\n",
            f"🎯 추천 {len(games)}게임",
        ]
        for g in games:
            label, strategy, n1, n2, n3, n4, n5, n6 = g
            nums = f"{n1:02d} - {n2:02d} - {n3:02d} - {n4:02d} - {n5:02d} - {n6:02d}"
            lines.append(f"  {label}게임 [{strategy}]  {nums}")

        lines.append(f"\n📈 분석 요약")
        lines.append(f"  • 총 학습 회차: {total_draws}")
        lines.append(f"  • 추천 대상 회차: {draw_no}")
        lines.append(f"  • 모델: balanced-ensemble be-v1.0.0")
        lines.append("\n⚠️ 주의: 정상적인 로또에서 모든 6개 번호 조합의 1등 확률은 동일합니다.")
        lines.append("이 추천은 통계적 분석일 뿐이며 당첨을 보장하지 않습니다.")

        return draw_no, "\n".join(lines)

    except Exception as e:
        print(f"[ERROR] DB 조회 실패: {e}")
        return None


# ---------------------------------------------------------------------------
# 추천 생성
# ---------------------------------------------------------------------------

def generate_fresh_recommendation() -> str:
    """lotto-doctor recommend 실행해서 최신 추천 생성."""
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
            print(f"[ERROR] stderr: {result.stderr[:300]}")
        return output if output else "추천번호 생성에 실패했습니다."
    except subprocess.TimeoutExpired:
        return "생성 시간이 초과됐습니다. 잠시 후 다시 시도해주세요."
    except Exception as e:
        return f"오류: {e}"


def get_recommendation() -> str:
    """캐시 우선 → DB → 새 생성 순서로 추천번호 반환. 메시지는 단 1개."""
    latest_draw = get_latest_draw_no()

    # 1) 메모리 캐시 확인
    if latest_draw and latest_draw in _cache:
        print(f"[INFO] 메모리 캐시 사용 (draw_no={latest_draw})")
        return _cache[latest_draw]

    # 2) DB 캐시 확인 (가장 최근 추천, 10게임 이상만 유효)
    db_result = get_latest_recommendation_from_db()
    if db_result:
        db_draw_no, db_msg = db_result
        print(f"[INFO] DB 캐시 사용 (draw_no={db_draw_no})")
        if latest_draw:
            _cache[latest_draw] = db_msg
        return db_msg

    # 3) 새로 생성
    print("[INFO] 새 추천 생성 중...")
    msg = generate_fresh_recommendation()

    # 생성 후 DB 캐시 재조회 (lotto-doctor recommend가 DB에 저장함)
    db_result = get_latest_recommendation_from_db()
    if db_result:
        _, formatted_msg = db_result
        if latest_draw:
            _cache[latest_draw] = formatted_msg
        return formatted_msg

    if latest_draw and "오류" not in msg and "실패" not in msg:
        _cache[latest_draw] = msg
    return msg


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    if not TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN 없음")
        sys.exit(1)

    print("[INFO] 텔레그램 봇 리스너 시작")
    print(f"[INFO] 키워드: {KEYWORDS}")
    print("[INFO] 봇: https://t.me/Lotttttto_bot")

    # 시작 시 DB 캐시 미리 로드
    db_result = get_latest_recommendation_from_db()
    if db_result:
        draw_no, msg = db_result
        latest = get_latest_draw_no()
        if latest:
            _cache[latest] = msg
        print(f"[INFO] 시작 캐시 로드 완료 (draw_no={draw_no})")
    else:
        print("[INFO] DB 캐시 없음, 첫 요청 시 생성")

    offset = 0
    processing = False

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

            if not any(kw in text for kw in KEYWORDS):
                continue

            if processing:
                send_text(chat_id, "⏳ 생성 중이에요. 잠시만 기다려주세요!")
                continue

            processing = True
            try:
                latest_draw = get_latest_draw_no()

                # 캐시에 있으면 바로 발송 (잠깐만요 없이)
                if latest_draw and latest_draw in _cache:
                    send_text(chat_id, _cache[latest_draw])
                    print("[INFO] 캐시 즉시 발송 완료")
                else:
                    # 새로 생성이 필요한 경우만 "잠깐만요" 발송
                    send_text(chat_id, "🎱 잠깐만요! 추천번호 가져오는 중...")
                    recommendation = get_recommendation()
                    send_text(chat_id, recommendation)
                    print("[INFO] 새 추천 발송 완료")
            finally:
                processing = False

        time.sleep(1)


if __name__ == "__main__":
    main()
