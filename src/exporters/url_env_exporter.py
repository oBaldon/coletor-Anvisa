from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass
class ExportResult:
    urls_count: int
    urls_path: str
    env_path: str


def export_urls_for_rag(
    csv_path: str | Path = "data/normas.csv",
    urls_path: str | Path = "data/urls_anvisa.txt",
    env_path: str | Path = "data/url.env",
    only_status: str | None = None,
    only_macrotema: str | None = None,
) -> ExportResult:
    csv_path = Path(csv_path)
    urls_path = Path(urls_path)
    env_path = Path(env_path)

    urls: list[str] = []

    if csv_path.exists() and csv_path.stat().st_size > 0:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if only_status and row.get("status_ato") != only_status:
                    continue
                if only_macrotema and row.get("macrotema") != only_macrotema:
                    continue

                url = (row.get("url_anvisalegis") or "").strip()
                if url.startswith(("http://", "https://")):
                    urls.append(url)

    urls = sorted(set(urls))
    urls_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    urls_path.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")

    now = datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")
    env_content = "\n".join(
        [
            f"ANVISA_NORMAS_CSV_PATH={csv_path}",
            f"ANVISA_NORMAS_URLS_PATH={urls_path}",
            "ANVISA_NORMAS_SOURCE=powerbi_anvisa_normas",
            f"ANVISA_NORMAS_LAST_UPDATE={now}",
            f"ANVISA_NORMAS_URLS_COUNT={len(urls)}",
            "",
        ]
    )
    env_path.write_text(env_content, encoding="utf-8")

    return ExportResult(
        urls_count=len(urls),
        urls_path=str(urls_path),
        env_path=str(env_path),
    )
