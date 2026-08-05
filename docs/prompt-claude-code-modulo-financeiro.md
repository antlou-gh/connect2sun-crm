# Prompt para o Claude Code — Módulo Financeiro (connect2sun-crm)

> Cola este prompt no Claude Code, com o terminal aberto na raiz do projeto
> `connect2sun-crm`. Antes de começares a editar, lê os ficheiros existentes
> para seguires as convenções já usadas (ver secção "Convenções").

---

## Contexto do projeto

CRM interno da Connect2Sun (empresa de energia solar). Stack: **Flask +
SQLAlchemy**, **PostgreSQL (Neon)**, deploy no Render, armazenamento de
documentos no Cloudflare R2, autenticação MFA/TOTP. Os modelos estão em
`app/models.py`; os blueprints em `app/blueprints/`; os templates Jinja em
`templates/`. O modelo `Client` já existe e **tem os campos `client_number`
(int único) e `nif` (string)** — não precisas de os criar.

## Objetivo

Construir um **módulo financeiro** que passa a ser a *fonte de verdade* dos
movimentos financeiros da empresa (substitui o atual ficheiro Excel
`BD Finanças_2026.xlsx`). O módulo precisa de:

1. Um modelo `Transacao`.
2. Criação do schema na BD.
3. Um **importador único** que migra os ~280 movimentos de 2026 do Excel.
4. CRUD de movimentos (é por aqui que entram os lançamentos novos).
5. Dois ecrãs de revisão: "movimentos por categorizar" e "por associar a cliente".
6. Dashboards: P&L geral + margem por cliente.
7. Integração da margem na ficha de cada cliente.
8. **Exportação para Excel** (snapshot da app de volta para o formato da folha).

---

## 1. Modelo `Transacao` (em `app/models.py`)

Segue o estilo dos modelos existentes (timestamps *timezone-aware*, método
`to_dict()`).

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | Integer, PK | |
| `numero_ordem` | Integer, único, indexado | "Nº de ordem" do Excel; lançamentos novos continuam a série a partir do máximo existente |
| `descricao` | Text, not null | formato `Pag./Rec. Inst <CÓDIGO> <Cliente> <detalhe>` |
| `valor` | Float, not null | **com sinal**: negativo = custo/saída, positivo = receita/entrada |
| `entidade_emissora` | String(120) | |
| `num_factura` | String(60) | |
| `valor_siva` | Float | valor sem IVA |
| `iva` | Float | montante de IVA |
| `iva_pct` | Float | ex.: 0.23 |
| `data` | Date, not null, indexado | **campo Date real** — consolida Dia + Mês + ano (ano = 2026 na migração) |
| `estado` | String(20) | um de: `Fechado`, `Falta receber`, `Falta pagar`, `Pag. Parcial` |
| `tipo_movimento` | String(30) | um de: `Custos gerais`, `Facturação`, `Material/Serviços`, `Nota de crédito`, `Pagamentos ao Estado` |
| `categoria` | String(20), **nullable** | um de: `Estrutura`, `Viaturas`, `Marketing`, `Seguros`, `Royalties` (ou NULL) |
| `cliente_id` | Integer, FK `clients.id`, **nullable**, indexado | NULL = movimento sem cliente (custo geral) |
| `created_at` / `updated_at` | DateTime tz-aware | como nos outros modelos |

**Importante sobre os campos com valores fechados** (`estado`, `tipo_movimento`,
`categoria`): usa **`String` + listas de constantes Python validadas na
aplicação**, NÃO o tipo `ENUM` nativo do Postgres (acrescentar valores a um
enum Postgres mais tarde é doloroso). Define as listas como constantes no topo
do módulo, ex.:

```python
ESTADOS = ["Fechado", "Falta receber", "Falta pagar", "Pag. Parcial"]
TIPOS_MOVIMENTO = ["Custos gerais", "Facturação", "Material/Serviços",
                   "Nota de crédito", "Pagamentos ao Estado"]
CATEGORIAS = ["Estrutura", "Viaturas", "Marketing", "Seguros", "Royalties"]

# Meses em português — usado pela importação (texto→nº) e pela exportação (nº→texto)
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
```

Adiciona uma `db.relationship` `transacoes` no lado do `Client` (apenas ORM, não
altera colunas) para facilitar o cálculo de margem por cliente. **Não acrescentes
nem alteres colunas do `Client`.**

