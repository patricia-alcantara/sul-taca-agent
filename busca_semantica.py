from pathlib import Path

import faiss
import numpy as np
from google.genai import types

from ler_documentos import (
    PASTA_DOCUMENTOS,
    dividir_em_chunks,
    encontrar_pdfs,
    extrair_paginas,
)

DIMENSAO_EMBEDDING = 768

ARQUIVO_PROMPT = (
    Path(__file__).parent
    / "prompts"
    / "prompt_jessi_sul_taca.md"
)


def carregar_prompt_jessi() -> str:
    prompt_completo = ARQUIVO_PROMPT.read_text(
        encoding="utf-8"
    )

    marcador = "## Informações dinâmicas fornecidas pela aplicação"

    return prompt_completo.split(marcador)[0].strip()

def montar_historico_conversa(
    historico: list[dict],
) -> str:
    if not historico:
        return "Ainda não há mensagens anteriores nesta sessão."

    mensagens_formatadas = []

    for mensagem in historico[-6:]:
        autor = (
            "Usuário"
            if mensagem["papel"] == "usuario"
            else "Jessi"
        )

        mensagens_formatadas.append(
            f"{autor}: {mensagem['conteudo']}"
        )

    return "\n\n".join(mensagens_formatadas)


def carregar_chunks() -> list[dict]:
    todas_as_paginas = []

    for arquivo_pdf in encontrar_pdfs(PASTA_DOCUMENTOS):
        paginas_extraidas = extrair_paginas(arquivo_pdf)
        todas_as_paginas.extend(paginas_extraidas)

    return dividir_em_chunks(todas_as_paginas)

def gerar_embeddings(chunks: list[dict], cliente) -> np.ndarray:
    textos = [chunk["texto"] for chunk in chunks]

    resultado = cliente.models.embed_content(
        model="gemini-embedding-001",
        contents=textos,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=DIMENSAO_EMBEDDING,
        ),
    )

    vetores = np.array(
        [embedding.values for embedding in resultado.embeddings],
        dtype="float32",
    )

    return vetores

def criar_indice(vetores: np.ndarray):
    faiss.normalize_L2(vetores)

    indice = faiss.IndexFlatIP(DIMENSAO_EMBEDDING)
    indice.add(vetores)

    return indice

def gerar_embedding_pergunta(
    pergunta: str,
    cliente,
) -> np.ndarray:
    resultado = cliente.models.embed_content(
        model="gemini-embedding-001",
        contents=pergunta,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=DIMENSAO_EMBEDDING,
        ),
    )

    vetor = np.array(
        [resultado.embeddings[0].values],
        dtype="float32",
    )

    faiss.normalize_L2(vetor)

    return vetor

def montar_contexto(
    chunks: list[dict],
    posicoes: np.ndarray,
) -> str:
    trechos = []

    for posicao in posicoes[0]:
        chunk = chunks[posicao]

        trecho = (
            f"Fonte: {chunk['documento']}, "
            f"página {chunk['pagina']}\n"
            f"{chunk['texto']}"
        )

        trechos.append(trecho)

    return "\n\n---\n\n".join(trechos)

def gerar_resposta(
    pergunta: str,
    contexto: str,
    historico: list[dict],
    cliente,
) -> str:
    instrucoes_jessi = carregar_prompt_jessi()
    historico_formatado = montar_historico_conversa(
        historico
    )

    prompt = f"""
{instrucoes_jessi}

## Histórico da conversa

{historico_formatado}

O histórico serve como contexto da sessão, não como fonte
factual sobre a Sul Taça. Não repita apresentações, perguntas
ou informações já registradas nele.

## Contexto recuperado dos documentos

Os trechos abaixo são candidatos recuperados por
similaridade. A presença de um trecho não significa que ele
responda à pergunta. Utilize somente informações que
sustentem explicitamente a afirmação feita. Se nenhum trecho
responder à pergunta exata, informe que não encontrou a
informação nos documentos.

{contexto}

## Mensagem atual do usuário

{pergunta}

Responda usando as instruções da Jessi e o histórico da
conversa. Use os documentos somente para afirmações
explicitamente sustentadas pelos trechos recuperados.

Quando utilizar uma informação factual dos documentos,
indique ao final somente o documento e a página que
sustentam diretamente essa informação. Não cite uma fonte
apenas relacionada ao assunto.
"""

    resultado = cliente.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
    )

    return resultado.text

def responder_pergunta(
    pergunta: str,
    chunks: list[dict],
    indice,
    historico: list[dict],
    cliente,
) -> str:
    vetor_pergunta = gerar_embedding_pergunta(
        pergunta,
        cliente,
    )
    _, posicoes = indice.search(vetor_pergunta, k=3)

    contexto = montar_contexto(chunks, posicoes)

    return gerar_resposta(
        pergunta,
        contexto,
        historico,
        cliente,
    )
