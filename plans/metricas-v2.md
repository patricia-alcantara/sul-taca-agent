# Métricas v2 — fato de interação e classificações

**Status:** MVP implementado, validado offline e aprovado manualmente em
12/08/2026. Checkpoints 1 a 6 concluídos; o refinamento visual previsto no
checkpoint 7 foi incorporado ao painel e aprovado no aceite final.

## Problema

A classificação atual é gravada junto da resposta elegível e depende demais da
última mensagem da pessoa. Em jornadas guiadas, a intenção de recomendação pode
começar no submenu, enquanto a continuação contém apenas “macarronada” ou “até
R$ 100”. A resposta final pode recomendar corretamente um produto e ainda ser
registrada sem a classificação de recomendação.

A tabela atual também reúne o fato da resposta, classificações comerciais e a
avaliação em uma única estrutura. Isso atende ao MVP inicial, mas limita a
distinção entre intenção, resultado e mecanismo técnico.

## Decisão arquitetural

Adotar um modelo enxuto de **fato de interação com classificações não
excludentes**, preservando o painel simples e separando:

1. tarefa conversacional e intenção entre turnos;
2. resultado efetivamente entregue;
3. mecanismo, rota e status técnico;
4. avaliação opcional e textos sanitizados.

Os dados atuais são de teste, mas o checkpoint 2 autorizou sua preservação. A
migração v1 → v2 é transacional e idempotente para evitar reconstrução ou perda
dos registros existentes. Esta decisão não implica event sourcing nem
rastreamento completo da jornada.

## Definições de Produto

- **Recomendação realizada:** resposta substantiva que indica explicitamente ao
  menos um produto Sul Taça como adequado a uma necessidade, preferência ou
  ocasião.
- Orientação sem rótulo específico não é recomendação realizada.
- **Comparação realizada:** contraste efetivo entre dois ou mais produtos.
- Uma interação pode ser simultaneamente comparação e recomendação.
- Intenção ou tentativa não equivale a resultado realizado.
- Página insuficiente pode registrar intenção e status, mas não comparação
  realizada.
- Perguntas locais, menus e esclarecimentos não são respostas substantivas nem
  avaliáveis.
- Recomendações e comparações não representam compra, conversão, receita ou
  intenção comercial confirmada.

## Modelo conceitual

### Tarefa conversacional em memória

```text
tarefa_atual
├── task_id anônimo
├── intencoes controladas
├── origem controlada
├── etapa
└── contexto operacional mínimo
```

A tarefa preserva a intenção entre turnos sem persistir histórico completo ou
texto pessoal. Ela deve ser concluída, substituída ou limpa de forma explícita.

### Envelope de resultado

```text
resultado_atendimento
├── texto
├── natureza_resposta
├── tipo_atendimento
├── rota_tecnica
├── mecanismo
├── status
├── produtos_sul_taca[]   # nome e/ou código controlado
├── classificacoes_realizadas[]
├── etapa_falha?
└── latencia_ms?
```

`classificacoes_realizadas` descreve o que foi entregue, não o que foi pedido.
Latência e falha ficam preparadas no modelo, mas podem permanecer nulas nesta
implementação.

A comprovação de recomendação deve nascer dos metadados estruturados produzidos
pela própria execução. O envelope precisa identificar ao menos um produto Sul
Taça por nome ou código e registrar que ele foi indicado como adequado à
necessidade, preferência ou ocasião. A classificação não pode depender apenas
da última mensagem nem usar uma segunda chamada Gemini. Quando houver geração
por modelo, texto e metadados estruturados devem resultar da mesma execução e
ser validados pela orquestração contra o catálogo recuperado.

### Persistência proposta

```text
interacoes
├── message_id PK
├── session_id anônimo
├── task_id anônimo
├── criada_em
├── elegivel
├── natureza_resposta
├── tipo_atendimento
├── rota_tecnica
├── mecanismo
├── status
├── etapa_falha NULL
└── latencia_ms NULL

classificacoes_interacao
├── message_id FK
├── dimensao          # intencao | resultado
├── classificacao     # recomendacao | comparacao | ...
└── PK(message_id, dimensao, classificacao)

avaliacoes
├── message_id PK/FK
├── avaliacao         # 1 | 0
├── criada_em
├── pergunta_sanitizada
└── resposta_sanitizada
```

As chaves e restrições devem permanecer portáveis para um banco relacional
compartilhado no futuro.

## Ciclo de vida

1. Uma entrada direta ou escolha guiada inicia/atualiza uma tarefa anônima.
2. Perguntas locais solicitam contexto, mas não criam interação elegível.
3. Continuações curtas complementam a tarefa sem substituir sua intenção.
4. A orquestração produz texto e envelope de resultado na mesma execução.
5. Só resultados efetivamente entregues recebem classificações de resultado.
6. A interação mínima é persistida com `message_id` idempotente.
7. A avaliação cria uma relação 1:1 e persiste pergunta/resposta sanitizadas.
8. Reruns e cliques repetidos não criam registros nem alteram a primeira nota.

