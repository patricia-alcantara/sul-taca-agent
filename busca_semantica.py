import faiss
import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

from ler_documentos import (
    PASTA_DOCUMENTOS,
    dividir_em_chunks,
    encontrar_pdfs,
    extrair_paginas,
)
DIMENSAO_EMBEDDING = 768

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
    cliente,
) -> str:
    prompt = f"""
Você é um assistente da loja de vinhos Sul Taça.

Responda em português usando exclusivamente as informações fornecidas no contexto.
Não invente produtos, preços, estoque, políticas ou características.
Não atribua certificações, selos ou garantias que não estejam explicitamente
no contexto. Se estiver escrito apenas "Vegano: Sim", diga somente que o vinho
é vegano.
Se o contexto não contiver informação suficiente, diga claramente que não encontrou
essa informação nos documentos da Sul Taça.
Se fizer uma recomendação, explique brevemente o motivo.
Ao final, informe o documento e a página usados como fonte.

CONTEXTO:
{contexto}

PERGUNTA:
{pergunta}
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
    cliente,
) -> str:
    vetor_pergunta = gerar_embedding_pergunta(pergunta, cliente)
    _, posicoes = indice.search(vetor_pergunta, k=3)

    contexto = montar_contexto(chunks, posicoes)

    return gerar_resposta(pergunta, contexto, cliente)

def main() -> None:
    load_dotenv()
    cliente = genai.Client()

    chunks = carregar_chunks()
    vetores = gerar_embeddings(chunks, cliente)
    indice = criar_indice(vetores)

    print("\nSul Taça pronta. Digite sua pergunta ou escreva 'sair' para encerrar.")

    while True:
        pergunta = input("\nVocê: ").strip()

        if pergunta.lower() == "sair":
            print("\nSessão encerrada.")
            break

        if not pergunta:
            print("Digite uma pergunta para continuar.")
            continue

        resposta = responder_pergunta(
            pergunta,
            chunks,
            indice,
            cliente,
        )

        print("\nSul Taça:")
        print(resposta)

if __name__ == "__main__":
    main()