# AGENTS.md

## Projeto e arquitetura

Sul Taça é uma aplicação Streamlit com uma interface pública (`app.py`) e um
painel local de qualidade (`painel_qualidade.py`). O atendimento combina RAG
interno (`busca_semantica.py`), comparação externa controlada por URL
(`consulta_url.py`) e persistência local de métricas em SQLite (`qualidade.py`).
Consulte [plans/metricas-v2.md](plans/metricas-v2.md) antes de alterar métricas.

## Responsabilidades

- `app.py`: interface Streamlit e orquestração dos componentes.
- `atendimento.py`: tarefa, transições, envelope e classificação do resultado.
- `busca_semantica.py`: catálogo/documentos, embeddings, recuperação e resposta.
- `consulta_url.py`: roteamento e comparação externa delimitada.
- `qualidade.py`: esquema, persistência, privacidade e idempotência.
- `painel_qualidade.py`: consultas e apresentação local; não publicar sem
  autenticação.
- `tests/`: testes offline de domínio, persistência e jornadas Streamlit.

Não misture mudanças visuais, conversacionais e de métricas sem necessidade.
Preserve o painel separado da interface pública.

## Comandos de validação

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m py_compile app.py atendimento.py busca_semantica.py \
  consulta_url.py qualidade.py painel_qualidade.py tests/*.py
git diff --check
```

Testes offline não podem chamar Gemini nem depender de rede. Para execução
manual: `.venv/bin/streamlit run app.py`. O painel usa comando próprio descrito
no README.

## Convenções

- Python simples, funções pequenas e nomes em português coerentes com o domínio.
- Use `message_id`, `session_id` e `task_id` anônimos e idempotentes.
- Separe intenção, resultado entregue, mecanismo técnico e avaliação.
- Classificações de resultado são não excludentes.
- Não derive resultado comercial apenas da última mensagem da pessoa.
- Comprove recomendações por metadados estruturados da própria execução,
  incluindo nome ou código dos produtos Sul Taça indicados; não faça uma
  segunda chamada Gemini para classificar.
- Perguntas locais, menus, navegação e mensagens operacionais não são respostas
  substantivas nem avaliáveis.
- Prefira APIs oficiais do Streamlit; CSS deve ser pequeno e limitado a classes
  próprias do projeto.

## Privacidade e segurança

- Nunca versionar `.env`, credenciais, SQLite ou arquivos auxiliares do banco.
- Não imprimir, copiar ou revelar chaves em comandos, testes ou handoffs.
- Não persistir nome, e-mail, telefone, CPF, IP, cookies ou histórico completo.
- Metadados anônimos podem existir sem avaliação.
- Pergunta e resposta somente são persistidas após avaliação e sanitização.
- Falhas técnicas e bloqueios persistem somente códigos controlados, sem textos
  e sem avaliação; página insuficiente segue a política própria de elegibilidade.
- Registre falhas por código/etapa, nunca por conteúdo pessoal bruto.
- Não alterar nem excluir dados locais sem autorização explícita.

## Qualidade mínima

- Avaliação única por `message_id`; cliques e reruns não podem duplicar ou trocar
  a primeira avaliação.
- Recomendações e comparações devem refletir resultados entregues, não intenção.
- Uma interação pode contar simultaneamente em mais de uma classificação.
- Testes de métricas devem percorrer jornadas reais entre turnos; injetar a flag
  esperada diretamente não comprova a classificação do fluxo.
- Toda mudança funcional exige testes offline, `py_compile` e `git diff --check`.
- Preserve acessibilidade, comportamento responsivo e fluxos existentes.

## Trabalho com Codex

- Inspecione o estado e o diff antes de editar; preserve alterações do usuário.
- Declare arquivos e escopo antes de mudanças relevantes.
- Não faça chamadas Gemini durante diagnóstico ou testes offline.
- Não faça stage, commit, push, migração ou limpeza de banco sem solicitação.
- Trabalhe em checkpoints pequenos e verificáveis; interrompa ao encontrar uma
  decisão de Produto que altere semântica ou escopo.
- Handoffs devem ser curtos por padrão e destacar resultado, arquivos,
  validações, estado do Git e próxima decisão.
