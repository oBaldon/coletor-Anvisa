from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExportEntry:
    group: str
    variable_name: str
    url: str
    sort_key: tuple[int, str]


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
    exports: list[ExportEntry] = []
    seen_urls: set[str] = set()
    used_variable_names: dict[str, int] = {}

    if csv_path.exists() and csv_path.stat().st_size > 0:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if only_status and row.get("status_ato") != only_status:
                    continue
                if only_macrotema and row.get("macrotema") != only_macrotema:
                    continue

                url = (row.get("url_anvisalegis") or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue

                urls.append(url)
                if url in seen_urls:
                    continue

                seen_urls.add(url)
                exports.append(
                    ExportEntry(
                        group=clean_group_name(row.get("macrotema")),
                        variable_name=build_variable_name(
                            row.get("numero_ato"),
                            used_variable_names,
                        ),
                        url=url,
                        sort_key=build_sort_key(row.get("numero_ato"), url),
                    )
                )

    urls = sorted(set(urls))
    urls_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    urls_path.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
    env_path.write_text(build_env_content(exports), encoding="utf-8")

    return ExportResult(
        urls_count=len(urls),
        urls_path=str(urls_path),
        env_path=str(env_path),
    )


def build_env_content(entries: list[ExportEntry]) -> str:
    if not entries:
        return ""

    lines: list[str] = []
    current_group: str | None = None

    for entry in sorted(
        entries,
        key=lambda item: (item.group.lower(), item.sort_key, item.variable_name),
    ):
        if entry.group != current_group:
            if lines:
                lines.append("")
            lines.append(f"# {entry.group}")
            current_group = entry.group

        lines.append(f'export {entry.variable_name}="{entry.url}"')

    lines.append("")
    return "\n".join(lines)


def clean_group_name(value: str | None) -> str:
    text = (value or "").strip()
    return text if text else "Sem macrotema"


def build_variable_name(
    numero_ato: str | None,
    used_variable_names: dict[str, int],
) -> str:
    raw_number = (numero_ato or "").strip().lstrip("0") or "0"
    base_name = f"URL_{raw_number}"
    count = used_variable_names.get(base_name, 0)
    used_variable_names[base_name] = count + 1

    if count == 0:
        return base_name

    return f"{base_name}_{count + 1}"


def build_sort_key(numero_ato: str | None, url: str) -> tuple[int, str]:
    cleaned = (numero_ato or "").strip().lstrip("0") or "0"
    if cleaned.isdigit():
        return int(cleaned), url

    return 10**12, url
