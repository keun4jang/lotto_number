# Lotto Doctor

Korean Lotto 6/45 statistical analysis and number recommendation system.

> **DISCLAIMER**: 정상적인 로또에서 모든 6개 번호 조합의 1등 확률은 동일합니다.
> 이 시스템의 추천은 통계적 분석일 뿐이며 당첨을 보장하지 않습니다.
>
> **All 6-number combinations in a fair lottery have equal 1st-prize probability.**
> Recommendations from this system are purely statistical and do **not** guarantee winnings.

---

## Features

- Automated draw data collection from the official Korean Lotto API
- Frequency analysis, gap analysis, and trend detection
- Balanced Ensemble model (`be-v1.0.0`) generating 300,000 candidates per run
- 10 diverse recommended games per week across 5 strategies
- Telegram bot integration for automatic delivery
- Walk-forward backtesting with comparison to random baseline
- CSV and Markdown reports saved locally
- GitHub Actions for fully automated weekly workflow

---

## Installation

```bash
cd lotto-doctor
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

---

## Environment Setup

Copy the example file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=-1001234567890
```

**Never commit `.env` to version control.**

---

## Telegram Bot Setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram and create a new bot.
2. Copy the bot token into `TELEGRAM_BOT_TOKEN`.
3. Add the bot to your group/channel, or start a direct conversation.
4. Get the chat ID:
   - For a private chat: send a message to the bot and visit
     `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - For a group: add `@userinfobot` to the group and type `/start`
5. Set `TELEGRAM_CHAT_ID` (groups/channels use a negative number, e.g. `-1001234567890`).

---

## Data Collection

```bash
# Collect all historical draws (first run, takes a few minutes)
lotto-doctor collect

# Collect only new draws since last run
lotto-doctor collect
```

---

## Generate Recommendations

```bash
# Generate and display recommendations for the next draw
lotto-doctor recommend

# Generate and send via Telegram
lotto-doctor recommend --send

# Target a specific draw number
lotto-doctor recommend --draw-no 1150
```

---

## Send via Telegram

```bash
lotto-doctor recommend --send

# Resend a previously generated recommendation
lotto-doctor resend --target-draw-no 1150
```

---

## Check Results

```bash
# After the draw, collect the result and evaluate previous recommendations
lotto-doctor collect
lotto-doctor check-result

# Evaluate and send results via Telegram
lotto-doctor check-result --send
```

---

## Frequency Analysis

```bash
lotto-doctor analyze
```

---

## Backtest

Run a walk-forward backtest to measure historical performance:

```bash
lotto-doctor backtest
```

The report is saved to `reports/backtest_summary.md`.

```bash
# Use a smaller training window for speed
lotto-doctor backtest --min-train 100
```

---

## GitHub Actions Setup

Automate the weekly workflow with GitHub Actions:

1. Push this repository to GitHub.
2. Go to **Settings → Secrets and variables → Actions**.
3. Add repository secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. The workflows will run automatically:
   - **Friday 09:00 KST** – collect data, generate and send recommendation
   - **Sunday 09:00 KST** – collect result, evaluate and send result

You can also trigger either workflow manually via the **Actions** tab → **Run workflow**.

---

## Model Description

### Balanced Ensemble (`be-v1.0.0`)

Generates **300,000 candidate combinations** split across 5 strategies:

| Strategy | Candidates | Games Selected |
|----------|-----------|----------------|
| balanced | 120,000 | 4 |
| recent | 60,000 | 2 |
| gap | 60,000 | 2 |
| anti_crowding | 30,000 | 1 |
| random_quality | 30,000 | 1 |

Each combination is **scored** using weighted features:

| Feature | Weight |
|---------|--------|
| Long-term frequency | 0.20 |
| Recent frequency (last 20 draws) | 0.20 |
| Gap score (overdue numbers) | 0.15 |
| Pair co-occurrence | 0.15 |
| Distribution (spacing) | 0.15 |
| Anti-crowding | 0.10 |
| Diversity (group entropy) | 0.05 |

The **seed** for each run equals the target draw number, ensuring fully **deterministic** results: the same draw number + model + config always produces the same recommendation.

### Combination Filters

All generated combinations must pass:

- Sum: 90–190
- Odd count: 2, 3, or 4
- Low numbers (1–22): 2, 3, or 4
- Consecutive pairs: ≤ 2
- Same ending digit: ≤ 2 numbers
- Same tens group: ≤ 3 numbers
- At least one number ≥ 32
- Not a pure arithmetic sequence
- ≤ 3 numbers overlapping with the previous draw

### Portfolio Diversity

The final 10 selected games must not share more than **2 numbers** between any two games.

---

## Project Structure

```
lotto-doctor/
  config/default.yaml     All tunable parameters
  data/lotto.db           SQLite database (auto-created)
  reports/                Generated CSV and Markdown reports
  scripts/                Thin CLI wrappers for each command
  src/lotto_doctor/       Main package
  tests/                  pytest test suite
  .github/workflows/      GitHub Actions automation
```
