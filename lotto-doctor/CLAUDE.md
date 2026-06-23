# CLAUDE.md — Lotto Doctor

## Project Overview

Lotto Doctor is a Korean Lotto 6/45 analysis and automated recommendation system built in Python 3.12.

## Key Commands

```bash
# Install (editable + dev deps)
pip install -e ".[dev]"

# Collect draw data
lotto-doctor collect

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
| `collector.py` | HTTP fetch from `dhlottery.co.kr` with retry |
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

- `weekly_recommendation.yml` — Friday 09:00 KST (cron `0 0 * * 5`)
- `weekly_result_check.yml` — Sunday 09:00 KST (cron `0 0 * * 0`)

Both support `workflow_dispatch` for manual runs. Secrets required: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
