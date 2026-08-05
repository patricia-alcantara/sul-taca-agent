from pathlib import Path

from pypdf import PdfReader


PASTA_DOCUMENTOS = Path(__file__).parent / "documentos"


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


if __name__ == "__main__":
    main()