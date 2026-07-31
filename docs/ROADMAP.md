# Roadmap — The Thomas

## Tabela de controle

| ID | Feature | Fase | Status | Data de conclusão |
|---|---|---|---|---|
| F00 | Core (schemas, carregamento de cenários, variáveis, correlação, `thomas request`) | 0 | Concluído | 2026-07-25 |
| F01 | Publicação inicial (repositório público, licença, marca, README) | 0 | Concluído | 2026-07-27 |
| F003 | Controle de verificação de certificado SSL e metadados de ambiente | 0 | Concluído | 2026-07-27 |
| F004 | Suporte a headers customizados em requisições | 0 | Concluído | 2026-07-27 |
| F005 | Thomas Init (`thomas init` — bootstrap projects without git clone) | 0 | Concluído | 2026-07-27 |
| F02 | Motor de validação genérico (operadores + orquestração de `thomas validate`) | 1 | Concluído | 2026-07-28 |
| F03 | Conector Oracle | 1 | Concluído | 2026-07-28 |
| F04 | Relatório HTML (bilíngue EN/PT) | 1 | Concluído | 2026-07-29 |
| F05 | Múltiplos ambientes (refinamento) | 1 | Não iniciado | — |
| F009 | Aplicar design system ao relatório HTML (cores, tipografia, espaçamento, responsivo) | 1 | Concluído | 2026-07-29 |
| F010 | Reestruturar relatório HTML em 3 views (Dashboard, Ambiente de execução, Timeline) | 1 | Concluído | 2026-07-29 |
| F011 | Quick start de primeira experiência para `thomas init` (exemplos contra API pública real, sem servidor local) | 1 | Concluído | 2026-07-31 |
| F06 | Conector DB2 | 2 | Não iniciado | — |
| F07 | Conector Kafka | 2 | Não iniciado | — |
| F08 | Conector MongoDB | 2 | Não iniciado | — |

> Atualizar "Status" (Não iniciado / Em andamento / Concluído) e "Data de
> conclusão" conforme cada feature avança pelo fluxo do Spec-Kit
> (`/specify` → `/plan` → `/tasks` → `/implement`).

## Nota sobre o momento de publicação

Diferente de um modelo tradicional em que a publicação ocorre só ao final
do roadmap, aqui **F01 (Publicação inicial) acontece logo após F00**, não
no final. Motivo: o comando `thomas request` sozinho já é uma ferramenta
útil e reutilizável em outros contextos. A partir de F01, toda feature seguinte (F02 em
diante) é desenvolvida diretamente no repositório já público.

F02-F04, F009 e F010 foram publicados em conjunto na v0.3.0
(2026-07-30), consolidando o fluxo completo `request` → `validate` →
`report` com o conector Oracle como prova de conceito.

## Nota sobre a ordem das fases

A Fase 1 (F02-F05) entrega o fluxo completo de ponta a ponta — disparo,
validação, relatório e suporte a múltiplos ambientes — usando um único
conector real (Oracle) como prova de conceito. Só depois, na Fase 2
(F06-F08), os demais conectores (DB2, Kafka, MongoDB) são adicionados,
cada um já se beneficiando do relatório e do suporte a múltiplos
ambientes formalizados na Fase 1, sem retrabalho.

## Descrição de cada feature

### F00 — Core
Fundação do projeto: definição e validação dos JSON Schemas (cenário,
ambiente, variáveis, execução v1, todos em inglês); leitura recursiva de
pastas de cenários; resolução de variáveis preparatórias estáticas;
resolução do ID de correlação (resposta da API ou payload); comando
`thomas request` completo (dispara requisições, consulta `/info`, avalia
`api_checks`, grava o registro de execução); logging em arquivo e
progresso em console. **Não inclui nenhum conector de dado** — cenários
com `validations` ficam registrados como `awaiting_validation` até que
F03 exista. Já é um entregável útil isoladamente para o time de
desenvolvimento validar contratos de API.

### F01 — Publicação inicial
Preparação e publicação pública do repositório logo após F00: licença
Apache 2.0, arquivo `NOTICE`, nota de marca sobre o nome/logo "The Thomas", README cobrindo o que existe até aqui (`thomas request`),
auditoria de higienização (garantir ausência de qualquer dado real desde
o primeiro commit público), `CONTRIBUTING.md`, e empacotamento mínimo
(`pyproject.toml` com metadados completos). Esta feature é
deliberadamente enxuta — cobre apenas o que já existe (F00), não antecipa
documentação de funcionalidades futuras.

### F003 — Controle de verificação de certificado SSL e metadados de ambiente
Adição de controle granular de verificação de certificado SSL por API e por
serviço, permitindo ambientes de teste com certificados auto-assinados. 
Simultaneamente, adição de campos opcionais de metadados de ambiente 
(`company_name`, `department_name`) para trilhas de auditoria e futuros 
relatórios. Ambas as mudanças são aditivas e retrocompatíveis com a versão 
de schema 1 (nenhum bump necessário). Habilita cenários de teste heterogêneos 
onde diferentes APIs e serviços têm diferentes configurações de certificado.

### F004 — Suporte a headers customizados em requisições
Adição de suporte a headers customizados em dois níveis: no cenário
(nível de endpoint) e no ambiente (nível de API e serviços), com precedência
de cenário sobre ambiente. Inclui resolução de variáveis nos valores dos headers
(`{{variable_name}}`), permitindo reutilização de cenários com credenciais
dinâmicas. Retrocompatível com schema version 1 (nenhum bump necessário).
Habilita testes de APIs que requerem autenticação por header ou headers
específicos da aplicação em tempo de teste.