Elegibilidade é uma decisão explícita e não depende somente de
`natureza_resposta = resposta_substantiva`. Uma página externa recuperada, mas
insuficiente, gera orientação útil para o próximo passo: permanece elegível,
recebe `status = insuficiente` e não recebe resultado `recomendacao` ou
`comparacao`.

### Tratamento de falhas e insuficiência

- **Falha técnica:** indisponibilidade, cota, exceção de recuperação ou geração;
  persiste apenas metadados controlados de mecanismo, status e etapa da falha,
  sem textos e sem avaliação.
- **Bloqueio de segurança:** interrupção determinística por regra de proteção;
  registra status controlado quando necessário para Engenharia, sem textos, sem
  avaliação e sem resultado comercial.
- **Página insuficiente:** recuperação externa concluída sem dados suficientes;
  é uma orientação elegível, pode receber avaliação e registra intenção e
  `status = insuficiente`, mas não comparação ou recomendação realizada.

### Vocabulários controlados iniciais

- natureza: `resposta_substantiva`, `pedido_esclarecimento`, `navegacao`,
  `mensagem_operacional`, `orientacao_recuperacao`;
- atendimento: `catalogo_documentos`, `comparacao_externa`, `fluxo_guiado`,
  `orientacao_sem_consulta`;
- mecanismo: `rag_interno`, `url_context`, `hibrido`, `regra_local`, `nenhum`;
- status: `sucesso`, `insuficiente`, `falha_tecnica`, `bloqueio_seguranca`;
- intenção: `recomendacao`, `comparacao`, `consulta_catalogo_politica`,
  `orientacao_operacional`;
- resultado: `recomendacao`, `comparacao`, `resposta_catalogo_politica`,
  `orientacao_operacional`;
- etapa de falha: `inicializacao`, `roteamento`, `recuperacao_interna`,
  `recuperacao_externa`, `geracao`, `persistencia`, `renderizacao`.

O checkpoint 1 deve validar e congelar esses valores antes de o esquema ser
criado. Alterações posteriores exigem compatibilidade explícita com os dados.

## Métricas derivadas

### Qualidade

- respostas elegíveis: interações com `elegivel = 1`;
- positivas e negativas: avaliações existentes;
- participação: avaliações / respostas elegíveis;
- qualidade por tipo: junção de interação e avaliação;
- detalhes textuais: somente interações avaliadas.

### Produto e comercial

- recomendações: interações com classificação de **resultado** `recomendacao`;
- comparações: interações com classificação de **resultado** `comparacao`;
- contexto de tentativa: dimensão `intencao`, origem, status e tipo;
- uma interação pode contribuir para ambas as contagens.

### Engenharia

- rota, mecanismo, status e tipo de atendimento desde a primeira versão;
- latência, código de erro e etapa da falha como evolução compatível;
- nenhuma mensagem bruta de erro ou histórico completo persistido.

## Checkpoints verificáveis

### 1. Tarefa conversacional e envelope de resultado

**Status:** aprovado manualmente em 11/08/2026.

- definir vocabulários controlados para natureza da resposta, tipo de
  atendimento, mecanismo, status, intenção, resultado e etapa de falha;
- definir estados, transições, conclusão, substituição e limpeza da tarefa;
- representar intenção e resultado separadamente;
- incluir produtos Sul Taça identificados por nome ou código no envelope;
- produzir texto e metadados na mesma execução, sem segunda chamada Gemini;
- cobrir continuações como “macarronada” e “até R$ 100”;
- provar que esclarecimentos não são substantivos nem avaliáveis.

**Saída:** testes de domínio e jornadas Streamlit passando sem persistência v2.

### 2. Esquema e persistência

**Status:** implementado e validado offline em 11/08/2026.

- criar tabelas, restrições, chaves estrangeiras e índices mínimos;
- garantir tags não excludentes e idempotência;
- manter textos nulos até avaliação e sanitizá-los no registro do feedback;
- reconstruir o banco de teste somente após autorização explícita.

**Saída:** testes de repositório com SQLite temporário e banco vazio.

### 3. Integração com fluxos reais

**Status:** implementado, validado offline e aprovado manualmente em
12/08/2026.

**Definição operacional de forma de atendimento:** comparação externa tem
precedência sobre orientação sem consulta; orientação sem consulta tem
precedência sobre fluxo guiado; uma tarefa ativa iniciada em `menu_guiado` é
registrada como fluxo guiado; as demais perguntas diretas ficam como catálogo e
documentos. O mecanismo permanece responsável pela dimensão técnica. Registros
migrados preservam integralmente sua classificação histórica.

- integrar recomendação direta e guiada, catálogo, políticas e comparação;
- distinguir página insuficiente de comparação realizada;
- permitir comparação + recomendação na mesma interação;
- preservar erros, bloqueios, menus e navegação fora das métricas indevidas.

**Saída:** jornadas reais entre turnos, sem injeção direta de flags esperadas.

### 4. Painel

**Status:** implementado, validado offline e aprovado manualmente em
12/08/2026.

- manter os blocos simples de qualidade e uso;
- consultar classificações de resultado para recomendações e comparações;
- manter textos apenas na tabela de avaliadas;
- expor rota/mecanismo como contexto secundário de Engenharia.

