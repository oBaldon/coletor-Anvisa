# coletor-Anvisa

Coletor de normas da ANVISA a partir do painel público Power BI "Painel de Gestão do Estoque Regulatório".

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

Coletar e salvar JSON decodificado:

```bash
python -m src.cli collect
```

Executar rotina completa:

```bash
python -m src.cli run-daily
```

Gerar arquivos consumidos pelo RAG:

```bash
python -m src.cli export-urls
```

Saídas principais:

- `data/normas.csv`
- `data/urls_anvisa.txt`
- `data/url.env`

## Observação regulatória

Este coletor cria uma camada de ingestão e indexação. A validação normativa final deve ser feita contra as fontes oficiais e por especialista regulatório.
