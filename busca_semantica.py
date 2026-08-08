from pathlib import Path
import re
import unicodedata
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

def normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    return re.sub(r"\s+", " ", texto).strip()


def identificar_maioridade(mensagem: str) -> bool | None:
    mensagem_normalizada = normalizar_texto(mensagem)

    idade_informada = re.search(
        r"\b(?:eu\s+)?(?:ainda\s+)?tenho\s+(\d{1,2})\s+anos?\b",
        mensagem_normalizada,
    )

    if idade_informada:
        idade = int(idade_informada.group(1))
        return idade >= 18

    confirmacoes_explicitas = (
        "tenho mais de 18",
        "sou maior de 18",
        "sou maior de idade",
        "ja sou maior de idade",
    )

    if any(
        confirmacao in mensagem_normalizada
        for confirmacao in confirmacoes_explicitas
    ):
        return True

    if mensagem_normalizada in {
        "sim",
        "sim, tenho",
        "tenho",
        "confirmo",
    }:
        return True

    if mensagem_normalizada in {
        "nao",
        "não",
        "sou menor de idade",
        "tenho menos de 18",
    }:
        return False

    return None

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

def main() -> None:
    load_dotenv()
    cliente = genai.Client()

    chunks = carregar_chunks()
    vetores = gerar_embeddings(chunks, cliente)
    indice = criar_indice(vetores)
    historico = []
    maioridade_confirmada = False
    pergunta_pendente = None

    print(
        "\nSul Taça pronta. Digite sua pergunta "
        "ou escreva 'sair' para encerrar."
    )

    while True:
        pergunta = input("\nVocê: ").strip()

        if pergunta.lower() == "sair":
            print("\nSessão encerrada.")
            break

        if not pergunta:
            print("Digite uma pergunta para continuar.")
            continue

        if not maioridade_confirmada:
            resultado_maioridade = identificar_maioridade(
                pergunta
            )

            if resultado_maioridade is False:
                pergunta_pendente = None
                print(
                    "\nSul Taça:\n"
                    "Não posso orientar a compra de bebidas "
                    "alcoólicas para menores de 18 anos."
                )
                continue

            if resultado_maioridade is None:
                pergunta_pendente = pergunta
                print(
                    "\nSul Taça:\n"
                    "Antes de continuar, preciso confirmar: "
                    "você tem 18 anos ou mais?"
                )
                continue

            maioridade_confirmada = True

            historico.append(
                {
                    "papel": "usuario",
                    "conteudo": (
                        "Confirmo que tenho 18 anos ou mais."
                    ),
                }
            )

            if pergunta_pendente:
                pergunta = pergunta_pendente
                pergunta_pendente = None
            else:
                mensagem_normalizada = normalizar_texto(
                    pergunta
                )
                confirmacoes_isoladas = {
                    "sim",
                    "sim, tenho",
                    "tenho",
                    "confirmo",
                    "tenho mais de 18 anos",
                    "sou maior de 18 anos",
                    "sou maior de idade",
                    "ja sou maior de idade",
                }

                if mensagem_normalizada in confirmacoes_isoladas:
                    print(
                        "\nSul Taça:\n"
                        "Obrigada pela confirmação. "
                        "Como posso ajudar?"
                    )
                    continue

        resposta = responder_pergunta(
            pergunta,
            chunks,
            indice,
            historico,
            cliente,
        )

        historico.append(
            {
                "papel": "usuario",
                "conteudo": pergunta,
            }
        )
        historico.append(
            {
                "papel": "jessi",
                "conteudo": resposta,
            }
        )

        print("\nSul Taça:")
        print(resposta)

if __name__ == "__main__":
    main()