**Saída:** painel vazio e preenchido funcionando sem cache de métricas.

### 5. Testes offline e jornadas

**Status:** concluído em 12/08/2026, com suíte offline, `py_compile` e
`git diff --check` aprovados.

- executar toda a suíte sem Gemini ou rede;
- cobrir recomendação guiada com continuação curta e produto explícito;
- cobrir orientação sem produto, comparação efetiva, comparação com
  recomendação e página insuficiente;
- cobrir idempotência, privacidade, rerun, métricas e SQLite vazio;
- executar `py_compile` e `git diff --check`.

**Saída:** suíte verde e evidência de que a classificação nasce do fluxo real.

### 6. Aceite manual

**Status:** aprovado em 12/08/2026 após duas execuções dos critérios finais.

- validar feedback somente em respostas explicitamente elegíveis, incluindo
  orientação de página insuficiente;
- conferir recomendações e comparações contra as respostas exibidas;
- validar painel, responsividade e ausência de regressão conversacional;
- decidir limpeza do banco local de teste antes do commit final.

**Saída:** aceite de Produto documentado.

### 7. Aceite visual do painel

**Status:** incorporado ao painel do MVP e aprovado manualmente em 12/08/2026.

Checkpoint separado e posterior ao aceite funcional:

- preservar o tema escuro exclusivo do painel;
- usar roxo nos títulos e valores principais;
- manter corpo, textos auxiliares e tabelas em off-white;
- verificar contraste WCAG AA nos fundos principal e secundário;
- não alterar consultas ou semântica das métricas durante o refinamento visual.

**Saída:** aceite visual documentado após métricas e jornadas aprovadas.

## Separação de responsabilidades prevista

- `atendimento.py`: tarefa conversacional, transições, envelope e classificação;
- `qualidade.py`: esquema, persistência, privacidade e idempotência;
- `painel_qualidade.py`: consultas das métricas e apresentação;
- `app.py`: interface e orquestração, sem regras de classificação dispersas.

## Critérios de aceite

- recomendação e comparação seguem exatamente as definições de Produto;
- intenção e resultado podem ser consultados separadamente;
- classificações de resultado são não excludentes;
- perguntas locais e operações não criam avaliação nem resultado comercial;
- metadados podem existir sem feedback, sem conteúdo pessoal bruto;
- textos sanitizados existem somente após avaliação;
- feedback permanece idempotente por `message_id`;
- “macarronada” preserva a tarefa e a recomendação posterior é contabilizada;
- página insuficiente não conta como comparação realizada;
- página insuficiente permanece elegível com status controlado;
- falhas técnicas e bloqueios não são avaliáveis e não persistem textos;
- recomendações comprovam no envelope ao menos um produto Sul Taça identificado;
- painel vazio, métricas e jornadas funcionam offline;
- fluxos atuais da Jessi não sofrem regressão.

## Privacidade

- persistir apenas identificadores anônimos e códigos controlados;
- não armazenar nome, e-mail, telefone, CPF, IP, cookies ou histórico completo;
- sanitizar textos antes da persistência associada à avaliação;
- evitar texto livre em telemetria de erro;
- manter SQLite e auxiliares fora do Git;
- painel continua local e não publicado sem autenticação.

## Riscos e mitigação

- **Tarefa obsoleta:** limpar em conclusão, mudança explícita e navegação.
- **Intenção marcada como resultado:** classificar somente no envelope final.
- **Resposta sem produto marcada como recomendação:** exigir produto Sul Taça
  explícito e adequação declarada.
- **Comparação incompleta contabilizada:** exigir contraste efetivo entre dois
  ou mais produtos.
- **Testes artificiais:** validar jornadas completas pela interface/orquestração.
- **Complexidade excessiva:** limitar o escopo às três tabelas e ao painel atual.
- **Dados pessoais em falhas:** persistir códigos e etapas, nunca payload bruto.

## Fora do escopo desta implementação

- banco persistente compartilhado;
- autenticação do painel;
- rastreamento completo da jornada;
- CRM, conversão, receita ou pedidos;
- filtros e visualizações avançadas;
- execução manual de limpeza ou reconstrução do banco local.

## Evolução posterior: integração contínua

Após a conclusão e estabilização das métricas v2, criar um workflow de CI
separado para executar automaticamente:

```text
verificação do conjunto alterado no PR → testes offline → py_compile →
git diff --check ou verificação equivalente
```

O workflow não deve acessar Gemini, credenciais de produção nem banco local e
deve validar que arquivos funcionais alterados possuem cobertura proporcional.
Ele não faz parte dos checkpoints desta implementação.

## Backlog pós-MVP

- instrumentar latência total e etapas controladas antes de criar indicadores
  de tempo no painel;
- avaliar tracing somente se a necessidade operacional justificar a
  complexidade adicional;
- definir uma análise de intenção versus resultado sem reclassificar o legado
  nem confundir tentativa com resultado entregue;
- manter registros sem latência fora de cálculos de tempo, nunca como zero.