## 2. Criação do schema

Usa o mesmo mecanismo de criação de schema que o projeto já usa (verifica em
`app/__init__.py` se é `db.create_all()` ou migrações Alembic/Flask-Migrate) e
acrescenta a tabela `transacoes` por essa via.

## 3. Importador único do Excel (comando CLI)

Cria um comando Flask CLI (ex.: `flask importar-financeiro <caminho_xlsx>`) ou
script em `scripts/`, que recebe o caminho do `.xlsx` como argumento.

Especificação:

- Lê a folha **`BD Financeira 2026`** (tabela `Tabela2`, intervalo real **B2:O647**).
  A **linha de cabeçalhos é a linha 2**; os dados começam na **linha 3**; ignora
  linhas totalmente vazias.
- **⚠️ LER COLUNAS POR NOME DE CABEÇALHO, NÃO POR POSIÇÃO.** No ficheiro real
  preparado pelo utilizador, o cabeçalho **"NIF" está na coluna D** (foi inserido
  logo a seguir à "Descrição", empurrando as colunas seguintes), por isso o
  mapeamento posicional por letra de coluna **falha**. Constrói um mapa
  `{cabeçalho_normalizado: índice_coluna}` lendo a linha de cabeçalhos (normaliza:
  *trim* + minúsculas + sem acentos) e lê cada campo pela coluna do respetivo
  cabeçalho. Se faltar um cabeçalho esperado, **falha com erro claro** (não
  adivinhes a coluna).
- Mapeamento cabeçalho → campo (**textos exatos confirmados no ficheiro real**, por
  ordem B→O):

  | Cabeçalho na folha | Campo |
  |--------------------|-------|
  | `Nº de ordem` | `numero_ordem` |
  | `Descrição` | `descricao` |
  | `NIF` | (→ resolve `cliente_id`) |
  | `Valor total` | `valor` (com sinal) |
  | `Entidade emissora` | `entidade_emissora` |
  | `Nº de factura` | `num_factura` |
  | `S/ IVA` | `valor_siva` |
  | `IVA` | `iva` — **na folha é fórmula** `=ABS([Valor total])-[S/ IVA]`; ver nota abaixo |
  | `IVA %` | `iva_pct` |
  | `Dia` | (→ `data`) |
  | `Mês` | (→ `data`) — **texto em português**: "Janeiro"…"Dezembro" |
  | `Total` | **ignorado** (na folha é fórmula `=ABS([Valor total])`; não se guarda) |
  | `Estado` | `estado` |
  | `Tipo de movimento` | `tipo_movimento` |

- **Colunas com fórmula (`IVA` e `Total`):** com openpyxl, ler células de fórmula
  devolve o texto da fórmula, não o valor. Para `iva`, **não guardes a string da
  fórmula** — calcula `iva = round(abs(valor) - abs(valor_siva), 2)` (o `abs()`
  nos **dois** lados: há movimentos em que ambos vêm negativos — ex.: ordem 141,
  "Pag. acessórios" — e sem o segundo `abs()` a subtração vira soma, gravando o
  dobro do valor). `Total` é ignorado de qualquer forma.
- `data` = construir `date(2026, mes_num, dia)`, convertendo o **nome do mês** para
  número via `MESES`. Se o dia/mês faltar ou for inválido, regista aviso e salta a linha.
- `categoria` = **sempre NULL** na importação (categorização é feita depois na app).
- `cliente_id` = procurar `Client` cujo `nif` == valor da coluna NIF. **Normalizar
  para string dos dois lados** antes de comparar: **no Excel o NIF vem como inteiro**
  (ex.: `123456789`) e no modelo `Client.nif` é `String(20)` — converte com
  `str(int(valor))`, tira espaços e trata um eventual prefixo "PT". Se a célula NIF
  estiver vazia ou o NIF não corresponder a nenhum cliente → `cliente_id = NULL`.
- **Idempotência**: usa `numero_ordem` como chave. Se já existir uma transação
  com esse número, salta (não duplica). Assim o comando pode correr mais que uma
  vez sem estragar.
- No fim, imprime um resumo: nº de movimentos importados, nº saltados, nº sem
  cliente associado, nº sem categoria.

