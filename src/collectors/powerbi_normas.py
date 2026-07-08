from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import requests


@dataclass(frozen=True)
class PowerBIConfig:
    """
    Configuração pública extraída do relatório Publish to Web da ANVISA.

    Observação: estes identificadores são públicos no embed do Power BI.
    Se a ANVISA republicar o painel, resource_key/model_id/report_id/visual_id podem mudar.
    """

    resource_key: str = "66ecdeda-4007-4d40-85da-45d43dd53fe5"
    querydata_url: str = (
        "https://wabi-brazil-south-api.analysis.windows.net/"
        "public/reports/querydata?synchronous=true"
    )
    model_id: int = 4706243
    dataset_id: str = "cac72255-de00-437c-bd13-cddc5a4f9556"
    report_id: str = "dd3627d2-358f-4836-acd9-f81187bd409b"
    visual_id: str = "173dbad307e2881b20c2"
    page_size: int = 500
    timeout_seconds: int = 60


COLUMN_MAP = {
    "COMPLETA.Identificador da Norma": "norma",
    "COMPLETA.Norma": "norma",
    "COMPLETA.Assunto/Ementa": "assunto_ementa",
    "COMPLETA.Macrotema": "macrotema",
    "COMPLETA.Tema Biblioteca": "tema_biblioteca",
    "COMPLETA.Status do Ato": "status_ato",
    "COMPLETA.Norma em revisão? Sim/Não": "norma_em_revisao",
    "COMPLETA.Processo": "processo",
    "COMPLETA.Data de Publicação(DOU)": "data_publicacao_dou",
    "COMPLETA.Origem do ato": "origem_ato",
    "COMPLETA.Link para página do portal": "url_anvisalegis",
    "Min(COMPLETA.Link para página do portal)": "url_anvisalegis_min",
}


class PowerBIDecodeError(RuntimeError):
    pass


