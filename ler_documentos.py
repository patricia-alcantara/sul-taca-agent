from pathlib import Path

from pypdf import PdfReader


PASTA_DOCUMENTOS = Path(__file__).parent / "documentos"
arquivos_pdf = sorted(PASTA_DOCUMENTOS.glob("*.pdf"))

print(f"PDFs encontrados: {len(arquivos_pdf)}")

for arquivo_pdf in arquivos_pdf:
    leitor = PdfReader(arquivo_pdf)

    texto = "\n".join(
        pagina.extract_text() or ""
        for pagina in leitor.pages
    )

    print(
        f"- {arquivo_pdf.name}: "
        f"{len(leitor.pages)} página(s), "
        f"{len(texto)} caracteres extraídos"
    )