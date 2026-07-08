from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


CSV_COLUMNS = [
    "id_norma",
    "norma",
    "tipo_ato",
    "numero_ato",
    "ano",
    "origem",
    "data_publicacao_dou",
    "assunto_ementa",
    "status_ato",
    "macrotema",
    "tema_biblioteca",
    "norma_em_revisao",
    "processo",
    "url_anvisalegis",
    "hash_registro",
    "data_primeira_coleta",
    "data_ultima_coleta",
    "data_ultima_alteracao",
]


@dataclass
class UpsertResult:
    total_recebidas: int
    total_csv: int
    inseridas: int
    atualizadas: int
    inalteradas: int
    csv_path: str


class CsvNormasRepository:
    def __init__(self, csv_path: str | Path = "data/normas.csv") -> None:
        self.csv_path = Path(csv_path)

    def upsert(self, rows: list[dict[str, str]]) -> UpsertResult:
        existing = self.read_all()
        index = {self._key(row): row for row in existing if self._key(row)}
        now = self._now()

        inserted = updated = unchanged = 0
        incoming_unique: dict[str, dict[str, str]] = {}

        for row in rows:
            key = self._key(row)
            if not key:
                continue
            incoming_unique[key] = row

        for key, row in incoming_unique.items():
            clean_row = self._ensure_columns(row)

            if key not in index:
                clean_row["data_primeira_coleta"] = now
                clean_row["data_ultima_coleta"] = now
                clean_row["data_ultima_alteracao"] = now
                index[key] = clean_row
                inserted += 1
                continue

            old = index[key]
            if old.get("hash_registro") != clean_row.get("hash_registro"):
                first_seen = old.get("data_primeira_coleta") or now
                clean_row["data_primeira_coleta"] = first_seen
                clean_row["data_ultima_coleta"] = now
                clean_row["data_ultima_alteracao"] = now
                index[key] = clean_row
                updated += 1
            else:
                old["data_ultima_coleta"] = now
                index[key] = self._ensure_columns(old)
                unchanged += 1

        output_rows = sorted(
            index.values(),
            key=lambda r: (r.get("data_publicacao_dou", ""), r.get("norma", "")),
        )
        self.write_all(output_rows)

        return UpsertResult(
            total_recebidas=len(rows),
            total_csv=len(output_rows),
            inseridas=inserted,
            atualizadas=updated,
            inalteradas=unchanged,
            csv_path=str(self.csv_path),
        )

    def read_all(self) -> list[dict[str, str]]:
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            return []

        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [self._ensure_columns(row) for row in reader]

    def write_all(self, rows: list[dict[str, str]]) -> None:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with self.csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(self._ensure_columns(row))

    @staticmethod
    def _key(row: dict[str, str]) -> str:
        return (
            row.get("id_norma")
            or row.get("url_anvisalegis")
            or row.get("hash_registro")
            or ""
        ).strip()

    @staticmethod
    def _ensure_columns(row: dict[str, str]) -> dict[str, str]:
        return {col: str(row.get(col, "") or "") for col in CSV_COLUMNS}

    @staticmethod
    def _now() -> str:
        return datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")
