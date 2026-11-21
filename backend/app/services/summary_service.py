"""시계열 분석 — 요약(프롬프트 주입용)과 확장 통계(보너스)."""
from __future__ import annotations

import statistics as st
from collections import Counter, defaultdict
from datetime import date as Date, timedelta

from ..config import settings

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
TREND_WINDOW = 14          # 최근 N일 vs 직전 N일 비교
TREND_THRESHOLD = 5.0      # ±5% 이내면 '유지'


def _r(x: float, n: int = 2) -> float:
    return round(float(x), n)


def _avg(values: list[float]) -> float | None:
    return _r(sum(values) / len(values)) if values else None


def compute_trend(items: list[dict]) -> tuple[str, float | None, float | None]:
    """마지막 날짜 기준 최근 14일 평균과 그 직전 14일 평균을 비교."""
    if not items:
        return "데이터 없음", None, None
    last = Date.fromisoformat(items[-1]["date"])
    recent_from = last - timedelta(days=TREND_WINDOW - 1)
    prev_from = recent_from - timedelta(days=TREND_WINDOW)
    recent = [i["value"] for i in items if Date.fromisoformat(i["date"]) >= recent_from]
    prev = [i["value"] for i in items
            if prev_from <= Date.fromisoformat(i["date"]) < recent_from]
    r_avg, p_avg = _avg(recent), _avg(prev)
    if r_avg is None or p_avg is None:
        return "판단 불가 (비교 기간 데이터 부족)", r_avg, p_avg
    if p_avg == 0:
        return ("상승 (직전 기간 0)" if r_avg > 0 else "유지"), r_avg, p_avg
    change = (r_avg - p_avg) / p_avg * 100
    if change > TREND_THRESHOLD:
        label = "상승"
    elif change < -TREND_THRESHOLD:
        label = "하락"
    else:
        label = "유지"
    return f"{label} (최근 {TREND_WINDOW}일 평균 {change:+.1f}%)", r_avg, p_avg


def compute_summary(items: list[dict]) -> dict:
    """items 는 날짜 오름차순 정렬된 data 문서 목록."""
    if not items:
        return {"period": "데이터 없음", "count": 0, "metrics": None, "trend": "데이터 없음",
                "recent_average": None, "previous_average": None, "unit": settings.data_unit}
    values = [float(i["value"]) for i in items]
    max_item = max(items, key=lambda i: i["value"])
    min_item = min(items, key=lambda i: i["value"])
    trend, r_avg, p_avg = compute_trend(items)
    return {
        "period": f"{items[0]['date']} ~ {items[-1]['date']}",
        "count": len(items),
        "metrics": {
            "total": _r(sum(values)),
            "average": _r(st.mean(values)),
            "max": _r(max_item["value"]),
            "min": _r(min_item["value"]),
            "max_date": max_item["date"],
            "min_date": min_item["date"],
        },
        "trend": trend,
        "recent_average": r_avg,
        "previous_average": p_avg,
        "unit": settings.data_unit,
    }


def _longest_streak(items: list[dict]) -> int:
    active_dates = sorted({Date.fromisoformat(i["date"]) for i in items if i["value"] > 0})
    best = cur = 0
    prev = None
    for d in active_dates:
        cur = cur + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, cur)
        prev = d
    return best


def compute_statistics(items: list[dict]) -> dict:
    values = [float(i["value"]) for i in items]
    weekday: dict[str, list[float]] = defaultdict(list)
    monthly: dict[str, list[float]] = defaultdict(list)
    memo_counter: Counter = Counter()
    memo_total: dict[str, float] = defaultdict(float)
    for i in items:
        d = Date.fromisoformat(i["date"])
        weekday[WEEKDAYS[d.weekday()]].append(i["value"])
        monthly[i["date"][:7]].append(i["value"])
        memo = (i.get("memo") or "").strip()
        if memo:
            memo_counter[memo] += 1
            memo_total[memo] += i["value"]

    ma7 = []
    for idx in range(len(items)):
        window = values[max(0, idx - 6): idx + 1]
        ma7.append({"date": items[idx]["date"], "value": items[idx]["value"],
                    "ma7": _r(sum(window) / len(window))})

    return {
        "count": len(values),
        "median": _r(st.median(values)) if values else None,
        "std": _r(st.stdev(values)) if len(values) > 1 else None,
        "active_ratio": _r(sum(v > 0 for v in values) / len(values), 3) if values else None,
        "longest_streak": _longest_streak(items),
        "weekday_average": {w: _r(st.mean(weekday[w])) for w in WEEKDAYS if weekday[w]},
        "monthly": [{"month": m, "count": len(v), "total": _r(sum(v)), "average": _r(st.mean(v))}
                    for m, v in sorted(monthly.items())],
        "moving_average_7": ma7,
        "top_memos": [{"memo": m, "count": c, "total": _r(memo_total[m])}
                      for m, c in memo_counter.most_common(5)],
    }


def summary_to_prompt(summary: dict) -> str:
    """요약 dict → 시스템 프롬프트에 그대로 삽입할 텍스트 블록."""
    unit = summary.get("unit", "")
    m = summary.get("metrics")
    if m:
        metrics = (f"합계 {m['total']}{unit}, 평균 {m['average']}{unit}, "
                   f"최대 {m['max']}{unit}({m['max_date']}), 최소 {m['min']}{unit}({m['min_date']})")
    else:
        metrics = "없음"
    return (
        f"- 데이터 종류: {settings.data_label} (단위: {unit})\n"
        f"- 데이터 기간: {summary['period']}\n"
        f"- 총 레코드: {summary['count']}개\n"
        f"- 주요 지표: {metrics}\n"
        f"- 최근 트렌드: {summary['trend']} "
        f"(최근 14일 평균 {summary.get('recent_average')}{unit}, 직전 14일 평균 {summary.get('previous_average')}{unit})"
    )
