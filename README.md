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

O script consulta as fontes habilitadas em `config.yaml`, agrega os resultados, remove duplicados por DOI/`external_id`/titulo normalizado, gera mensagens em blocos e tenta enviar pelo Telegram. Se o Telegram nao estiver configurado, ele imprime as mensagens no terminal.

## Configuração

Cada fonte pode ser habilitada e ajustada separadamente:

```yaml
max_results_per_source: 20
languages_priority:
  - en
  - pt

notification:
  max_items_per_message: 10

sources:
  openalex:
    enabled: true
    lookback_days: 3
```

`Semantic Scholar` aceita a variável de ambiente opcional `SEMANTIC_SCHOLAR_API_KEY`.

## Telegram

Crie o bot com o `@BotFather`, use `/newbot` e copie o token gerado.

Para obter o `chat_id`:

1. Inicie uma conversa com o bot e envie qualquer mensagem.
2. Abra `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`.
3. Leia o campo `message.chat.id` da conversa desejada.

Crie um arquivo `.env` na raiz do projeto:

```env
TELEGRAM_BOT_TOKEN=seu_token
TELEGRAM_CHAT_ID=seu_chat_id
```

O `.env` nao deve ser versionado. Se o token do bot tiver sido exposto, gere um novo no `@BotFather` antes de usar em producao.
