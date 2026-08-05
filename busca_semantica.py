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

def main() -> None:
    load_dotenv()
    cliente = genai.Client()

    chunks = carregar_chunks()
    print(f"Chunks carregados para busca: {len(chunks)}")

    vetores = gerar_embeddings(chunks, cliente)
    indice = criar_indice(vetores)
    print(f"Vetores armazenados no índice: {indice.ntotal}")
    print(f"Formato da matriz de embeddings: {vetores.shape}")

    pergunta = "Quero um vinho vegano para acompanhar risoto de cogumelos."

    vetor_pergunta = gerar_embedding_pergunta(pergunta, cliente)
    pontuacoes, posicoes = indice.search(vetor_pergunta, k=3)

    print(f"\nPergunta: {pergunta}")
    print("\nResultados mais próximos:")

    for ordem, (posicao, pontuacao) in enumerate(
        zip(posicoes[0], pontuacoes[0]),
        start=1,
    ):
        chunk = chunks[posicao]

        print(
            f"\n{ordem}. {chunk['documento']} "
            f"| página {chunk['pagina']} "
            f"| similaridade {pontuacao:.3f}"
        )
        print(chunk["texto"][:500])
        
if __name__ == "__main__":
    main()