## 4. CRUD de movimentos

Blueprint novo (ex.: `app/blueprints/financeiro.py`), registado em
`app/__init__.py` como os restantes, e protegido pelo mesmo decorator de
autenticação/MFA que as outras rotas.

- **Lista** de movimentos com filtros (por mês, tipo de movimento, categoria,
  estado, cliente) e pesquisa por descrição. Mostra o `valor` com sinal e
  formata em euros.
- **Criar / Editar / Eliminar** movimento, com formulário que usa *dropdowns*
  para `estado`, `tipo_movimento`, `categoria` (das constantes) e seleção de
  cliente (opcional). Campo de data com máscara `dd/mm/aaaa` (segue o que já
  existe no projeto). Ao criar, `numero_ordem` = `max(numero_ordem) + 1`.
  **`entidade_emissora` é obrigatória** (validação na aplicação, não na coluna
  da BD) — tal como `descricao`, `valor` e `data`: sem ela o movimento não é
  rastreável até ao fornecedor/cliente que o emitiu, e essa informação nunca
  mais é recuperável depois de perdida. `num_factura` fica opcional (nem todo
  o movimento tem documento associado, ex.: transferência bancária), mas
  incentivada.

## 5. Ecrãs de revisão

Deriva-os por *query*, sem campos extra:

- **"Por categorizar"**: movimentos com `categoria IS NULL` **e** `tipo_movimento`
  em (`Custos gerais`, `Pagamentos ao Estado`). Tabela com *dropdown* de categoria
  por linha, para classificar rapidamente (de preferência gravação inline/AJAX).
  Os tipos `Facturação`, `Material/Serviços` e `Nota de crédito` **não** precisam
  de categoria, por isso não aparecem aqui.
- **"Por associar a cliente"**: movimentos com `cliente_id IS NULL` **e**
  `tipo_movimento` em (`Facturação`, `Material/Serviços`) — ou seja, os que
  deviam ter cliente mas ficaram sem. Permite escolher o cliente por linha.

## 6. Dashboards

- **P&L geral** (com filtro de período — mês e ano):
  - Receita = soma de `valor` dos `Facturação` (abate as `Nota de crédito`).
  - Custos diretos = soma de `abs(valor)` dos `Material/Serviços`.
  - Custos de estrutura = soma de `abs(valor)` dos `Custos gerais` +
    `Pagamentos ao Estado`, **com breakdown por `categoria`**.
  - Resultado = Receita − Custos diretos − Custos de estrutura.
- **Margem por cliente**: por cada cliente com movimentos, margem =
  Σ`Facturação` − Σ`Material/Serviços` (filtrados por `cliente_id`). Lista
  ordenável por margem.

Gráficos simples chegam (podes usar a biblioteca de charting que o projeto já
tenha; se não tiver, usa algo leve sem dependências pesadas).

## 7. Ficha do cliente

Na página de detalhe de cada cliente, acrescenta um bloco com: a margem desse
cliente e a lista dos seus movimentos (faturação e custos imputados).

## 8. Exportação para Excel

Permite gerar um **snapshot** das transações da app no formato da folha
"BD Financeira 2026", para o contabilista, backup ou consulta.

### Princípio fundamental — export UNIDIRECIONAL
- O export é um **snapshot/relatório** (app → Excel). A app continua a ser a
  **fonte única de verdade**.
- **NUNCA** se reimporta um Excel exportado. Não há round-trip.
- Gerar **sempre um ficheiro novo** (ex.: `BD Financeira_export_AAAAMMDD.xlsx`);
  nunca sobrescrever a BD viva.

### Interface: botão "Exportar para Excel"
- Adicionar um botão **"Exportar para Excel"** no módulo financeiro (ex.: na lista
  de movimentos e/ou no dashboard).
