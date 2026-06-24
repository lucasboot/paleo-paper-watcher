# paleo-paper-watcher

Projeto pessoal em Python para monitorar diariamente novos artigos cientificos relacionados a Formacao Alagamar, Bacia Potiguar e proxies paleoambientais/geoquimicos do intervalo Aptiano-Albiano, com execucao via GitHub Actions e notificacoes por Telegram.

## Estrutura

- `main.py`: executa todas as fontes habilitadas para todas as queries, deduplica e aplica o filtro de relevancia.
- `src/config.py`: carregamento e validacao de `config.yaml`.
- `src/models.py`: modelos Pydantic do dominio.
- `src/relevance.py`: motor de score e decisao de relevancia.
- `src/normalize.py`: normalizacao de titulo e geracao de chave de deduplicacao.
- `src/sources/`: integracoes com OpenAlex, Crossref, Semantic Scholar e arXiv.
- `src/notify/`: integracoes de notificacao.
- `data/seen.json`: persistencia simples para evitar alertas duplicados.

## Requisitos

- Python 3.12

## Instalacao

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Execucao local

```bash
.venv/bin/python main.py
```

O script consulta as fontes habilitadas em `config.yaml`, agrega os resultados, remove duplicados por DOI/`external_id`/titulo normalizado, aplica um pos-filtro de relevancia e gera mensagens para Telegram. Se o Telegram nao estiver configurado, ele imprime as mensagens no terminal. Artigos rejeitados pelo pos-filtro tambem aparecem no terminal com score e motivos.

## Configuracao

O arquivo [config.yaml](/home/lucas-alves/Documents/paleo-paper-watcher/config.yaml) concentra as queries e o filtro cientifico. O `arxiv` fica desabilitado por padrao porque tende a gerar mais ruido para esse tema.

Exemplo resumido:

```yaml
max_results_per_source: 20
queries:
  - '"Alagamar Formation"'
  - '"Potiguar Basin" "organic geochemistry"'

filters:
  enabled: true
  min_score: 7
  require_anchor: true
  anchor_keywords:
    - Alagamar Formation
    - Potiguar Basin
    - palynofacies
  strong_geology_keywords:
    - organic geochemistry
    - Rock-Eval
    - marine transgression
```

`Semantic Scholar` aceita a variavel de ambiente opcional `SEMANTIC_SCHOLAR_API_KEY`.

### Estrategia de queries

As queries atuais foram calibradas para quatro blocos:

1. Nucleo direto da tese: Alagamar, Bacia Potiguar, Aptiano-Albiano, Pos-Rifte.
2. Metodos centrais: palinologia, palinofacies, palinomorfos, bioestratigrafia.
3. Interpretacao geologica: transgressao marinha, incursao marinha, paleoambiente.
4. Proxies associados: biomarcadores, geoquimica organica, COT/TOC, Rock-Eval, maturacao termica.

Prefira queries compostas com contexto geologico explicito. Evite termos abertos como `pollen`, `spores`, `palynology` ou `sedimentology` sozinhos, porque as APIs tratam texto livre de forma ampla e isso aumenta muito o ruido.

### Pos-filtro de relevancia

A secao `filters` funciona como uma segunda barreira antes das notificacoes:

- `enabled`: liga ou desliga o pos-filtro.
- `min_score`: score minimo para aprovacao.
- `require_anchor`: exige ancora no caminho principal de aprovacao.
- `anchor_keywords`: termos que indicam aderencia forte ao tema da tese.
- `geology_keywords`: termos geologicos e de proxy detectados no artigo.
- `strong_geology_keywords`: subconjunto usado na regra alternativa de aprovacao sem ancora.
- `preferred_venues`: periodicos que recebem bonus de score.
- `preferred_authors`: autores recorrentes do tema que recebem bonus de score.
- `negative_keywords`: termos que reduzem score e bloqueiam ruido.

#### Regras de score

- `+8` se o titulo contem `Alagamar`, `Alagamar Formation`, `Formacao Alagamar`, `Potiguar Basin` ou `Bacia Potiguar`
- `+6` se o resumo contem esses termos centrais
- `+5` se o titulo contem `Upanema`, `Ponta do Tubarao`, `Galinhos` ou `Canto do Amaro`
- `+5` se o titulo contem `palynofacies`, `palinofacies`, `palynology`, `palinologia` ou `palynomorphs`
- `+3` se o resumo contem esses termos metodologicos
- `+3` se o artigo contem `Aptian`, `Aptiano`, `Albian`, `Albiano`, `Lower Cretaceous` ou `Cretaceo Inferior`
- `+2` se o artigo contem termos-alvo de geoquimica/proxy como `organic geochemistry`, `biomarkers`, `TOC`, `COT`, `Rock-Eval` ou `thermal maturation`
- `+2` se o periodico estiver em `preferred_venues`
- `+2` se algum autor estiver em `preferred_authors`
- `-6` por `negative_keyword`
- `-10` adicionais se houver termo negativo e nenhum `anchor_keyword`

#### Regra final de aprovacao

Um artigo e aprovado quando:

- `score >= min_score`
- e tem pelo menos uma `anchor_keyword`

Ou, alternativamente:

- `score >= min_score`
- tem pelo menos duas `strong_geology_keywords`
- e nao tem `negative_keyword`

Com `require_anchor: true`, o caminho principal continua exigindo ancora. A excecao e apenas a regra alternativa acima.

### Calibragem pratica

Use os logs dos artigos filtrados para ajustar:

- `min_score`: normalmente entre `6` e `10`
- `anchor_keywords`: para ampliar ou fechar aderencia ao tema
- `strong_geology_keywords`: para controlar o caminho alternativo sem ancora
- `negative_keywords`: para bloquear ruido recorrente de educacao, saude, agricultura ou ciencia planetaria

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

Cada artigo aprovado inclui uma linha resumida de relevancia no Telegram com score e motivos principais da selecao.

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

### Alterar queries e filtros

As queries e os filtros monitorados ficam em [config.yaml](/home/lucas-alves/Documents/paleo-paper-watcher/config.yaml). Edite `queries:` e `filters:` e faca commit normalmente. O proximo agendamento usara essa configuracao.

### Persistencia do estado

Ao final da execucao, o workflow tenta commitar `data/seen.json` de volta ao repositorio se ele tiver mudado. Isso evita alertas duplicados entre runs agendados.
