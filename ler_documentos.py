from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter

from pypdf import PdfReader


PASTA_DOCUMENTOS = Path(__file__).parent / "documentos"

TAMANHO_CHUNK = 1000
SOBREPOSICAO_CHUNK = 300

def encontrar_pdfs(pasta: Path) -> list[Path]:
    return sorted(pasta.glob("*.pdf"))


def extrair_paginas(arquivo_pdf: Path) -> list[dict]:
    leitor = PdfReader(arquivo_pdf)
    paginas_extraidas = []

    for numero_pagina, pagina in enumerate(leitor.pages, start=1):
        paginas_extraidas.append(
            {
                "documento": arquivo_pdf.name,
                "pagina": numero_pagina,
                "texto": pagina.extract_text() or "",
            }
        )

    return paginas_extraidas

def dividir_em_chunks(paginas: list[dict]) -> list[dict]:
    divisor = RecursiveCharacterTextSplitter(
        chunk_size=TAMANHO_CHUNK,
        chunk_overlap=SOBREPOSICAO_CHUNK,
    )

    chunks = []

    for pagina in paginas:
        textos_divididos = divisor.split_text(pagina["texto"])

        for numero_chunk, texto_chunk in enumerate(
            textos_divididos,
            start=1,
        ):
            chunks.append(
                {
                    "documento": pagina["documento"],
                    "pagina": pagina["pagina"],
                    "chunk": numero_chunk,
                    "texto": texto_chunk,
                }
            )

    return chunks

def exibir_resultado(
    arquivo_pdf: Path,
    paginas_extraidas: list[dict],
) -> None:
    quantidade_caracteres = sum(
        len(pagina["texto"])
        for pagina in paginas_extraidas
    )

    print(
        f"- {arquivo_pdf.name}: "
        f"{len(paginas_extraidas)} página(s), "
        f"{quantidade_caracteres} caracteres extraídos"
    )


def main() -> None:
    arquivos_pdf = encontrar_pdfs(PASTA_DOCUMENTOS)
    todas_as_paginas = []

    print(f"PDFs encontrados: {len(arquivos_pdf)}")

    for arquivo_pdf in arquivos_pdf:
        paginas_extraidas = extrair_paginas(arquivo_pdf)
        todas_as_paginas.extend(paginas_extraidas)
        exibir_resultado(arquivo_pdf, paginas_extraidas)

    print(f"Total de páginas processadas: {len(todas_as_paginas)}")

    chunks = dividir_em_chunks(todas_as_paginas)

    print(f"Total de chunks gerados: {len(chunks)}")

    if chunks:
        tamanhos = [len(chunk["texto"]) for chunk in chunks]

        print(f"Menor chunk: {min(tamanhos)} caracteres")
        print(f"Maior chunk: {max(tamanhos)} caracteres")
        
if __name__ == "__main__":
    main()