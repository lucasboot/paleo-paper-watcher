# paleo-paper-watcher

Projeto pessoal em Python para monitorar diariamente novos artigos científicos sobre Paleopalinologia/Palaeopalynology, com execução via GitHub Actions e notificações por Telegram.

## Estrutura

- `main.py`: executa todas as fontes habilitadas para todas as queries.
- `src/config.py`: carregamento e validação de `config.yaml`.
- `src/models.py`: modelos Pydantic do domínio.
- `src/normalize.py`: normalização de título e geração de chave de deduplicação.
- `src/sources/`: integrações reais com OpenAlex, Crossref, Semantic Scholar e arXiv.
- `src/notify/`: integrações de notificação.
- `data/seen.json`: persistência simples para evitar alertas duplicados.

## Requisitos

- Python 3.12

## Instalação

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Execução

```bash
python main.py
```

O script consulta todas as fontes habilitadas em `config.yaml`, agrega os resultados, remove duplicados por DOI/`external_id`/título normalizado e imprime `title | source | published_date | url`.

## Configuração

Cada fonte pode ser habilitada e ajustada separadamente:

```yaml
sources:
  openalex:
    enabled: true
    lookback_days: 30
    max_results: 25
```

`Semantic Scholar` aceita a variável de ambiente opcional `SEMANTIC_SCHOLAR_API_KEY`.