class PowerBINormasCollector:
    def __init__(self, config: PowerBIConfig | None = None) -> None:
        self.config = config or PowerBIConfig()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": "https://app.powerbi.com",
                "Referer": "https://app.powerbi.com/",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "X-PowerBI-ResourceKey": self.config.resource_key,
            }
        )

    def collect_all(
        self,
        max_pages: int = 100,
        sleep_seconds: float = 0.3,
        raw_dir: str | Path | None = "data/raw",
    ) -> list[dict[str, Any]]:
        """
        Coleta todas as páginas da tabela de normas.

        Retorna linhas já decodificadas, mas ainda não normalizadas.
        """
        all_rows: list[dict[str, Any]] = []
        restart_tokens: list[list[Any]] | None = None
        seen_restart_tokens: set[str] = set()

        for page in range(1, max_pages + 1):
            payload = self.build_payload(restart_tokens=restart_tokens)
            response_json = self.fetch_page(payload)

            if raw_dir:
                self._save_raw_response(response_json, raw_dir, page)

            rows = self.decode_response(response_json)
            all_rows.extend(rows)

            restart_tokens = self.extract_restart_tokens(response_json)
            if not restart_tokens:
                break

            token_hash = json.dumps(restart_tokens, ensure_ascii=False, sort_keys=True)
            if token_hash in seen_restart_tokens:
                raise PowerBIDecodeError("Paginação interrompida: RestartTokens repetidos.")
            seen_restart_tokens.add(token_hash)

            if sleep_seconds:
                time.sleep(sleep_seconds)

        return self.deduplicate_rows(all_rows)

    def fetch_page(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.session.headers.update(
            {
                "ActivityId": str(uuid4()),
                "RequestId": str(uuid4()),
            }
        )
        resp = self.session.post(
            self.config.querydata_url,
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def build_payload(self, restart_tokens: list[list[Any]] | None = None) -> dict[str, Any]:
        command = self._base_command()
        window = command["SemanticQueryDataShapeCommand"]["Binding"]["DataReduction"]["Primary"]["Window"]

        if restart_tokens:
            window["RestartTokens"] = restart_tokens

        commands = [command]
        cache_key = json.dumps({"Commands": commands}, ensure_ascii=False, separators=(",", ":"))

        return {
            "version": "1.0.0",
            "queries": [
                {
                    "Query": {"Commands": commands},
                    "CacheKey": cache_key,
                    "QueryId": "",
                    "ApplicationContext": {
                        "DatasetId": self.config.dataset_id,
                        "Sources": [
                            {
                                "ReportId": self.config.report_id,
                                "VisualId": self.config.visual_id,
                            }
                        ],
                    },
                }
            ],
            "cancelQueries": [],
            "modelId": self.config.model_id,
        }

    def _base_command(self) -> dict[str, Any]:
        c = self.config
        select = [
            self._column("Norma", "COMPLETA.Identificador da Norma"),
            self._column("Assunto/Ementa", "COMPLETA.Assunto/Ementa"),
            self._column("Macrotema", "COMPLETA.Macrotema"),
            self._column("Tema Biblioteca", "COMPLETA.Tema Biblioteca"),
            self._column("Status do Ato", "COMPLETA.Status do Ato"),
            self._column("Norma em revisão? Sim/Não", "COMPLETA.Norma em revisão? Sim/Não"),
            self._column("Processo", "COMPLETA.Processo"),
            self._column("Data de Publicação(DOU)", "COMPLETA.Data de Publicação(DOU)"),
            self._column("Origem do ato", "COMPLETA.Origem do ato"),
            self._column("Link para página do portal", "COMPLETA.Link para página do portal"),
            {
                "Aggregation": {
                    "Expression": {
                        "Column": {
                            "Expression": {"SourceRef": {"Source": "c"}},
                            "Property": "Link para página do portal",
                        }
                    },
                    "Function": 3,
                },
                "Name": "Min(COMPLETA.Link para página do portal)",
            },
        ]

        return {
            "SemanticQueryDataShapeCommand": {
                "Query": {
                    "Version": 2,
                    "From": [{"Name": "c", "Entity": "COMPLETA", "Type": 0}],
                    "Select": select,
                    "Where": [
                        {
                            "Condition": {
                                "Not": {
                                    "Expression": {
                                        "In": {
                                            "Expressions": [
                                                {
                                                    "Column": {
                                                        "Expression": {"SourceRef": {"Source": "c"}},
                                                        "Property": "Status do Ato",
                                                    }
                                                }
                                            ],
                                            "Values": [[{"Literal": {"Value": "'Não identificado'"}}]],
                                        }
                                    }
                                }
                            }
                        },
                        {
                            "Condition": {
                                "In": {
                                    "Expressions": [
                                        {
                                            "Column": {
                                                "Expression": {"SourceRef": {"Source": "c"}},
                                                "Property": "Tipo de Ato",
                                            }
                                        }
                                    ],
                                    "Values": [
                                        [{"Literal": {"Value": "'IN'"}}],
                                        [{"Literal": {"Value": "'INC'"}}],
                                        [{"Literal": {"Value": "'PRT'"}}],
                                        [{"Literal": {"Value": "'PRTC'"}}],
                                        [{"Literal": {"Value": "'RDC'"}}],
                                        [{"Literal": {"Value": "'RE'"}}],
                                        [{"Literal": {"Value": "'RES'"}}],
                                    ],
                                }
                            }
                        },
                    ],
                    "OrderBy": [
                        {
                            "Direction": 1,
                            "Expression": {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "c"}},
                                    "Property": "Data de Publicação(DOU)",
                                }
                            },
                        }
                    ],
                },
                "Binding": {
                    "Primary": {"Groupings": [{"Projections": list(range(len(select)))}]},
                    "DataReduction": {
                        "DataVolume": 3,
                        "Primary": {"Window": {"Count": c.page_size}},
                    },
                    "SuppressedJoinPredicates": [10],
                    "Version": 1,
                },
                "ExecutionMetricsKind": 1,
            }
        }

    @staticmethod
    def _column(property_name: str, alias: str) -> dict[str, Any]:
        return {
            "Column": {
                "Expression": {"SourceRef": {"Source": "c"}},
                "Property": property_name,
            },
            "Name": alias,
        }

    def decode_response(self, response_json: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            data = response_json["results"][0]["result"]["data"]
            descriptor = data["descriptor"]
            ds = data["dsr"]["DS"][0]
            rows = ds["PH"][0]["DM0"]
        except (KeyError, IndexError, TypeError) as exc:
            raise PowerBIDecodeError("Resposta Power BI sem estrutura DSR esperada.") from exc

        select_names = [item["Name"] for item in descriptor["Select"]]
        output_names = [COLUMN_MAP.get(name, name) for name in select_names]

        value_dicts = ds.get("ValueDicts", {})
        schema: list[dict[str, Any]] | None = None
        previous: list[Any] = [None] * len(output_names)
        decoded_rows: list[dict[str, Any]] = []

        for compressed_row in rows:
            if "S" in compressed_row:
                schema = compressed_row["S"]

            if schema is None:
                raise PowerBIDecodeError("Linha DSR sem schema inicial.")

            values = self._decode_compressed_row(
                compressed_row=compressed_row,
                schema=schema,
                value_dicts=value_dicts,
                previous=previous,
                expected_len=len(output_names),
            )
            previous = values

            row_dict = dict(zip(output_names, values))
            # A coluna agregada Min(...) repete o link. Mantemos apenas a URL principal.
            row_dict.pop("url_anvisalegis_min", None)
            decoded_rows.append(row_dict)

        return decoded_rows

    def _decode_compressed_row(
        self,
        compressed_row: dict[str, Any],
        schema: list[dict[str, Any]],
        value_dicts: dict[str, list[Any]],
        previous: list[Any],
        expected_len: int,
    ) -> list[Any]:
        raw_values = compressed_row.get("C", [])
        repeat_mask = int(compressed_row.get("R", 0) or 0)
        null_mask = int(compressed_row.get("Ø", 0) or 0)

        decoded: list[Any] = []
        cursor = 0

        for idx in range(expected_len):
            is_repeated = bool(repeat_mask & (1 << idx))
            is_null = bool(null_mask & (1 << idx))

            if is_repeated:
                decoded.append(previous[idx] if idx < len(previous) else None)
                continue

            if is_null:
                decoded.append(None)
                continue

            if cursor >= len(raw_values):
                decoded.append(None)
                continue

            raw = raw_values[cursor]
            cursor += 1

            schema_item = schema[idx] if idx < len(schema) else {}
            decoded.append(self._decode_cell(raw, schema_item, value_dicts))

        return decoded

    @staticmethod
    def _decode_cell(raw: Any, schema_item: dict[str, Any], value_dicts: dict[str, list[Any]]) -> Any:
        dict_name = schema_item.get("DN")
        if dict_name and isinstance(raw, int):
            dict_values = value_dicts.get(dict_name, [])
            if 0 <= raw < len(dict_values):
                return dict_values[raw]

        if schema_item.get("T") == 7 and isinstance(raw, (int, float)):
            # Datas podem vir como epoch em milissegundos.
            return datetime.fromtimestamp(raw / 1000, tz=timezone.utc).date().isoformat()

        return raw

    @staticmethod
    def extract_restart_tokens(response_json: dict[str, Any]) -> list[list[Any]] | None:
        try:
            ds = response_json["results"][0]["result"]["data"]["dsr"]["DS"][0]
        except (KeyError, IndexError, TypeError):
            return None

        restart_tokens = ds.get("RT")
        return restart_tokens if restart_tokens else None

    @staticmethod
    def deduplicate_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []

        for row in rows:
            key_parts = [
                str(row.get("norma") or "").strip(),
                str(row.get("data_publicacao_dou") or "").strip(),
                str(row.get("url_anvisalegis") or "").strip(),
            ]
            key = "||".join(key_parts)
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)

        return unique

    @staticmethod
    def _save_raw_response(response_json: dict[str, Any], raw_dir: str | Path, page: int) -> None:
        raw_path = Path(raw_dir)
        raw_path.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        file_path = raw_path / f"powerbi_normas_page_{page:03d}_{stamp}.json"
        file_path.write_text(json.dumps(response_json, ensure_ascii=False, indent=2), encoding="utf-8")
