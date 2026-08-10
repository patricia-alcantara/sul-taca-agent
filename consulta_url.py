import re
import unicodedata

from google.genai import types

from busca_semantica import carregar_prompt_jessi


MODELO_CONSULTA_URL = "gemini-3.6-flash"
MARCADOR_PAGINA_INSUFICIENTE = "PAGINA_SEM_DETALHES"

PADRAO_URL = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
PADRAO_COMPARACAO = re.compile(
    r"\b(compar\w*|versus|vs\.?|diferença entre)\b",
    re.IGNORECASE,
)
PADRAO_VINHO = re.compile(
    r"\b(vinho|vinícola|produtor|uva|safra|rótulo|espumante|"
    r"malbec|merlot|cabernet|chardonnay|pinot|tannat|sauvignon)\w*\b",
    re.IGNORECASE,
)
PADRAO_DETALHES = re.compile(
    r"\b(uva\s*:?[ ]+\w+|safra\s*:?[ ]+(?:19|20)\d{2}|"
    r"preço\s*:?[ ]+(?:r\$[ ]*)?\d+|corpo\s*:?[ ]+\w+|"
    r"aroma\w*\s*:?[ ]+\w+|origem\s*:?[ ]+\w+|"
    r"harmoniza\w*\s*:?[ ]+\w+)",
    re.IGNORECASE,
)
PADRAO_SENSIVEL = re.compile(
    r"\b(pedido|cpf|rg|e-?mail|endereço|telefone|meu nome|me chamo)\b|"
    r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
PADRAO_SEM_ROTULO = re.compile(
    r"\b(qual|um|outro|esse|este|aquele)\s+(vinho|rótulo)\b",
    re.IGNORECASE,
)
PADRAO_PRODUTO = re.compile(r"\(ST-\d{3}\)")
PADRAO_CERTIFICACAO = re.compile(
    r"\b(vegan\w*|certifica\w*|selos?)\b",
    re.IGNORECASE,
)
PADRAO_CRITERIO_PRECO = re.compile(
    r"\b(preço|valor|custa\w*)\b|r\$",
    re.IGNORECASE,
)
PADRAO_CRITERIO_HARMONIZACAO = re.compile(
    r"\b(harmoniza\w*|combina\s+com|pratos?|carnes?|queijos?)\b",
    re.IGNORECASE,
)
PADRAO_CRITERIO_PERFIL = re.compile(
    r"\b(sabor|gosto|aroma\w*|leve|encorpado|frutado|seco|doce)\b",
    re.IGNORECASE,
)
PADRAO_DADO_PRECO = re.compile(
    r"r\$\s*\d+(?:[.,]\d{1,2})?|"
    r"\b(?:preço|valor|custa\w*)\s*(?:é|eh|:|de)?\s*"
    r"(?:r\$\s*)?\d+(?:[.,]\d{1,2})?",
    re.IGNORECASE,
)
PADRAO_DADO_HARMONIZACAO = re.compile(
    r"\b(carnes?|queijos?|massas?|peixes?|aves?|risotos?|"
    r"saladas?|frutos do mar|sobremesas?|chocolate|cogumelos?)\b|"
    r"\b(?:combina|harmoniza)\w*\s+com\s+[\wÀ-ÿ-]+",
    re.IGNORECASE,
)
PADRAO_DADO_PERFIL = re.compile(
    r"\b(leve|encorpado|frutado|seco|doce|ácido|macio|intenso|"
    r"suave|tânico|cítrico|floral)\b|"
    r"\b(?:sabor|gosto|aroma\w*)\s+(?:(?:é|eh|de)\s+)?"
    r"(?!do\b|da\b|e\b|ou\b)[\wÀ-ÿ-]+",
    re.IGNORECASE,
)
PADRAO_CONTINUACAO = re.compile(
    r"\b(ele|ela|compar\w*)\b|"
    r"\b(?:é|eh)\s+(?:malbec|merlot|cabernet|chardonnay|"
    r"pinot|tannat|sauvignon)\b",
    re.IGNORECASE,
)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize(
        "NFKD",
        texto,
    ).encode("ascii", "ignore").decode("ascii")

    return " ".join(texto.casefold().split())

def extrair_url(pergunta: str) -> str:
    resultado = PADRAO_URL.search(pergunta)

    if not resultado:
        return ""

    return resultado.group().rstrip(".,);]")

def identificar_produto_catalogo(
    pergunta: str,
    chunks: list[dict],
) -> str:
    pergunta_normalizada = normalizar(pergunta)

    for chunk in chunks:
        for linha in chunk["texto"].splitlines():
            if not PADRAO_PRODUTO.search(linha):
                continue

            nome = PADRAO_PRODUTO.sub("", linha).strip()
            nome = re.sub(r"\s+(?:19|20)\d{2}$", "", nome)

            if normalizar(nome) in pergunta_normalizada:
                return nome

    return ""

def extrair_nome_vinho_externo(
    pergunta: str,
    produto_sul_taca: str,
) -> str:
    separador = re.search(
        r"\s+(?:com|versus|vs\.?)\s+",
        pergunta,
        re.IGNORECASE,
    )

    if not separador:
        return ""

    nome = pergunta[separador.end():].strip(" .")
    nome = re.sub(r"^(?:o|a)\s+", "", nome, flags=re.IGNORECASE)
    nome = re.split(r"[.!?](?:\s|$)", nome, maxsplit=1)[0]

    if normalizar(nome) == normalizar(produto_sul_taca):
        return ""

    return nome

def reconhecer_criterios(texto: str) -> list[str]:
    criterios = []

    if PADRAO_CRITERIO_PRECO.search(texto):
        criterios.append("preço")

    if PADRAO_CRITERIO_HARMONIZACAO.search(texto):
        criterios.append("harmonização")

    if PADRAO_CRITERIO_PERFIL.search(texto):
        criterios.append("perfil")

    return criterios

def tem_dado_externo(texto: str, criterio: str) -> bool:
    padroes = {
        "preço": PADRAO_DADO_PRECO,
        "harmonização": PADRAO_DADO_HARMONIZACAO,
        "perfil": PADRAO_DADO_PERFIL,
    }

    return bool(padroes[criterio].search(texto))

def criar_comparacao_pendente(
    pergunta: str,
    chunks: list[dict],
) -> dict:
    produto = identificar_produto_catalogo(pergunta, chunks)

    return {
        "produto_sul_taca": produto,
        "vinho_externo": extrair_nome_vinho_externo(
            pergunta,
            produto,
        ),
        "criterios": [],
        "dados_externos": {},
        "texto_original": "",
    }

def eh_continuacao_comparacao(pergunta: str) -> bool:
    return bool(
        PADRAO_CONTINUACAO.search(pergunta)
        or reconhecer_criterios(pergunta)
    )

def atualizar_comparacao_pendente(
    comparacao: dict,
    texto: str,
) -> None:
    criterios = reconhecer_criterios(texto)

    for criterio in criterios:
        if criterio not in comparacao["criterios"]:
            comparacao["criterios"].append(criterio)

        if tem_dado_externo(texto, criterio):
            comparacao["dados_externos"][criterio] = texto

    textos = [comparacao["texto_original"], texto.strip()]
    comparacao["texto_original"] = "\n".join(
        item
        for item in textos
        if item
    )

def comparacao_tem_dados_suficientes(comparacao: dict) -> bool:
    return bool(
        comparacao["vinho_externo"]
        and comparacao["criterios"]
        and all(
            criterio in comparacao["dados_externos"]
            for criterio in comparacao["criterios"]
        )
    )

def decidir_rota(pergunta: str, chunks: list[dict]) -> str:
    url = extrair_url(pergunta)
    assunto_vinho = bool(PADRAO_VINHO.search(pergunta))
    comparacao = bool(PADRAO_COMPARACAO.search(pergunta))

    if url and assunto_vinho:
        if PADRAO_SENSIVEL.search(pergunta):
            return "bloquear_url"

        if identificar_produto_catalogo(pergunta, chunks):
            return "hibrida"

        return "url"

    if comparacao and assunto_vinho:
        produto = identificar_produto_catalogo(pergunta, chunks)

        if produto and extrair_nome_vinho_externo(
            pergunta,
            produto,
        ):
            return "pedir_detalhes"

        if PADRAO_DETALHES.search(pergunta):
            return "rag"

        if PADRAO_SEM_ROTULO.search(pergunta):
            return "pedir_vinho"

        return "pedir_detalhes"

    return "rag"

def extrair_resultado_url(response) -> tuple[str, str]:
    candidatos = response.candidates or []

    if not candidatos:
        return "", ""

    metadata = candidatos[0].url_context_metadata
    urls = metadata.url_metadata if metadata else []

    for item in urls or []:
        url = item.retrieved_url

        if (
            item.url_retrieval_status
            != types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_SUCCESS
            or not url
            or not url.startswith(("http://", "https://"))
        ):
            continue

        resposta = response.text or ""

        if MARCADOR_PAGINA_INSUFICIENTE in resposta:
            return "", ""

        fonte = f"**Fonte externa**\n\n- [{url}]({url})"
        return resposta, fonte

    return "", ""

def filtrar_contexto_interno(
    contexto: str,
    pergunta: str,
) -> str:
    if PADRAO_CERTIFICACAO.search(pergunta):
        return contexto

    linhas = []

    for linha in contexto.splitlines():
        partes = [
            parte
            for parte in linha.split(" | ")
            if not PADRAO_CERTIFICACAO.search(parte)
        ]

        if partes:
            linhas.append(" | ".join(partes))

    return "\n".join(linhas)

def filtrar_contexto_por_criterios(
    contexto: str,
    criterios: list[str],
) -> str:
    padroes = {
        "preço": re.compile(r"\bpreço\b", re.IGNORECASE),
        "harmonização": re.compile(
            r"\bharmoniza\w*\b",
            re.IGNORECASE,
        ),
        "perfil": re.compile(r"^Perfil:", re.IGNORECASE),
    }
    linhas = []

    for linha in contexto.splitlines():
        partes = linha.split(" | ")

        for parte in partes:
            if any(
                padroes[criterio].search(parte)
                for criterio in criterios
                if criterio in padroes
            ):
                linhas.append(parte.strip())

    return "\n".join(linhas)

def comparar_dados_fornecidos(
    comparacao: dict,
    contexto_interno: str,
    cliente,
) -> str:
    instrucoes_jessi = carregar_prompt_jessi()
    criterios = ", ".join(comparacao["criterios"])
    contexto_interno = filtrar_contexto_por_criterios(
        contexto_interno,
        comparacao["criterios"],
    )

    prompt = f"""
{instrucoes_jessi}

Compare os produtos somente pelos critérios solicitados.
Use do produto Sul Taça somente os campos presentes em DADOS
DO PRODUTO SUL TAÇA. Omita qualquer outro atributo.
Não atribua ao vinho externo nenhuma informação além do texto
fornecido pela pessoa. Trate esses dados como relato da pessoa,
não como fatos verificados ou como conteúdo de fonte externa.
Não complete lacunas com conhecimento próprio.
Não use qualificações como tradicional, excelente ou perfeito,
nem outras avaliações não sustentadas ou desnecessárias.

## DADOS DO PRODUTO SUL TAÇA

Produto: {comparacao["produto_sul_taca"]}

{contexto_interno}

## DADOS DO VINHO EXTERNO INFORMADOS PELA PESSOA

Produto: {comparacao["vinho_externo"]}
Critérios: {criterios}
Origem dos dados: Informado por você
Texto original: {comparacao["texto_original"]}

Comece com uma síntese curta orientada à escolha. Explique o que
as diferenças representam para a decisão, usando construções como
"se você prefere...", sem inventar preferências, atributos ou
superioridade. Depois apresente uma tabela Markdown compacta somente
quando houver diferenças relevantes. Identifique claramente os dados
externos como informados pela pessoa. Após a tabela, não repita os
mesmos dados. Termine com uma chamada curta, sem pressionar para
entrega, e não crie fontes externas.
"""

    response = cliente.models.generate_content(
        model=MODELO_CONSULTA_URL,
        contents=prompt,
    )

    return response.text

def consultar_pagina_vinho(
    pergunta: str,
    cliente,
    contexto_interno: str = "",
) -> tuple[str, str]:
    instrucoes_jessi = carregar_prompt_jessi()
    url = extrair_url(pergunta)
    contexto = ""

    if contexto_interno:
        contexto_interno = filtrar_contexto_interno(
            contexto_interno,
            pergunta,
        )
        contexto = f"""
## DADOS DO PRODUTO SUL TAÇA

Estes dados pertencem somente ao produto da Sul Taça:

{contexto_interno}
"""

    prompt = f"""
{instrucoes_jessi}

Consulte somente a URL fornecida e não siga links da página.
Não use conhecimento externo.

## REGRAS DA COMPARAÇÃO

- Trate DADOS DO PRODUTO SUL TAÇA e PÁGINA DO PRODUTO EXTERNO
  como fontes independentes.
- Nunca transfira atributos de um produto para o outro.
- Para cada dado do produto externo, use somente informação
  explícita na página consultada.
- Quando um campo não aparecer na página externa, escreva
  exatamente: Não informado na página consultada.
- Nunca deduza veganismo, preço, disponibilidade, origem,
  safra ou certificações.
- Não mencione veganismo, certificações ou selos, a menos que
  a pessoa tenha perguntado diretamente sobre isso. Nesse caso,
  só afirme esses dados do produto externo quando a página os
  declarar; caso contrário, use exatamente: Não informado na
  página consultada.
- Comece com uma síntese curta orientada à escolha, baseada somente
  nas diferenças sustentadas. Explique o que elas representam
  para a decisão com construções como "se você prefere...", sem
  inventar preferências, atributos ou superioridade.
- Depois apresente uma tabela Markdown compacta somente quando houver
  diferenças relevantes, com apenas os campos úteis para a decisão.
- Após a tabela, não repita os mesmos dados.
- Termine com uma chamada curta, sem pressionar para entrega.
- Ao mencionar preço, escreva Custa R$, nunca Custos de R$.
- Se a página não trouxer detalhes suficientes sobre um vinho,
  responda somente com {MARCADOR_PAGINA_INSUFICIENTE}.
{contexto}

## Mensagem do usuário

{pergunta}

## PÁGINA DO PRODUTO EXTERNO

{url}
"""

    response = cliente.models.generate_content(
        model=MODELO_CONSULTA_URL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"url_context": {}}],
        ),
    )

    return extrair_resultado_url(response)
