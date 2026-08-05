from pathlib import Path

from pypdf import PdfReader


PASTA_DOCUMENTOS = Path(__file__).parent / "documentos"


def encontrar_pdfs(pasta: Path) -> list[Path]:
    return sorted(pasta.glob("*.pdf"))


def extrair_texto(arquivo_pdf: Path) -> tuple[str, int]:
    leitor = PdfReader(arquivo_pdf)

    texto = "\n".join(
        pagina.extract_text() or ""
        for pagina in leitor.pages
    )

    return texto, len(leitor.pages)


def exibir_resultado(
    arquivo_pdf: Path,
    texto: str,
    quantidade_paginas: int,
) -> None:
    print(
        f"- {arquivo_pdf.name}: "
        f"{quantidade_paginas} página(s), "
        f"{len(texto)} caracteres extraídos"
    )


def main() -> None:
    arquivos_pdf = encontrar_pdfs(PASTA_DOCUMENTOS)

    print(f"PDFs encontrados: {len(arquivos_pdf)}")

    for arquivo_pdf in arquivos_pdf:
        texto, quantidade_paginas = extrair_texto(arquivo_pdf)
        exibir_resultado(
            arquivo_pdf,
            texto,
            quantidade_paginas,
        )


if __name__ == "__main__":
    main()