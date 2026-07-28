# Constitution — The Thomas

## 1. Propósito e visão

The Thomas é uma ferramenta de automação de testes de API **orientada a dados**,
que dispara requisições HTTP a partir de cenários descritos em JSON e
valida seus efeitos colaterais em múltiplas fontes de dados heterogêneas
(bancos relacionais, NoSQL, tópicos de mensageria), com suporte nativo a
processamento assíncrono de duração indeterminada.

O diferencial do The Thomas em relação a frameworks de teste de API existentes
(Karate, Tavern, Robot Framework) é a combinação simultânea de cinco
características que nenhuma ferramenta pesquisada reúne:

1. Cenário 100% declarativo em JSON — sem sintaxe própria de DSL, sem
   necessidade de escrever código (Java, Python ou outro) por caso de teste.
2. Assert configurado por dado (query + operador + valor esperado), não por
   código — uma pessoa não-programadora consegue editar um cenário.
3. Múltiplas fontes de dados heterogêneas (Oracle, DB2, MongoDB, Kafka) sob
   a mesma interface declarativa.
4. Execução fisicamente desacoplada no tempo entre disparo e validação,
   como funcionalidade central do design — não um workaround.
5. Barreira de entrada baixa o suficiente para uso por equipes de produto
   e QA em homologação funcional, não apenas por desenvolvedores.

## 2. Público-alvo

- Equipes de desenvolvimento (uso técnico, integração em pipelines).
- Equipes de produto e QA funcional (homologação de funcionalidades, sem
  necessidade de escrever código).
- Público internacional — daí a decisão de idioma da seção anterior: o
  produto em si (comandos, schemas, documentação) é em inglês para não
  limitar a adoção a falantes de português.

Toda decisão de design deve ser avaliada também sob a ótica de: *"uma
pessoa de produto, sem experiência em programação, consegue editar isto?"*

## 3. Princípios inegociáveis

### I. Simplicidade sobre abstração
Prioriza-se um conjunto pequeno de scripts diretos sobre um sistema com
muitas camadas. Não criar classes, camadas de abstração ou padrões de
projeto (repository, factory, etc.) que não tenham necessidade concreta e
imediata. Um motor genérico bem desenhado é preferível a muitas funções
especializadas.

### II. Cenários declarativos, sem código por caso de teste
Todo cenário de teste é um arquivo JSON. Não é permitido que a adição de um
novo cenário exija escrever ou alterar código Python. Exceção única: a
adição de um **novo tipo de conector** ou **novo operador de comparação**
exige código — isso é esperado e faz parte do roadmap por feature.

### III. Motor de asserts único e genérico
Existe um único mecanismo de comparação (operadores) reutilizado tanto para
validar a resposta imediata da API (`api_checks`) quanto para validar
dados obtidos de conectores (`validations`). Não deve haver lógica de
comparação duplicada ou paralela entre essas duas verificações.

### IV. Duas fases desacopladas no tempo, nunca fundidas
`thomas request` (dispara e registra) e `thomas validate` (lê o registro
e valida) são comandos independentes, que podem ser executados com
qualquer intervalo de tempo entre si — de segundos a dias. `thomas
validate` pode ser executado **múltiplas vezes** sobre o mesmo registro de
execução, sempre acrescentando uma nova rodada, nunca sobrescrevendo
rodadas anteriores. Isso é um requisito estrutural, não uma opção de
configuração.

### V. Acessibilidade a não-programadores
Qualquer campo de configuração usado no dia a dia (cenários, variáveis
preparatórias) deve ser editável por alguém que só entenda JSON básico. A
complexidade técnica (drivers, conectores, motor de execução) fica
inteiramente encapsulada no código Python, nunca exposta ao usuário final
do cenário.

### VI. Extensibilidade por conector, isolada
Cada tipo de conexão (Oracle, DB2, MongoDB, Kafka, e futuros) é implementado
como um módulo independente, com sua própria dependência **opcional** de
pacote Python (via extras do `pyproject.toml`). A ausência de um driver não
pode impedir o uso dos demais conectores. Cada conector é uma feature
isolada no roadmap.

