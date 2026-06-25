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
  normalize:
    remove_accents: true
  direct_thesis:
    min_score: 7
    require_anchor: true
  methodological_analog:
    min_score: 10
    min_methodological_terms: 3
    require_geoscience_context: true
  regional_keywords:
    - Alagamar Formation
    - Potiguar Basin
  methodological_keywords:
    - palynofacies
    - organic geochemistry
    - Rock-Eval
```

As fontes usam estas variaveis opcionais de ambiente:

- `OPENALEX_API_KEY`: aumenta o limite diario do OpenAlex e reduz `429`.
- `CROSSREF_MAILTO`: identifica o watcher no Crossref via `mailto` e `User-Agent`.
- `SEMANTIC_SCHOLAR_API_KEY`: ajuda no suporte e evita throttling compartilhado no Semantic Scholar.

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
- `normalize.remove_accents`: controla a remocao de acentos no matching.
- `direct_thesis`: regras do caminho de relacao direta com a tese.
- `methodological_analog`: regras do caminho de analogos metodologicos.
- `regional_keywords`: ancora espacial e estratigrafica direta.
- `temporal_keywords`: ancora temporal do recorte da tese.
- `methodological_keywords`: proxies e metodos centrais.
- `geoscience_context_keywords`: contexto geologico exigido para analogos.
- `preferred_venues`: periodicos que recebem bonus de score.
- `preferred_authors`: autores recorrentes do tema que recebem bonus de score.
- `negative_keywords`: termos que reduzem score e bloqueiam ruido.

#### Matching

- termos de uma palavra usam match por fronteira de palavra.
- siglas curtas como `TOC` e `COT` so contam como token isolado.
- frases com varias palavras usam busca por frase normalizada.
- `negative_keywords` usam a mesma regra estruturada e nao substring simples.
- isso evita falsos positivos como `crop` em `outcrop`, `TOC` em `autocuidado` e `COT` em `contexto`.

#### Categorias de aprovacao

`direct_thesis_relevance`:

- exige score minimo em `direct_thesis.min_score`
- exige ancora regional ou temporal
- prioriza trabalhos diretamente ligados a Alagamar, Potiguar, Aptiano-Albiano e unidades correlatas

`methodological_analog`:

- permite aprovacao sem citar Potiguar ou Alagamar
- exige score minimo em `methodological_analog.min_score`
- exige pelo menos `min_methodological_terms` distintos
- exige contexto geocientifico quando `require_geoscience_context=true`
- foi pensado para artigos como palinofacies, geoquimica organica, TOC/COT, Rock-Eval, biomarcadores e rochas geradoras em outras bacias ou idades

Quando ambos passam, o sistema prioriza `direct_thesis_relevance`.

### Calibragem pratica

Use os logs dos artigos filtrados para ajustar:

- `direct_thesis.min_score`: normalmente entre `6` e `10`
- `methodological_analog.min_score`: normalmente entre `9` e `12`
- `methodological_analog.min_methodological_terms`: controla o rigor dos analogos
- `regional_keywords`, `temporal_keywords` e `methodological_keywords`: para abrir ou fechar o funil
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
OPENALEX_API_KEY=sua_chave_openalex
CROSSREF_MAILTO=seu-email@dominio.com
SEMANTIC_SCHOLAR_API_KEY=sua_chave_semantic_scholar
```

Use `TELEGRAM_CHAT_IDS` com ids separados por virgula. O mesmo conjunto de artigos sera enviado para todos os chats, e um paper so sera marcado como notificado quando todos os chats da lista receberem a mensagem com sucesso.

Cada artigo aprovado inclui uma linha resumida de relevancia no Telegram com categoria, score e motivos principais da selecao.

## APIs e limites

- OpenAlex: usa `OPENALEX_API_KEY` como `api_key` na query string. Sem chave, o limite diario gratuito e menor. O watcher aplica retry com backoff e pacing conservador.
- Crossref: nao usa API key no REST publico. O watcher envia `mailto` e `User-Agent` identificavel quando `CROSSREF_MAILTO` estiver configurado, com retry e pacing conservador.
- Semantic Scholar: usa `SEMANTIC_SCHOLAR_API_KEY` no header `x-api-key`. O watcher limita as chamadas a um ritmo conservador de `1` request por vez com backoff em `429` e `5xx`.

## GitHub Actions

O workflow semanal fica em [.github/workflows/weekly.yml](/home/lucas-alves/Documents/paleo-paper-watcher/.github/workflows/weekly.yml) e roda:

- automaticamente toda segunda-feira as `11:00 UTC`
- manualmente via `workflow_dispatch`

No fuso `America/Fortaleza (UTC-3)`, `11:00 UTC` corresponde a `08:00`.

### Configurar secrets

No repositorio do GitHub:

1. Abra `Settings`.
2. Abra `Secrets and variables` > `Actions`.
3. Crie os secrets:
4. `TELEGRAM_BOT_TOKEN`
5. `TELEGRAM_CHAT_IDS`
6. `OPENALEX_API_KEY` (recomendado para reduzir `429` e ampliar o limite diario)
7. `CROSSREF_MAILTO` (recomendado para usar o pool identificado do Crossref)
8. `SEMANTIC_SCHOLAR_API_KEY` (recomendado para reduzir throttling compartilhado)

### Rodar manualmente no GitHub

1. Abra a aba `Actions`.
2. Selecione `Weekly Paleo Paper Watcher`.
3. Clique em `Run workflow`.
4. Escolha a branch e execute.

### Alterar queries e filtros

As queries e os filtros monitorados ficam em [config.yaml](/home/lucas-alves/Documents/paleo-paper-watcher/config.yaml). Edite `queries:` e `filters:` e faca commit normalmente. O proximo agendamento usara essa configuracao.

### Persistencia do estado

Ao final da execucao, o workflow tenta commitar `data/seen.json` de volta ao repositorio se ele tiver mudado. Isso evita alertas duplicados entre runs agendados.
