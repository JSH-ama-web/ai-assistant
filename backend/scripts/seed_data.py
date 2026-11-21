"""CSV 시계열 데이터를 Firestore `data` 컬렉션에 업로드한다.

사용법 (backend 폴더에서):
    python scripts/seed_data.py                      # data/workout_log.csv 업로드
    python scripts/seed_data.py --csv my.csv         # 내 CSV 업로드 (헤더: date,value,memo)
    python scripts/seed_data.py --reset              # 기존 data 문서 삭제 후 업로드
    python scripts/seed_data.py --dry-run            # 업로드 없이 검증 + 요약만 출력

CSV 를 Pydantic(DataCreate)으로 한 줄씩 검증하므로 잘못된 행은 건너뛰고 알려 준다.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from app.schemas import DataCreate  # noqa: E402


def load_rows(path: Path) -> list[DataCreate]:
    rows, errors = [], 0
    with path.open(encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(csv.DictReader(f), start=2):
            try:
                rows.append(DataCreate(date=raw["date"], value=float(raw["value"]),
                                       memo=raw.get("memo") or ""))
            except (ValidationError, ValueError, KeyError) as exc:
                errors += 1
                print(f"  ! {line_no}행 건너뜀: {exc}".splitlines()[0])
    print(f"검증 완료: 유효 {len(rows)}행, 오류 {errors}행")
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=str(ROOT / "data" / "workout_log.csv"))
    p.add_argument("--reset", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    rows = load_rows(Path(a.csv))
    if len(rows) < 100:
        print(f"경고: 데이터가 {len(rows)}개입니다 (과제 요구: 100개 이상).")

    from app.services.summary_service import compute_summary
    preview = [{"date": r.date.isoformat(), "value": r.value, "memo": r.memo}
               for r in sorted(rows, key=lambda r: r.date)]
    print("요약 미리보기:", json.dumps(compute_summary(preview), ensure_ascii=False, indent=2))
    if a.dry_run:
        return

    from app.database import DATA_COLLECTION, get_repo
    from app.services.data_service import create_data
    repo = get_repo()
    if a.reset:
        existing = repo.list(DATA_COLLECTION)
        for doc in existing:
            repo.delete(DATA_COLLECTION, doc["id"])
        print(f"기존 {len(existing)}건 삭제")
    for i, r in enumerate(rows, 1):
        create_data(repo, r)
        if i % 25 == 0:
            print(f"  업로드 {i}/{len(rows)}")
    print(f"완료: {len(rows)}건 업로드")


if __name__ == "__main__":
    main()
