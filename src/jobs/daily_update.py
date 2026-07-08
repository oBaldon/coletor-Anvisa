from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.collectors.powerbi_normas import PowerBINormasCollector
from src.exporters.url_env_exporter import ExportResult, export_urls_for_rag
from src.normalizers.normas import normalize_rows
from src.storage.csv_repository import CsvNormasRepository, UpsertResult


@dataclass
class DailyUpdateResult:
    coletadas: int
    normalizadas: int
    csv: UpsertResult
    export: ExportResult | None


def run_daily_update(
    csv_path: str | Path = "data/normas.csv",
    urls_path: str | Path = "data/urls_anvisa.txt",
    env_path: str | Path = "data/url.env",
    raw_dir: str | Path | None = "data/raw",
    max_pages: int = 100,
    export_urls: bool = True,
) -> DailyUpdateResult:
    collector = PowerBINormasCollector()
    raw_rows = collector.collect_all(max_pages=max_pages, raw_dir=raw_dir)
    normalized = normalize_rows(raw_rows)

    repo = CsvNormasRepository(csv_path)
    csv_result = repo.upsert(normalized)

    export_result = None
    if export_urls:
        export_result = export_urls_for_rag(
            csv_path=csv_path,
            urls_path=urls_path,
            env_path=env_path,
        )

    return DailyUpdateResult(
        coletadas=len(raw_rows),
        normalizadas=len(normalized),
        csv=csv_result,
        export=export_result,
    )


def save_decoded_rows(rows: list[dict[str, Any]], out_dir: str | Path = "data/raw") -> Path:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_path = path / f"powerbi_normas_decoded_{stamp}.json"
    file_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path