### VII. Nenhum dado real de terceiros no código público
O repositório público não deve conter, em nenhum momento do seu histórico
de commits, nomes de tabela, schema, endpoint, regra de negócio ou dado de
qualquer sistema real de terceiros. Todos os exemplos usados em
documentação, testes e cenários de demonstração devem ser fictícios,
construídos a partir de especificações públicas quando aplicável. Como o
repositório é publicado logo após a primeira feature (ver seção 10), esta
regra vale **desde o primeiro commit público**, não apenas em uma etapa
final de "preparação para lançamento".

### VIII. Rastreabilidade e auditabilidade completa
Toda execução gera um arquivo de registro imutável (append-only): novas
rodadas de validação são sempre adicionadas, nunca sobrescrevem histórico.
O relatório final deve refletir a linha do tempo completa de tentativas de
validação de cada cenário, não apenas o resultado mais recente.

### IX. Versionamento de schema obrigatório
Todo arquivo de cenário, ambiente, variáveis e execução carrega o campo
`schema_version`. O The Thomas valida esse campo antes de processar qualquer
arquivo e falha de forma clara e imediata se a versão for incompatível com
a versão suportada pela instalação atual.

### X. Relatório como artefato autocontido e bilíngue
O relatório é um único arquivo `.html`, sem dependências externas (CSS, JS
e logo SVG embutidos inline no próprio arquivo). Deve poder ser aberto em
qualquer navegador, anexado a e-mail, ou compartilhado sem pasta de
imagens ou link externo quebrável. O idioma do conteúdo textual do
relatório (não dos dados em si) é determinado por `report_language` no
arquivo de ambiente (`en` ou `pt`), resolvido inteiramente no momento da
geração — o The Thomas não embute um seletor de idioma em tempo de
visualização.

### XI. A documentação de arquitetura é vinculante
Tudo o que está documentado em `docs/architecture/` é normativo, não
apenas ilustrativo — a implementação de qualquer feature deve seguir
exatamente os schemas, contratos, nomes de campo, comandos e
comportamentos ali descritos. Nenhuma implementação pode divergir
silenciosamente do que está documentado. Se, durante a implementação de
uma feature, surgir a necessidade de desviar do que foi especificado em
`docs/architecture/`, o documento correspondente deve ser atualizado
primeiro (ou no mesmo Pull Request), refletindo a decisão de arquitetura
revista — nunca implementar algo diferente do documentado sem atualizar a
documentação junto. Em caso de dúvida sobre qual documento é a fonte de
verdade para um comportamento específico, os documentos em
`docs/architecture/` prevalecem sobre suposições de implementação, e esta
constitution prevalece sobre os documentos de arquitetura (ver seção 8).

### XII. O roadmap reflete o estado real do projeto
`docs/ROADMAP.md` deve ser mantido atualizado a cada avanço de feature —
não é um documento estático escrito uma vez no início do projeto. Sempre
que uma feature muda de status (Não iniciado → Em andamento → Concluído),
a tabela de controle em `docs/ROADMAP.md` deve ser atualizada no mesmo
Pull Request que implementa essa mudança, incluindo o preenchimento da
data de conclusão quando aplicável. Um roadmap desatualizado é tratado
como um defeito de mesma gravidade que um teste quebrado — nenhuma feature
é considerada finalizada enquanto o roadmap não refletir seu estado real
(ver Definition of Done, seção 9).

## 4. Glossário de domínio

