from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


PT_MONTHS = {
    "janeiro": "01",
    "fevereiro": "02",
    "março": "03",
    "marco": "03",
    "abril": "04",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "agosto": "08",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [normalize_row(row) for row in rows]


def normalize_row(row: dict[str, Any]) -> dict[str, str]:
    norma = clean_text(row.get("norma"))
    tipo_ato, numero_ato, ano = parse_norma(norma)

    data_publicacao = normalize_date(row.get("data_publicacao_dou"))
    url = normalize_url(row.get("url_anvisalegis"))

    normalized = {
        "id_norma": "",
        "norma": norma,
        "tipo_ato": tipo_ato,
        "numero_ato": numero_ato,
        "ano": ano,
        "origem": clean_text(row.get("origem_ato")),
        "data_publicacao_dou": data_publicacao,
        "assunto_ementa": clean_text(row.get("assunto_ementa")),
        "status_ato": clean_text(row.get("status_ato")),
        "macrotema": clean_text(row.get("macrotema")),
        "tema_biblioteca": clean_text(row.get("tema_biblioteca")),
        "norma_em_revisao": clean_text(row.get("norma_em_revisao")),
        "processo": clean_text(row.get("processo")),
        "url_anvisalegis": url,
        "hash_registro": "",
        "data_primeira_coleta": "",
        "data_ultima_coleta": "",
        "data_ultima_alteracao": "",
    }

    normalized["id_norma"] = build_id_norma(normalized)
    normalized["hash_registro"] = build_hash_registro(normalized)
    return normalized


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def normalize_url(value: Any) -> str:
    text = clean_text(value)
    if not text or text.lower().startswith("link não identificado"):
        return ""
    if not text.startswith(("http://", "https://")):
        return ""
    return text


def parse_norma(norma: str) -> tuple[str, str, str]:
    """
    Exemplos esperados:
    - RDC nº 568 de 2021
    - IN nº 289 de 2024
    - PRT nº 17 de 1966
    - RES nº 1 de 1977
    """
    text = clean_text(norma)
    pattern = re.compile(
        r"^\s*(?P<tipo>[A-Z]{2,5})\s+n[ºo°]?\s*(?P<num>[0-9.]+)\s*(?:de|/)\s*(?P<ano>\d{4})",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return "", "", ""

    tipo = match.group("tipo").upper()
    numero = match.group("num").replace(".", "").lstrip("0") or "0"
    ano = match.group("ano")
    return tipo, numero, ano


def normalize_date(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()

    text = clean_text(value)
    if not text:
        return ""

    if text.startswith("datetime'") and text.endswith("'"):
        text = text.removeprefix("datetime'").removesuffix("'")

    # ISO datetime ou ISO date.
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if iso_match:
        return iso_match.group(1)

    # Formato Power BI eventualmente serializado como número em string.
    if re.fullmatch(r"\d{11,13}", text):
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc).date().isoformat()

    # Ex.: "sexta-feira, 1 de outubro de 2021"
    normalized = strip_accents(text.lower())
    pt_match = re.search(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", normalized)
    if pt_match:
        day = pt_match.group(1).zfill(2)
        month = PT_MONTHS.get(pt_match.group(2), "")
        year = pt_match.group(3)
        if month:
            return f"{year}-{month}-{day}"

    return text


def strip_accents(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )


def build_id_norma(row: dict[str, str]) -> str:
    tipo = row.get("tipo_ato", "")
    numero = row.get("numero_ato", "")
    ano = row.get("ano", "")

    if tipo and numero and ano:
        return f"{tipo}-{numero}-{ano}"

    fallback = "|".join(
        [
            row.get("norma", ""),
            row.get("data_publicacao_dou", ""),
            row.get("url_anvisalegis", ""),
        ]
    )
    digest = hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:16]
    return f"SEM-ID-{digest}"


def build_hash_registro(row: dict[str, str]) -> str:
    fields = [
        "norma",
        "origem",
        "data_publicacao_dou",
        "assunto_ementa",
        "status_ato",
        "macrotema",
        "tema_biblioteca",
        "norma_em_revisao",
        "processo",
        "url_anvisalegis",
    ]
    payload = "|".join(row.get(field, "") for field in fields)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
