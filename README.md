# Sul Taça Agent 🍷

Agente de inteligência artificial desenvolvido para a Sul Taça, um e-commerce fictício de vinhos com sede em Porto Alegre, no Rio Grande do Sul.

O projeto faz parte do Challenge Alura Agent e tem como objetivo facilitar o acesso às informações da loja. Por meio de uma interface de conversa, as pessoas poderão fazer perguntas sobre produtos, entregas, devoluções, privacidade e outras políticas da empresa.

## Objetivo do projeto

O agente será capaz de consultar os documentos da Sul Taça e gerar respostas claras em linguagem natural. Dessa forma, a pessoa não precisará procurar manualmente a informação em diferentes arquivos.

Além de responder dúvidas sobre a operação da loja, o agente também poderá utilizar o catálogo para sugerir vinhos de acordo com preferências, ocasiões e harmonizações.

## Base de conhecimento

O agente utilizará os seguintes documentos em PDF:

- Política de Privacidade
- Política de Reembolso e Devoluções
- Perguntas Frequentes
- Guia de Envios e Entregas
- Termos e Condições
- Catálogo de Vinhos

Todos os documentos estão disponíveis na pasta `documentos`.

## Arquitetura planejada

A aplicação utilizará uma arquitetura RAG (Geração Aumentada por Recuperação).

O fluxo será composto pelas seguintes etapas:

1. Leitura dos documentos em PDF.
2. Divisão do conteúdo em trechos menores.
3. Transformação dos trechos em representações numéricas chamadas embeddings.
4. Armazenamento dos embeddings em um banco vetorial.
5. Busca dos trechos mais relacionados à pergunta.
6. Envio da pergunta e do contexto encontrado para o modelo de linguagem.
7. Geração da resposta com indicação da fonte consultada.

## Tecnologias planejadas

- Python
- Streamlit
- LangChain
- PyPDF
- FAISS
- Google Gemini

As tecnologias poderão ser ajustadas durante o desenvolvimento, de acordo com os testes e as necessidades do projeto.

## Exemplos de perguntas

- Qual é o prazo de entrega para a região Sul?
- O que devo fazer se uma garrafa chegar quebrada?
- Posso devolver um vinho depois de recebê-lo?
- Como a Sul Taça utiliza os meus dados pessoais?
- Quais vinhos combinam com risoto de cogumelos?
- Existe algum vinho vegano no catálogo?
- Quais são os vinhos mais baratos disponíveis?

## Status do projeto

Em desenvolvimento.

### Etapas concluídas

- Definição do contexto e da identidade da empresa fictícia.
- Criação da documentação da Sul Taça.
- Organização da base de conhecimento em PDF.
- Criação do catálogo de vinhos.
- Configuração do repositório e do versionamento com Git.

### Próximas etapas

- Implementar a leitura e o processamento dos PDFs.
- Construir o sistema de busca nos documentos.
- Integrar o modelo de linguagem.
- Criar a interface conversacional.
- Testar as respostas do agente.
- Publicar a aplicação na nuvem.
- Adicionar exemplos de respostas e evidências do funcionamento.

## Aviso

A Sul Taça é uma empresa fictícia criada exclusivamente para fins educacionais. Os produtos, preços, políticas e demais informações presentes neste projeto não representam uma operação comercial real.