| Termo (PT, para referência) | Identificador técnico (EN) | Definição |
|---|---|---|
| Cenário | `scenario` | Arquivo JSON descrevendo um caso de teste: requisição, verificações da API e validações via conector. |
| Funcionalidade | `feature` | Identificador de negócio do cenário, campo obrigatório em todo cenário, usado para agrupamento no relatório. |
| Correlação (ID de correlação) | `correlation` / `correlation_id` | Identificador único que conecta a requisição disparada ao(s) registro(s) de dados a validar depois. Pode vir da resposta da API (`api_response`) ou do próprio payload enviado (`request_payload`). |
| Verificação de API | `api_checks` | Checagem feita imediatamente após a resposta HTTP (status code, corpo), usando o motor de operadores. |
| Validação (via conector) | `validations` | Checagem feita contra uma fonte de dados externa (Oracle, DB2, Mongo, Kafka), potencialmente muito tempo depois da requisição, usando o mesmo motor de operadores. |
| Rodada de validação | `validation_round` | Uma execução do comando `thomas validate` sobre um registro de execução. Cada rodada é registrada com timestamp próprio; podem existir várias rodadas para o mesmo cenário ao longo do tempo. |
| Conector | `connector` | Configuração nomeada de acesso a uma fonte de dados, definida no arquivo de ambiente, com tipo, credenciais e string/URI de conexão. Tabelas, queries e tópicos ficam no cenário, não no conector. |
| Registro de execução | `execution record` | Arquivo JSON gerado por `thomas request` e atualizado por `thomas validate`, contendo todos os cenários incluídos naquela rodada de disparo e o histórico de validações. |
| Ambiente | `environment` | Arquivo de configuração nomeado (ex: `staging.json`) com URL base da API, fuso horário, idioma do relatório, nome do sistema testado, endpoints de `/info` e conectores disponíveis. |
| Variáveis preparatórias | `variables` | Valores fictícios (conta, chave de pagamento, cliente) resolvidos uma única vez antes do início do disparo dos cenários, e reutilizáveis via `{{variable_name}}` em qualquer cenário. |

## 5. Padrões técnicos obrigatórios

- **Linguagem de implementação**: Python 3.10+.
- **Idioma do produto**: inglês em todo comando, schema, mensagem de log,
  mensagem de erro e documentação de arquitetura.
- **Empacotamento**: `pyproject.toml` (PEP 621), sem Poetry. Dependências de
  conector são **extras opcionais** (`thomas[oracle]`, `thomas[kafka]`, etc.).
- **CLI**: comandos `thomas request`, `thomas validate`, `thomas report`.
- **Console**: progresso resumido via `rich` (barra de progresso, tabela
  final). Log detalhado (DEBUG) sempre gravado em arquivo, nunca só no
  console.
- **Relatório**: gerado via Jinja2, HTML único autocontido, inspirado
  visualmente no relatório do Karate, com logo SVG do The Thomas inline, e
  suporte bilíngue (inglês/português) conforme `report_language`.
- **Validação de schema**: `jsonschema` para validar cenários, ambientes,
  variáveis e registros de execução contra os schemas versionados.
- **Sem banco de dados interno**: o The Thomas não persiste estado em banco
  próprio — todo estado vive em arquivos JSON versionáveis/legíveis.

## 6. Segurança e dados sensíveis

- Arquivos de ambiente contêm credenciais (mesmo sendo ambiente de teste) e
  **nunca** devem ser versionados. O repositório deve conter apenas um
  arquivo de exemplo (`config/environments/example.json.dist`) com campos
  vazios/fictícios, versionado; arquivos reais ficam no `.gitignore`.
- Não há requisito de mascaramento de dados no relatório (dados são sempre
  fictícios por definição do processo de teste).
- Nenhuma credencial deve aparecer em log, nem em nível DEBUG.

## 7. Licenciamento e marca

- Código-fonte licenciado sob **Apache 2.0** — permite uso comercial e
  gratuito, exige preservação de avisos de copyright/licença via arquivo
  `NOTICE`, inclui concessão explícita de patente (com cláusula de
  retaliação em caso de litígio) e uma cláusula própria (Seção 6 da
  licença) que já nega, no próprio texto, qualquer concessão de uso de
  marca — reforçando a separação entre licença de código e proteção de
  marca descrita abaixo.