### F005 — Thomas Init
Comando `thomas init [destination] [--force]` que bootstrapa um novo projeto
Thomas completo, pronto para uso, sem necessidade de git clone. Inclui:
estrutura de diretórios (scenarios/, config/, examples/), arquivos de
template (config/environments/example.json.dist, .gitignore, README), e
cenários de exemplo prontos para uso.
Suporta validação de path (symlinks, mount points, Windows limit),
proteção da pasta scenarios/ contra sobrescrita mesmo com --force,
idempotência total (executar duas vezes não causa danos), e mensagens de
erro claras com exit codes apropriados. Reduz barreira de entrada para
novos usuários — nenhum git, nenhuma instalação editable, apenas
`pip install the-thomas-test-suite && thomas init`.

> **Nota (F011)**: o ambiente de exemplo original desta feature dependia de
> um servidor mock local (`examples/mock_server.py`), substituído pela F011
> por exemplos que chamam uma API pública real.

### F02 — Motor de validação genérico
Implementação do motor de operadores (tabela completa descrita em
`04-validation-engine-operators.md`), da interface abstrata de conector
(`BaseConnector`), e da orquestração do comando `thomas validate` (leitura
do registro de execução, execução de rodada, acréscimo ao histórico,
recálculo de `final_status`) — usando ao menos um conector de teste
simplificado (in-memory/fake) para validar a orquestração de ponta a ponta
antes de plugar um driver real.

### F03 — Conector Oracle
Primeiro conector real, usando `oracledb` em modo thin. Define o padrão de
implementação que os demais conectores (F06-F08) seguem. É o único
conector disponível durante toda a Fase 1 — suficiente para exercitar o
relatório (F04) e o suporte a múltiplos ambientes (F05) com dados reais.

### F04 — Relatório HTML
Template Jinja2 autocontido (CSS/JS/logo SVG inline), com **suporte
bilíngue inglês/português** controlado por `report_language` no arquivo
de ambiente. Dashboard com cards de estatística, gauge de percentual,
badge de status combinável, filtros por pasta/funcionalidade,
tabela-resumo agrupada por pasta, detalhamento em três níveis (cenário →
rodada → validação individual), aba de timeline cronológica, dark mode.
Já pode ser exercitada com dados reais de execuções usando o conector
Oracle (F03).

### F009 — Aplicar design system ao relatório HTML
Restilização apenas via CSS do relatório HTML gerado pela F04 (cores,
tipografia, espaçamento, layout responsivo, dark mode), reaproveitando a
estrutura de classes HTML e a lógica de população de dados já existentes,
sem alterações estruturais.

### F010 — Reestruturar relatório HTML em 3 views
Reconstrução estrutural (não apenas visual) do template Jinja2 do
relatório: três views mutuamente exclusivas navegáveis por tabs
(Dashboard padrão, Ambiente de execução, Timeline), reaproveitando os
tokens de design da F009 e o pipeline de dados da F04/F008 sem
reescrevê-los. Dashboard ganha donut chart, mini-cards com toggle
Pasta/Funcionalidade, chips de filtro por status combináveis com busca
textual, e detalhamento de cenário em 4 seções colapsáveis
independentes (Requisição/Resposta/Verificações/Validação). Ambiente de
execução consolida identificação, API sob teste, serviços de
informação, conectores (com mascaramento de campos sensíveis) e
variáveis preparatórias — cada bloco omitido por completo quando não há
dado. Timeline ganha visualização Gantt (marcadores proporcionais ao
tempo real, coloridos por resultado da rodada) e visualização Log
intercalada, além de gráfico de dispersão de latência. Inclui uma
mudança aditiva de schema (`prepared_variables` em `execution_v1.json`,
sem bump de versão) para que `thomas request` registre as variáveis
resolvidas usadas na execução.

### F011 — Quick start de primeira experiência para `thomas init`
Substitui o ambiente de exemplo baseado em servidor mock local
(`examples/mock_server.py`) por três cenários prontos para uso contra uma
API pública real (`jsonplaceholder.typicode.com`), sem exigir nenhum
processo auxiliar, porta local ou segundo terminal: leitura de dados,
escrita de dados, e um fluxo de validação posterior (confirmação
imediata e determinística via o conector `fake`, sem retry/polling).
Remove a pasta `examples/` divergente mantida separadamente no
repositório e alinha toda a documentação pública ao único conjunto de
exemplos gerado por `thomas init`.

### F05 — Múltiplos ambientes (refinamento)
Formalização do suporte a múltiplos arquivos de ambiente nomeados,
incluindo validação cruzada entre o ambiente usado no `request` e no
`validate`, e refinamento do relatório para exibir claramente qual
ambiente foi usado em cada etapa. Encerra a Fase 1 — a partir daqui, o
fluxo completo (`request` → `validate` → `report`, múltiplos ambientes)
está pronto, faltando apenas adicionar mais conectores.

### F06 — Conector DB2
Implementação via `ibm-db` (ou `jaydebeapi` como alternativa documentada),
seguindo o mesmo contrato do conector Oracle. Primeira feature da Fase 2.

### F07 — Conector Kafka
Implementação via `confluent-kafka`, com estratégia de consumer group
efêmero, leitura por offset de tempo, filtro por chave de correlação, e
tratamento de timeout como erro técnico.

### F08 — Conector MongoDB
Implementação via `pymongo`, com o formato de validação por filtro/coleção
específico de banco não-relacional (ver `05-connectors.md`). Última
feature do roadmap atual.
