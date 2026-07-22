"""CLI entry points for Lotto Doctor."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from .config import compute_config_hash, get_db_path, load_config
from .database import (
    get_all_draws,
    get_all_evaluation_results,
    get_games_for_run,
    get_latest_draw_no,
    get_latest_recommendation_run,
    get_valid_recommendation,
    get_candidate_numbers,
    init_db,
    insert_backtest_run,
    insert_candidate_numbers,
    insert_evaluation_result,
    insert_recommendation_game,
    insert_recommendation_run,
    get_connection,
    upsert_draw,
)
from .models import RecommendationRun


def _get_code_commit() -> Optional[str]:
    import subprocess
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return res.stdout.strip() or None
    except Exception:
        return None


@click.group()
def main() -> None:
    """Lotto Doctor - Korean Lotto 6/45 analysis and recommendation tool."""


@main.command()
@click.option("--start", type=int, default=None, help="Start draw number")
@click.option("--end", type=int, default=None, help="End draw number (default: latest)")
@click.option(
    "--source",
    type=click.Choice(["github", "api"], case_sensitive=False),
    default="github",
    show_default=True,
    help="Data source: github (smok95/lotto, 병렬, 빠름) or api (dhlottery.co.kr)",
)
def collect(start: Optional[int], end: Optional[int], source: str) -> None:
    """Collect lotto draw data."""
    from .collector import (
        collect_all_draws,
        collect_all_draws_github,
        detect_latest_draw_no,
        detect_latest_draw_no_github,
    )

    cfg = load_config()
    db_path = get_db_path(cfg)
    init_db(db_path)

    with get_connection(db_path) as conn:
        db_latest = get_latest_draw_no(conn)

    if start is None:
        start = (db_latest + 1) if db_latest else 1

    if end is None:
        click.echo("최신 회차 확인 중...")
        if source == "github":
            end = detect_latest_draw_no_github()
        else:
            end = detect_latest_draw_no(cfg)

    click.echo(f"[{source}] {start}회 ~ {end}회 수집 중...")

    collected = [0]

    def progress(done: int, total: int) -> None:
        collected[0] = done
        click.echo(f"  [{done}/{total}]\r", nl=False)

    if source == "github":
        draws = collect_all_draws_github(start=start, end=end, progress_callback=progress)
    else:
        draws = collect_all_draws(cfg, start=start, end=end, progress_callback=progress)

    click.echo("")

    with get_connection(db_path) as conn:
        for draw in draws:
            upsert_draw(conn, draw)
        conn.commit()

    click.echo(f"저장 완료: {len(draws)}회차 → {db_path}")


@main.command()
def analyze() -> None:
    """Analyze collected lotto data and show frequency statistics."""
    from .analyzer import get_summary_stats

    cfg = load_config()
    db_path = get_db_path(cfg)
    init_db(db_path)

    with get_connection(db_path) as conn:
        draws = get_all_draws(conn)

    if not draws:
        click.echo("No draws in DB. Run `lotto-doctor collect` first.")
        return

    stats = get_summary_stats(draws)
    click.echo(f"Total draws: {stats['total_draws']}")
    click.echo(f"Latest draw: {stats['latest_draw_no']}")
    click.echo("\nMost frequent numbers:")
    for n, cnt in stats["most_frequent"]:
        click.echo(f"  {n:2d}: {cnt}")
    click.echo("\nLongest gap numbers:")
    for n, gap in stats["longest_gap"]:
        click.echo(f"  {n:2d}: {gap} draws ago")


@main.command()
@click.option("--send", is_flag=True, default=False, help="Send via Telegram")
@click.option("--draw-no", type=int, default=None, help="Target draw number (default: latest+1)")
@click.option("--force", is_flag=True, default=False, help="캐시 무시하고 새 추천 생성")
@click.option(
    "--mode",
    type=click.Choice(["portfolio", "wheel"], case_sensitive=False),
    default="portfolio",
    show_default=True,
    help="portfolio: 기본 전략별 추천 / wheel: TOP-12 후보 번호 축약 휠 (분산 구조만 조정, 확률/EV 불변)",
)
def recommend(send: bool, draw_no: Optional[int], force: bool, mode: str) -> None:
    """Generate recommendations and optionally send via Telegram."""
    from .coverage import format_coverage_line, portfolio_coverage_metrics
    from .portfolio import build_portfolio, build_wheel_portfolio
    from .reporter import save_recommendation_csv, save_recommendation_markdown
    from .telegram_bot import build_recommendation_message, send_message
    from .analyzer import get_summary_stats

    cfg = load_config()
    db_path = get_db_path(cfg)
    init_db(db_path)

    with get_connection(db_path) as conn:
        draws = get_all_draws(conn)
        db_latest = get_latest_draw_no(conn)

    if not draws:
        click.echo("No draws in DB. Run `lotto-doctor collect` first.")
        return

    if draw_no is None:
        draw_no = (db_latest or 0) + 1

    mode = mode.lower()
    seed = draw_no
    model_name = cfg["app"]["model_name"]
    model_version = cfg["app"]["model_version"]
    if mode == "wheel":
        # 캐시/기본 모드와 충돌 방지: wheel run 은 별도 model_version 으로 저장
        model_version = f"{model_version}+wheel"
    cfg_hash = compute_config_hash(cfg)
    num_games = cfg["generator"]["num_games"]
    strategy_games: dict[str, int] = cfg["generator"]["strategy_games"]
    strategy_summary = ",".join(f"{s}:{n}" for s, n in strategy_games.items() if n > 0)
    code_commit = _get_code_commit()

    # 캐시 확인 (--force 시 건너뜀)
    cached_run_id = None
    if not force:
        with get_connection(db_path) as conn:
            cached = get_valid_recommendation(conn, draw_no, model_version, cfg_hash, num_games)
        if cached:
            cached_run_id = cached["id"]
            click.echo(f"[캐시] 기존 추천 재사용 (draw_no={draw_no}, model={model_version})")

    if cached_run_id:
        with get_connection(db_path) as conn:
            games = get_games_for_run(conn, cached_run_id)
            candidate_numbers = get_candidate_numbers(conn, cached_run_id)
    else:
        click.echo(f"Generating recommendations for draw #{draw_no} (seed={seed}, model={model_version})...")

        run = RecommendationRun(
            draw_no=draw_no,
            model_name=model_name,
            model_version=model_version,
            seed=seed,
            config_hash=cfg_hash,
            game_count=num_games,
            strategy_summary=strategy_summary,
            code_commit=code_commit,
        )

        with get_connection(db_path) as conn:
            run_id = insert_recommendation_run(conn, run)
            conn.commit()

        if mode == "wheel":
            games, candidate_numbers, _ = build_wheel_portfolio(draws, cfg, seed, run_id)
        else:
            games, candidate_numbers = build_portfolio(draws, cfg, seed, run_id)

        with get_connection(db_path) as conn:
            for game in games:
                insert_recommendation_game(conn, game)
            insert_candidate_numbers(conn, candidate_numbers)
            conn.commit()

    stats = get_summary_stats(draws)
    summary = {
        "총 학습 회차": stats["total_draws"],
        "최신 회차": stats["latest_draw_no"],
        "모델": f"{model_name} {model_version}",
    }

    # 커버리지 리포트 (분산 구조 지표 — 티켓당 확률/EV 향상 아님, 당첨 보장 없음)
    game_number_lists = [g.numbers for g in games]
    cov_metrics = portfolio_coverage_metrics(game_number_lists)
    wheel_coverage = None
    if mode == "wheel":
        from .coverage import wheel_3subset_coverage
        from .generator import select_top_numbers

        pool_size = cfg.get("portfolio", {}).get("wheel_pool_size", 12)
        pool = [n for n, _ in select_top_numbers(draws, cfg, seed, top_k=pool_size)]
        wheel_coverage = wheel_3subset_coverage(game_number_lists, pool)
    coverage_line = format_coverage_line(cov_metrics, wheel_coverage)

    top_nums = [(c.number, c.score) for c in candidate_numbers]
    save_recommendation_csv(games, draw_no, cfg)
    save_recommendation_markdown(games, top_nums, draw_no, cfg, coverage_line=coverage_line)

    click.echo(f"\n후보번호 TOP 10: {', '.join(str(c.number) for c in candidate_numbers)}")
    click.echo(f"\n추천 {len(games)}게임:")
    for g in games:
        nums_str = " - ".join(f"{n:02d}" for n in g.numbers)
        click.echo(f"  {g.game_label}: [{g.strategy}] {nums_str}")
    click.echo(f"\n{coverage_line}")

    if send:
        from datetime import datetime, timedelta
        draw_date = ""
        with get_connection(db_path) as conn:
            prev = conn.execute(
                "SELECT draw_date FROM draws WHERE draw_no=? LIMIT 1", (draw_no - 1,)
            ).fetchone()
        if prev and prev[0]:
            try:
                d = datetime.strptime(str(prev[0]), "%Y-%m-%d") + timedelta(days=7)
                draw_date = d.strftime("%Y년 %m월 %d일")
            except Exception:
                pass
        msg = build_recommendation_message(draw_no, top_nums, games, summary, draw_date)
        send_message(msg)
        click.echo("\nTelegram message sent.")


@main.command("check-result")
@click.option("--send", is_flag=True, default=False, help="Send results via Telegram")
@click.option("--draw-no", type=int, default=None, help="Draw number to evaluate")
def check_result(send: bool, draw_no: Optional[int]) -> None:
    """Evaluate the latest recommendation against the actual draw result."""
    from .evaluator import evaluate_run, summarise_evaluation
    from .reporter import save_evaluation_markdown
    from .telegram_bot import build_result_message, send_message
    from .utils import compute_cumulative_stats
    from .database import get_draw

    cfg = load_config()
    db_path = get_db_path(cfg)
    init_db(db_path)

    with get_connection(db_path) as conn:
        run_info = get_latest_recommendation_run(conn)
        if run_info is None:
            click.echo("No recommendation runs found.")
            return

        target_draw_no = draw_no or run_info["draw_no"]
        draw = get_draw(conn, target_draw_no)
        if draw is None:
            click.echo(f"Draw #{target_draw_no} not in DB. Run `lotto-doctor collect` first.")
            return

        games = get_games_for_run(conn, run_info["id"])
        if not games:
            click.echo(f"No games found for run #{run_info['id']}.")
            return

        results = evaluate_run(games, draw)
        # 재실행 시 중복 삽입으로 누적/반성 통계가 부풀려지는 것을 방지
        conn.execute(
            "DELETE FROM evaluation_results WHERE run_id = ?", (run_info["id"],)
        )
        for result in results:
            insert_evaluation_result(conn, result)
        conn.commit()

        all_results = get_all_evaluation_results(conn)

    summary = summarise_evaluation(results)
    save_evaluation_markdown(games, results, target_draw_no, cfg)
    cumulative = compute_cumulative_stats(all_results)

    click.echo(f"\n제{target_draw_no}회 당첨번호: {draw.numbers} + 보너스 {draw.bonus}")
    click.echo("\n결과:")
    for r in results:
        click.echo(f"  {r.game_label}: {r.matched_count}개 적중 → {r.rank_label}")
    click.echo(f"\n최고 적중: {summary['best_match']}개")

    if send:
        msg = build_result_message(draw, games, results, cumulative)
        send_message(msg)
        click.echo("\nTelegram message sent.")

    # 반성 리포트 자동 생성 및 발송
    _run_reflection(db_path, draw, games, results, cfg, send)


def _run_reflection(db_path, draw, games, results, cfg, send: bool) -> None:
    """전략별 성과 분석 → 자동 조정 → 반성 텔레그램 발송."""
    from .reflection import (
        load_strategy_performance,
        compute_weight_adjustment,
        generate_reflection_text,
        save_reflection_report,
        apply_strategy_adjustment,
    )
    from .telegram_bot import send_message

    perf = load_strategy_performance(db_path)

    old_strategy_games: dict[str, int] = dict(cfg["generator"]["strategy_games"])
    new_strategy_games = compute_weight_adjustment(perf, cfg)

    games_dict = [
        {
            "game_label": g.game_label,
            "strategy": g.strategy,
            "matched_count": r.matched_count,
            "rank_label": r.rank_label,
            "has_bonus_match": r.has_bonus_match,
        }
        for g, r in zip(games, results)
    ]

    # 성과 기반 자동 조정 먼저 적용 → 버전 확보
    new_ver: str | None = None
    if new_strategy_games:
        try:
            new_ver = apply_strategy_adjustment(new_strategy_games) or None
            if new_ver:
                click.echo(f"[반성] 전략 배분 자동 조정 완료: {new_strategy_games} → model_version {new_ver}")
            else:
                click.echo(f"[반성] 전략 배분 변화 없음 (조정값 동일): {new_strategy_games}")
        except Exception as e:
            click.echo(f"[반성] 조정 실패: {e}")
    else:
        click.echo("[반성] 데이터 부족으로 조정 보류")

    ev_section = _compute_ev_section(db_path, draw, games)

    reflection_text = generate_reflection_text(
        draw_no=draw.draw_no,
        draw_numbers=draw.numbers,
        bonus=draw.bonus,
        games=games_dict,
        perf=perf,
        new_strategy_games=new_strategy_games,
        old_strategy_games=old_strategy_games,
        new_model_version=new_ver,
        ev_section=ev_section,
    )

    save_reflection_report(
        draw_no=draw.draw_no,
        text=reflection_text,
        perf=perf,
        new_strategy_games=new_strategy_games,
        reports_dir=cfg.get("reporter", {}).get("reports_dir", "reports"),
    )

    if send:
        send_message(reflection_text)
        click.echo("반성 리포트 텔레그램 발송 완료.")


def _compute_ev_section(db_path, draw, games) -> str | None:
    """EV 계측: 계산 + ev_metrics 저장 + 반성 리포트 섹션 텍스트.

    실패해도 주간 반성 작업을 깨지 않도록 항상 방어적으로 None 반환.
    (상금 분할 노출 계측일 뿐 당첨 확률과 무관.)
    """
    try:
        from .database import get_all_draws, get_draw
        from .ev_monitor import (
            check_calibration_drift,
            ev_track_record,
            evaluate_recommendation_ev,
            format_ev_section,
            measure_draw_popularity,
            upsert_ev_metric,
        )

        with get_connection(db_path) as conn:
            prev = get_draw(conn, draw.draw_no - 1)
            prev_nums = list(prev.numbers) if prev else None
            ev = evaluate_recommendation_ev(
                games, winning_numbers=draw.numbers, prev_numbers=prev_nums
            )
            winner_ratio = measure_draw_popularity(draw)
            upsert_ev_metric(
                conn,
                draw_no=draw.draw_no,
                portfolio_mean_score=ev["portfolio_mean_score"],
                portfolio_percentile=ev["portfolio_percentile"],
                winning_combo_score=ev["winning_combo_score"],
                winner_ratio=winner_ratio,
            )
            conn.commit()
            history = ev_track_record(conn)
            drift = check_calibration_drift(get_all_draws(conn))
        return format_ev_section(ev, winner_ratio, history, drift)
    except Exception as e:  # noqa: BLE001 — 주간 잡 보호
        click.echo(f"[EV 계측] 계산 생략: {e}")
        return None


@main.command()
@click.option("--min-train", type=int, default=None, help="Minimum training draws")
def backtest(min_train: Optional[int]) -> None:
    """Run walk-forward backtest."""
    from .backtester import run_backtest, generate_backtest_report

    cfg = load_config()
    if min_train:
        cfg["backtester"]["min_train_draws"] = min_train

    db_path = get_db_path(cfg)
    init_db(db_path)

    with get_connection(db_path) as conn:
        draws = get_all_draws(conn)

    if not draws:
        click.echo("No draws in DB. Run `lotto-doctor collect` first.")
        return

    click.echo(f"Running backtest on {len(draws)} draws (min_train={cfg['backtester']['min_train_draws']})...")
    results = run_backtest(draws, cfg)

    with get_connection(db_path) as conn:
        for r in results:
            insert_backtest_run(conn, r)
        conn.commit()

    report_path = cfg["backtester"]["report_path"]
    generate_backtest_report(results, report_path)

    click.echo(f"Backtest complete. {len(results)} draws evaluated.")
    click.echo(f"Report: {report_path}")
    total_3 = sum(r.matched_3 for r in results)
    total_4 = sum(r.matched_4 for r in results)
    click.echo(f"3개 적중 게임: {total_3}, 4개 적중 게임: {total_4}")


@main.command()
@click.option("--target-draw-no", type=int, required=True, help="Draw number to resend")
def resend(target_draw_no: int) -> None:
    """Resend recommendation for a specific draw number via Telegram."""
    from .telegram_bot import build_recommendation_message, send_message

    cfg = load_config()
    db_path = get_db_path(cfg)
    init_db(db_path)

    with get_connection(db_path) as conn:
        from .database import get_recommendation_runs_for_draw
        runs = get_recommendation_runs_for_draw(conn, target_draw_no)
        if not runs:
            click.echo(f"No recommendation runs for draw #{target_draw_no}.")
            return
        run_id = runs[0]["id"]
        games = get_games_for_run(conn, run_id)
        candidates = get_candidate_numbers(conn, run_id)

    top_nums = [(c.number, c.score) for c in candidates]
    summary = {"대상 회차": target_draw_no, "모델": runs[0]["model_name"]}
    msg = build_recommendation_message(target_draw_no, top_nums, games, summary)
    send_message(msg)
    click.echo(f"Resent recommendation for draw #{target_draw_no}.")


# ---------------------------------------------------------------------------
# Pension Lottery 720+ commands
# ---------------------------------------------------------------------------

@main.group()
def pension() -> None:
    """연금복권720+ analysis and recommendation commands."""


@pension.command("collect")
@click.argument("csv_path")
def pension_collect(csv_path: str) -> None:
    """Import pension lottery draw data from CSV file.

    CSV format: 회차,추첨일,조,번호
    Download from https://dhlottery.co.kr (연금복권720+ 당첨번호 조회)
    """
    from .pension_collector import load_pension_csv
    from .pension_database import init_pension_db, upsert_pension_draw
    from .database import get_connection

    cfg = load_config()
    db_path = get_db_path(cfg)
    init_pension_db(db_path)

    draws = load_pension_csv(csv_path)
    if not draws:
        click.echo("CSV에서 데이터를 읽지 못했습니다. 형식을 확인하세요.")
        return

    with get_connection(db_path) as conn:
        for draw in draws:
            upsert_pension_draw(conn, draw)
        conn.commit()

    click.echo(f"저장 완료: {len(draws)}회차 → {db_path}")
    click.echo(f"  최신 회차: {draws[-1].draw_no} ({draws[-1].draw_date})")


@pension.command("collect-auto")
@click.option("--min-agreement", type=int, default=2, help="교차검증에 필요한 최소 일치 기사 수")
def pension_collect_auto(min_agreement: int) -> None:
    """구글 뉴스 검색으로 최신 연금복권720+ 당첨번호를 자동 수집한다.

    dhlottery.co.kr 직접 수집은 봇 차단으로 불가능하므로, 추첨 직후 보도되는
    언론사 기사 제목을 교차검증하여 당첨번호를 추출한다.
    """
    from .pension_news_collector import fetch_latest_pension_draw_from_news
    from .pension_database import init_pension_db, upsert_pension_draw, get_pension_draw

    cfg = load_config()
    db_path = get_db_path(cfg)
    init_pension_db(db_path)

    draw = fetch_latest_pension_draw_from_news(min_agreement=min_agreement)
    if draw is None:
        click.echo("뉴스 교차검증 실패: 신뢰할 수 있는 당첨번호를 찾지 못했습니다.")
        click.echo("(회차가 아직 보도되지 않았거나 언론사 표기가 일치하지 않음)")
        return

    with get_connection(db_path) as conn:
        existing = get_pension_draw(conn, draw.draw_no)
        upsert_pension_draw(conn, draw)
        conn.commit()

    status = "갱신" if existing else "신규 저장"
    click.echo(f"{status} 완료: 제{draw.draw_no}회 {draw.jo}조 {draw.number} ({draw.draw_date})")


@pension.command("backfill")
@click.option("--count", type=int, default=20, help="백필할 과거 회차 수")
@click.option("--delay", type=float, default=1.0, help="요청 간 대기 시간(초)")
def pension_backfill(count: int, delay: float) -> None:
    """뉴스 검색으로 과거 회차를 회차별 개별 조회하여 통계 신뢰도를 높인다."""
    from .pension_news_collector import backfill_pension_history
    from .pension_database import (
        init_pension_db, get_latest_pension_draw_no, upsert_pension_draw,
    )

    cfg = load_config()
    db_path = get_db_path(cfg)
    init_pension_db(db_path)

    with get_connection(db_path) as conn:
        latest = get_latest_pension_draw_no(conn)

    if not latest:
        click.echo("기준이 될 최신 회차가 없습니다. 먼저 pension collect-auto를 실행하세요.")
        return

    click.echo(f"제{latest}회 기준 과거 {count}개 회차 백필 중...")
    draws = backfill_pension_history(latest, count=count, delay_sec=delay)

    with get_connection(db_path) as conn:
        for draw in draws:
            upsert_pension_draw(conn, draw)
        conn.commit()

    click.echo(f"백필 완료: {len(draws)}/{count}건 저장")
    for d in sorted(draws, key=lambda x: x.draw_no):
        click.echo(f"  제{d.draw_no}회 {d.jo}조 {d.number} ({d.draw_date})")


@pension.command("recommend")
@click.option("--send", is_flag=True, default=False, help="Send via Telegram")
@click.option("--draw-no", type=int, default=None, help="Target draw number (default: latest+1)")
def pension_recommend(send: bool, draw_no: Optional[int]) -> None:
    """Generate pension lottery 720+ recommendations."""
    from .pension_database import (
        init_pension_db, get_all_pension_draws, get_latest_pension_draw_no,
        insert_pension_run, insert_pension_game,
    )
    from .pension_generator import generate_pension_portfolio
    from .pension_models import PensionRecommendationRun
    from .pension_telegram import build_pension_recommendation_message
    from .telegram_bot import send_message
    from .database import get_connection

    cfg = load_config()
    db_path = get_db_path(cfg)
    init_pension_db(db_path)

    with get_connection(db_path) as conn:
        draws = get_all_pension_draws(conn)
        db_latest = get_latest_pension_draw_no(conn)

    if not draws:
        msg = (
            "데이터 없음. CSV로 먼저 수집하세요: lotto-doctor pension collect <file.csv>"
        )
        click.echo(msg)
        if send:
            send_message(
                "⚠️ 연금복권720+ 추천 실패\n\n"
                "당첨번호 데이터가 아직 없습니다.\n"
                "dhlottery.co.kr 자동 수집이 차단되어 있어 CSV 수동 임포트가 필요합니다.\n"
                "(lotto-doctor pension collect <file.csv>)"
            )
        return

    if draw_no is None:
        draw_no = (db_latest or 0) + 1

    run = PensionRecommendationRun(
        draw_no=draw_no,
        model_version="pension-v1.0.0",
        seed=draw_no,
    )

    with get_connection(db_path) as conn:
        run_id = insert_pension_run(conn, run)
        conn.commit()

    games = generate_pension_portfolio(draws, cfg, seed=draw_no, run_id=run_id)

    with get_connection(db_path) as conn:
        for game in games:
            insert_pension_game(conn, game)
        conn.commit()

    click.echo(f"\n제{draw_no}회 연금복권720+ 추천:")
    for g in games:
        click.echo(f"  [{g.game_label}] [{g.strategy}] {g.jo}조 - {g.number}")

    if send:
        from datetime import datetime, timedelta
        draw_date = ""
        with get_connection(db_path) as conn:
            prev = conn.execute(
                "SELECT draw_date FROM pension_draws WHERE draw_no=? LIMIT 1", (draw_no - 1,)
            ).fetchone()
        if prev and prev[0]:
            try:
                d = datetime.strptime(str(prev[0]), "%Y-%m-%d") + timedelta(days=7)
                draw_date = d.strftime("%Y년 %m월 %d일")
            except Exception:
                pass
        msg = build_pension_recommendation_message(draw_no, games, draw_date)
        send_message(msg)
        click.echo("Telegram message sent.")


@pension.command("check-result")
@click.option("--send", is_flag=True, default=False, help="Send results via Telegram")
@click.option("--draw-no", type=int, default=None, help="Draw number to evaluate")
def pension_check_result(send: bool, draw_no: Optional[int]) -> None:
    """Evaluate pension lottery recommendations against actual draw result."""
    from .pension_database import (
        init_pension_db, get_latest_pension_run, get_pension_draw,
        get_pension_games_for_run, insert_pension_evaluation,
    )
    from .pension_evaluator import evaluate_pension_run
    from .pension_telegram import build_pension_result_message
    from .telegram_bot import send_message
    from .database import get_connection

    cfg = load_config()
    db_path = get_db_path(cfg)
    init_pension_db(db_path)

    with get_connection(db_path) as conn:
        run_info = get_latest_pension_run(conn)
        if run_info is None:
            click.echo("추천 기록 없음. pension recommend 먼저 실행하세요.")
            return

        target_draw_no = draw_no or run_info["draw_no"]
        draw = get_pension_draw(conn, target_draw_no)
        if draw is None:
            click.echo(f"제{target_draw_no}회 결과 없음. CSV로 수집 후 재시도하세요.")
            return

        games = get_pension_games_for_run(conn, run_info["id"])
        if not games:
            click.echo(f"추천 게임 없음 (run_id={run_info['id']}).")
            return

        results = evaluate_pension_run(games, draw)
        for result in results:
            insert_pension_evaluation(conn, result)
        conn.commit()

    click.echo(f"\n제{target_draw_no}회 당첨번호: {draw.jo}조 - {draw.number}")
    click.echo("\n결과:")
    for g, r in zip(games, results):
        jo_note = "조✓" if r.jo_match else "조✗"
        click.echo(f"  [{g.game_label}] {g.jo}조-{g.number} ({jo_note}, 뒤{r.matched_suffix}자리) → {r.prize_rank}")

    if send:
        msg = build_pension_result_message(draw, games, results)
        send_message(msg)
        click.echo("Telegram message sent.")


@pension.command("sample-csv")
@click.option("--out", default="data/pension_sample.csv", help="Output path")
def pension_sample_csv(out: str) -> None:
    """Generate a sample CSV template for pension lottery data entry."""
    from .pension_collector import generate_sample_csv
    generate_sample_csv(out)
    click.echo(f"샘플 CSV 생성: {out}")
    click.echo("이 파일에 연금복권720+ 당첨번호를 입력 후 'pension collect' 명령으로 로드하세요.")