- O botão chama um endpoint (ex.: `GET /financeiro/exportar?ano=2026`) que gera o
  ficheiro em memória (`io.BytesIO`) e o devolve como **download** via `send_file`:
  - mimetype `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  - `as_attachment=True`, nome `BD Financeira_export_AAAAMMDD.xlsx`
- A geração vive numa **função de serviço partilhada**
  `gerar_export_financeiro(ano) -> Workbook`, reutilizada pelo comando CLI
  `flask exportar-financeiro <ficheiro> [--ano 2026]` — ver a secção 9. O endpoint
  grava o Workbook em `BytesIO`, o CLI grava-o em ficheiro; a lógica é a mesma nos
  dois caminhos, e é isso que garante que o CLI e o botão nunca divergem.

### Template-modelo (preservar o aspeto da folha do contabilista)
O export parte de um **ficheiro-modelo** guardado no projeto, em vez de construir a
folha do zero — mantém Tabela2, cabeçalhos, formatações, larguras e o aspeto conhecido.

- Guardar em: `app/static/templates_xlsx/BD_Financeira_2026_modelo.xlsx`
  (o nome inclui o ano; é o caminho que o `financeiro_service.MODELO_PATH` lê)
- O modelo é uma **cópia da `BD Finanças_2026.xlsx` apenas com a linha de cabeçalhos
  (linha 2) e os estilos/larguras** — **sem dados**. Mantém o título em B1 (merge
  B1:E1) e a `Tabela2` reduzida a `B2:O3` (cabeçalho + 1 linha vazia, para a tabela
  continuar válida no Excel). É um **artefacto de apresentação**, versionado com o código.
- O modelo **já contém** o cabeçalho **"NIF" na coluna D** (a seguir à "Descrição").
  _(Este ficheiro já foi gerado e entregue; basta colocá-lo no caminho acima.)_

### Layout de saída — escrever SEMPRE por NOME de cabeçalho
**Não usar letras de coluna fixas** (mesma razão do import: o "NIF" está na coluna D,
não no fim). Localiza cada coluna pelo **texto do cabeçalho** e escreve cada campo nessa
coluna. Mapeamento campo da `Transacao` → cabeçalho (**textos exatos**, ordem B→O):

| Cabeçalho na folha | Origem na `Transacao` |
|--------------------|-----------------------|
| `Nº de ordem` | `numero_ordem` |
| `Descrição` | `descricao` |
| `NIF` | `cliente.nif` se `cliente_id`, senão vazio |
| `Valor total` | `valor` (com sinal) |
| `Entidade emissora` | `entidade_emissora` |
| `Nº de factura` | `num_factura` |
| `S/ IVA` | `valor_siva` |
| `IVA` | `iva` (valor literal) |
| `IVA %` | `iva_pct` |
| `Dia` | `data.day` |
| `Mês` | **nome do mês em português** via `MESES[data.month - 1]` |
| `Total` | `abs(valor)` (valor literal, não fórmula) |
| `Estado` | `estado` |
| `Tipo de movimento` | `tipo_movimento` |

### Fluxo de geração `gerar_export_financeiro(ano)`
1. `load_workbook` do **modelo** (ler sempre fresco a cada chamada — não mutar um
   workbook partilhado em memória).
2. Selecionar a folha "BD Financeira 2026"; localizar a **linha de cabeçalhos** da
   Tabela2; construir o mapa `{cabeçalho_normalizado: índice_coluna}` (mesma
   normalização do import).
3. Escrever as transações (ordenadas por `numero_ordem`, filtradas por `data.year`,
   default 2026) a partir da primeira linha de dados, cada campo na coluna do
   respetivo cabeçalho.
4. **Ajustar o intervalo da `Tabela2`** ao nº de linhas escritas
   (`worksheet.tables["Tabela2"].ref`), para não ficar com linhas a mais/menos.
5. Devolver o `Workbook` (o endpoint grava em `BytesIO`; o CLI grava em ficheiro).

### Regras do export
- **Read-only sobre a BD** (só leitura da `Transacao`).
- **Mês** escrito como **texto português** (consistente com a folha original e com o
  que o import espera ler), via `MESES`.
- **Total** como valor literal `abs(valor)`, **nunca fórmula** (evita erros de
  recálculo no openpyxl).
- A coluna **`categoria` NÃO é exportada** — é dimensão só da app e não existe na
  Tabela2 (manter compatibilidade com o ficheiro do contabilista).
- NIF normalizado para string (consistente com o import).
- Preservar a linha de cabeçalho; reescrever apenas a região de dados.
- Se faltar um cabeçalho esperado, ou se o modelo não existir, **falhar com erro
  claro** — nunca escrever em coluna errada.

---

## 9. Comandos CLI (estado real, `app/cli.py`)

Todos registados em `register_cli(app)` e invocados como `flask <comando>`. Correm
contra a BD apontada pelo `DATABASE_URL` do ambiente — atenção a qual, porque três
deles escrevem.

| Comando | Escreve? | Para que serve |
|---|---|---|
| `importar-financeiro <caminho_xlsx> [--ano 2026]` | sim | Importa os movimentos do Excel. Idempotente: `numero_ordem` já existente é saltado. Imprime resumo (importados, já existentes, sem cliente, sem categoria, ignoradas) e avisos linha a linha. |
| `exportar-financeiro <ficheiro> [--ano 2026]` | não | Snapshot Excel no formato da folha do contabilista, via `gerar_export_financeiro(ano)`. Grava no `<ficheiro>` indicado. |
| `financeiro-lacunas [--csv <path>] [--apply]` | só com `--apply` | Relatório de `num_factura`/`entidade_emissora` em falta, com sugestões extraídas da Descrição. Sem `--apply` é read-only. Com `--apply` escreve **apenas** as linhas de estado `ok` — nunca as `ambíguo` nem as `sem correspondência`. |
| `clientes-nif [--todos]` | não | Lista nº + nome + NIF dos clientes, para conferir com a folha. |

Regras que estes comandos ilustram e que se mantêm:
- **O export nunca é reimportado.** O `exportar-financeiro` produz um ficheiro novo;
  o `importar-financeiro` só deve ver a folha original do contabilista.
- **Nenhum comando destrói dados.** A escrita é sempre acrescentar (import) ou
  preencher campos vazios (lacunas `--apply`); não há comando de apagar.
- **O `--apply` é opt-in.** O comportamento por omissão de qualquer comando que
  possa escrever é mostrar o que faria.

## Convenções a respeitar

- Lê `app/models.py`, `app/__init__.py`, um blueprint existente (ex.:
  `app/blueprints/clients.py`) e um par de templates antes de escrever, para
  imitar o estilo (estrutura de rotas, `to_dict()`, timestamps tz-aware, layout
  Jinja, navbar).
- Acrescenta a entrada do módulo financeiro à navbar.
- Para UI nova, podes apoiar-te no skill `frontend-design` se estiver disponível.
- Mensagens e labels em **português de Portugal**.

## Critérios de aceitação

1. Tabela `transacoes` criada na BD.
2. `flask importar-financeiro <ficheiro>` corre, **lendo as colunas por nome de
   cabeçalho**, importa os movimentos de 2026, resolve `cliente_id` por NIF onde
   possível, deixa `categoria` a NULL, e imprime o resumo. Correr 2× não duplica.
3. CRUD funcional; lançamentos novos continuam a série de `numero_ordem`.
4. Os dois ecrãs de revisão filtram corretamente.
5. Dashboards de P&L e margem por cliente calculam valores coerentes.
6. A ficha do cliente mostra a margem.
7. O botão **"Exportar para Excel"** gera um ficheiro novo no formato da folha
   (colunas por nome de cabeçalho, mês em texto, `categoria` não exportada) e
   descarrega-o; o ficheiro abre sem erros.
8. `flask exportar-financeiro <ficheiro>` produz **o mesmo ficheiro** que o botão,
   para o mesmo ano — se divergirem, é sinal de que a lógica deixou de estar
   partilhada em `gerar_export_financeiro(ano)` e passou a estar duplicada.
9. `flask financeiro-lacunas` sem `--apply` não escreve nada na BD; com `--apply`
   só toca nas linhas de estado `ok`.
10. Tudo protegido pela autenticação existente.

## O que NÃO fazer

- Não alterar nem acrescentar colunas ao modelo `Client` (`nif` e
  `client_number` já existem; usa-os).
- Não tocar em `proposal_path` nem na função `_migrate_proposals_to_documents`.
- Não usar `ENUM` nativo do Postgres (usa `String` + listas de constantes).
- Não usar **mapeamento posicional de colunas** no Excel (import e export leem/
  escrevem **por nome de cabeçalho**).
- **Não reimportar** ficheiros gerados pelo export, nem escrever na BD Financeira
  "viva": a partir de agora a app é a fonte de verdade; o export é apenas um
  snapshot unidirecional para um ficheiro novo.