- O logo e o nome "The Thomas" são tratados como **marca do projeto**, protegida
  separadamente da licença de código. O template padrão do relatório
  inclui o logo do The Thomas por convenção do projeto. Forks são livres para
  remover, mas nesse caso não podem se apresentar publicamente como
  "The Thomas" nem usar o nome/logo do projeto.
- **Estratégia de monetização futura (open core)**: a licença permissiva
  do core não impede a criação futura de produtos comerciais separados
  (ex: funcionalidades enterprise, hospedagem, suporte pago), desde que:
  (a) tais produtos sejam desenvolvidos como código **proprietário desde o
  início**, nunca publicados sob Apache 2.0 e depois "fechados"; (b) a
  marca "The Thomas" seja registrada, para impedir que concorrentes vendam
  produtos usando o mesmo nome; (c) caso o projeto passe a aceitar
  contribuições externas relevantes, seja adotado um CLA (Contributor
  License Agreement), para preservar a possibilidade de uso mais amplo do
  código contribuído pela comunidade. Nenhuma funcionalidade do roadmap
  atual (ver `docs/ROADMAP.md`) é proprietária — esta seção documenta
  apenas a estratégia, sem afetar o escopo técnico presente.

## 8. Governança

- Aprovação de mudanças em cenários de exemplo, schemas e código segue o
  fluxo padrão de Pull Request no Git — o The Thomas não implementa mecanismo
  próprio de aprovação.
- Mudanças de schema que quebrem compatibilidade retroativa exigem
  incremento de `schema_version` e devem manter suporte de leitura (ou
  mensagem de erro clara de incompatibilidade) por ao menos uma versão
  minor anterior.
- Esta constitution é a fonte de verdade para qualquer decisão de design
  não coberta explicitamente pelos documentos de arquitetura. Em caso de
  conflito aparente entre um prompt de feature e esta constitution, a
  constitution prevalece.

## 9. Definition of Done (aplicável a toda feature do roadmap)

Uma feature só é considerada concluída quando:

1. Não introduz código Python necessário para o usuário final descrever um
   novo cenário (Princípio II).
2. Reaproveita o motor de operadores existente, sem lógica de comparação
   paralela (Princípio III).
3. Tem exemplo de cenário/configuração fictício, documentado, em inglês.
4. Não adiciona dependência obrigatória nova ao pacote base — apenas via
   extras, se for conector (Princípio VI).
5. Não introduz nenhum dado, nome ou estrutura de sistema real de terceiros
   (Princípio VII) — regra válida desde o primeiro commit público (ver
   seção 10).
6. Possui testes automatizados cobrindo o comportamento novo.
7. Segue estritamente o que está documentado em `docs/architecture/`
   (Princípio XI); qualquer divergência necessária já foi refletida nesses
   documentos antes ou junto desta entrega, não apenas no código.
8. Atualiza a documentação de arquitetura relevante (`docs/architecture/`,
   em inglês), se o comportamento documentado mudar.
9. Atualiza `docs/ROADMAP.md` (Princípio XII): status da feature marcado
   como "Concluído" e data de conclusão preenchida na tabela de controle.

## 10. Momento de publicação

Diferente de um modelo em que a publicação ocorre apenas ao final do
roadmap, o The Thomas é publicado publicamente **logo após a conclusão da
primeira feature (F00 — Core)**, pois  o comando `thomas request` sozinho 
já é uma ferramenta útil e utilizável em outros contextos.

Consequência prática: a feature F01 do roadmap (ver `docs/ROADMAP.md`) é
dedicada exclusivamente a essa publicação inicial (licença, `NOTICE`,
README, higienização, marca), e ocorre **antes** das demais features
técnicas (motor de validação, conectores, relatório, múltiplos
ambientes). A partir de F01, toda feature subsequente é desenvolvida
diretamente no repositório já público, sob as mesmas regras de
higienização do Princípio VII, sem necessidade de uma etapa final de
"preparação para lançamento".
