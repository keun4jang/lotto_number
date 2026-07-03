"""CLI entry points for Lotto Doctor."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from .config import get_db_path, load_config
from .database import (
    get_all_draws,
    get_all_evaluation_results,
    get_games_for_run,
    get_latest_draw_no,
    get_latest_recommendation_run,
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
def recommend(send: bool, draw_no: Optional[int]) -> None:
    """Generate recommendations and optionally send via Telegram."""
    from .portfolio import build_portfolio
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

    seed = draw_no
    model_name = cfg["app"]["model_name"]
    model_version = cfg["app"]["model_version"]

    click.echo(f"Generating recommendations for draw #{draw_no} (seed={seed})...")

    run = RecommendationRun(
        draw_no=draw_no,
        model_name=model_name,
        model_version=model_version,
        seed=seed,
    )

    with get_connection(db_path) as conn:
        run_id = insert_recommendation_run(conn, run)
        conn.commit()

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

    top_nums = [(c.number, c.score) for c in candidate_numbers]
    save_recommendation_csv(games, draw_no, cfg)
    save_recommendation_markdown(games, top_nums, draw_no, cfg)

    click.echo(f"\n후보번호 TOP 10: {', '.join(str(c.number) for c in candidate_numbers)}")
    click.echo(f"\n추천 {len(games)}게임:")
    for g in games:
        nums_str = " - ".join(f"{n:02d}" for n in g.numbers)
        click.echo(f"  {g.game_label}: [{g.strategy}] {nums_str}")

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

    reflection_text = generate_reflection_text(
        draw_no=draw.draw_no,
        draw_numbers=draw.numbers,
        bonus=draw.bonus,
        games=games_dict,
        perf=perf,
        new_strategy_games=new_strategy_games,
    )

    save_reflection_report(
        draw_no=draw.draw_no,
        text=reflection_text,
        perf=perf,
        new_strategy_games=new_strategy_games,
        reports_dir=cfg.get("reporter", {}).get("reports_dir", "reports"),
    )

    # 성과 기반 자동 조정 적용
    if new_strategy_games:
        try:
            apply_strategy_adjustment(new_strategy_games)
            click.echo(f"[반성] 전략 배분 자동 조정 완료: {new_strategy_games}")
        except Exception as e:
            click.echo(f"[반성] 조정 실패: {e}")
    else:
        click.echo("[반성] 데이터 부족으로 조정 보류")

    if send:
        send_message(reflection_text)
        click.echo("반성 리포트 텔레그램 발송 완료.")


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
