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

## Execução local

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
TELEGRAM_CHAT_IDS=5291018127,-1001234567890
```

Use `TELEGRAM_CHAT_IDS` com ids separados por virgula. O mesmo conjunto de artigos sera enviado para todos os chats, e um paper so sera marcado como notificado quando todos os chats da lista receberem a mensagem com sucesso.

O `.env` nao deve ser versionado. Se o token do bot tiver sido exposto, gere um novo no `@BotFather` antes de usar em producao.

## GitHub Actions

O workflow diario fica em [.github/workflows/daily.yml](/home/lucas-alves/Documents/paleo-paper-watcher/.github/workflows/daily.yml) e roda:

- automaticamente todos os dias as `11:00 UTC`
- manualmente via `workflow_dispatch`

No fuso `America/Fortaleza (UTC-3)`, `11:00 UTC` corresponde a `08:00`.

### Configurar secrets

No repositorio do GitHub:

1. Abra `Settings`.
2. Abra `Secrets and variables` > `Actions`.
3. Crie os secrets:
4. `TELEGRAM_BOT_TOKEN`
5. `TELEGRAM_CHAT_IDS`
6. `SEMANTIC_SCHOLAR_API_KEY` (opcional, mas recomendado para reduzir rate limit)

### Rodar manualmente no GitHub

1. Abra a aba `Actions`.
2. Selecione `Daily Paleo Paper Watcher`.
3. Clique em `Run workflow`.
4. Escolha a branch e execute.

### Alterar queries

As queries monitoradas ficam em [config.yaml](/home/lucas-alves/Documents/paleo-paper-watcher/config.yaml). Edite a lista `queries:` e faça commit normalmente. O proximo agendamento usara essa configuracao.

### Persistencia do estado

Ao final da execucao, o workflow tenta commitar `data/seen.json` de volta ao repositorio se ele tiver mudado. Isso evita alertas duplicados entre runs agendados.
