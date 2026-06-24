# CLAUDE.md — Lotto Doctor

## Project Overview

Lotto Doctor is a Korean Lotto 6/45 analysis and automated recommendation system built in Python 3.12.

## Key Commands

```bash
# Install (editable + dev deps, Python 3.10+)
pip install -e ".[dev]"

# Collect draw data — 반드시 --source github 사용 (dhlottery.co.kr 차단됨)
lotto-doctor collect --source github
lotto-doctor collect --source github --start 1   # 전체 재수집

# Analyze frequencies
lotto-doctor analyze

# Generate recommendations
lotto-doctor recommend
lotto-doctor recommend --send          # also sends via Telegram

# Check results
lotto-doctor check-result
lotto-doctor check-result --send

# Walk-forward backtest
lotto-doctor backtest

# Resend a previous recommendation
lotto-doctor resend --target-draw-no 1234

# Run tests
pytest
pytest -v tests/test_filters.py
```

## Environment Variables (required for Telegram)

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Copy `.env.example` to `.env` and fill in. Never commit `.env`.

## Architecture

| Module | Role |
|--------|------|
| `config.py` | Load `config/default.yaml` + env vars |
| `models.py` | Dataclasses: Draw, RecommendationRun, RecommendationGame, ... |
| `collector.py` | GitHub smok95/lotto 병렬 수집 (기본) + dhlottery.co.kr fallback |
| `database.py` | SQLite CRUD for 6 tables |
| `validator.py` | Range/uniqueness checks |
| `analyzer.py` | Frequency, gap, pair statistics |
| `features.py` | Per-number and per-combination feature computation |
| `filters.py` | 9 combination filters + portfolio diversity check |
| `scorer.py` | Weighted linear scoring per strategy |
| `generator.py` | Generate 300k candidate combinations |
| `portfolio.py` | Greedy selection of 10 diverse games |
| `evaluator.py` | Match counting and prize ranking |
| `backtester.py` | Walk-forward backtest |
| `telegram_bot.py` | Telegram Bot API, message formatting |
| `reporter.py` | CSV and Markdown report generation |
| `cli.py` | Click CLI (`lotto-doctor` entry point) |
| `utils.py` | Shared helpers |

## Model

**Balanced Ensemble be-v1.0.0** — 300,000 candidates, 5 strategies, 10 games per recommendation.

Seed = target draw number → **fully deterministic** given the same config.

## Database (SQLite at `data/lotto.db`)

Tables: `draws`, `recommendation_runs`, `recommendation_games`, `candidate_numbers`, `evaluation_results`, `backtest_runs`.

## Testing

```bash
pytest                  # all tests
pytest --cov=lotto_doctor --cov-report=term-missing
```

Test files:
- `test_validator.py` — number range and uniqueness
- `test_filters.py` — all combination filters
- `test_generator.py` — 10 games, diversity, determinism
- `test_evaluator.py` — prize ranking
- `test_backtester.py` — walk-forward with small sample
- `test_telegram_message.py` — disclaimer present, message structure

## GitHub Actions

| 워크플로우 | 스케줄 | 설명 |
|-----------|--------|------|
| `daily_recommendation.yml` | 매일 09:00 KST | 추천 생성 + 텔레그램 발송 |
| `weekly_recommendation.yml` | 금요일 09:00 KST | 주간 추천 |
| `weekly_result_check.yml` | 일요일 09:00 KST | 결과 확인 |
| `server_deploy.yml` | 수동 only | 서버 SSH 명령 실행 |

모두 `workflow_dispatch` 수동 실행 지원.
Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SSH_PRIVATE_KEY`, `SSH_HOST`, `SSH_USER`

## 서버

- `ubuntu@168.107.4.184` — 로또봇 및 트레이딩봇 운영 서버
- 서버 명령은 GitHub Actions `Server Deploy / Command` 워크플로우로 실행
- 서버 DB: `/home/ubuntu/lotto_number/lotto-doctor/data/lotto.db` (1~1229회차)
