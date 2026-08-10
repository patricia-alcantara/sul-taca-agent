from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit


CAMINHO_BANCO = Path(__file__).parent / "data" / "qualidade.db"

TIPO_CATALOGO = "Catálogo e documentos"
TIPO_COMPARACAO = "Comparação externa"
TIPO_FLUXO_GUIADO = "Fluxo guiado"
TIPO_ORIENTACAO = "Orientação sem consulta"

CATEGORIAS_NAO_AVALIAVEIS = {
    "apresentacao",
    "maioridade",
    "identificacao_nome",
    "menu",
    "submenu",
    "navegacao",
    "erro_api",
    "bloqueio_seguranca",
}

PADRAO_EMAIL = re.compile(
    r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)
PADRAO_CPF = re.compile(
    r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"
)
PADRAO_TELEFONE = re.compile(
    r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?[\s.-]*)?"
    r"9?\d{4}[\s.-]?\d{4}(?!\d)"
)
PADRAO_NOME_DECLARADO = re.compile(
    r"\b(?:meu nome (?:é|e)|me chamo)\s+"
    r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]{0,60}",
    re.IGNORECASE,
)
PADRAO_URL = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
PADRAO_RECOMENDACAO = re.compile(
    r"\b(recomend\w*|indic\w*|suger\w*|qual vinho|"
    r"vinho para|acompanhar um prato|presentear|faixa de preço|"
    r"descobrir algo novo)\b",
    re.IGNORECASE,
)


def conectar(caminho_banco: Path | str = CAMINHO_BANCO) -> sqlite3.Connection:
    caminho = Path(caminho_banco)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    criar_tabela(conexao)
    return conexao


@contextmanager
def abrir_banco(caminho_banco: Path | str = CAMINHO_BANCO):
    conexao = conectar(caminho_banco)

    try:
        yield conexao
        conexao.commit()
    finally:
        conexao.close()


def criar_tabela(conexao: sqlite3.Connection) -> None:
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS avaliacoes (
            message_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            criada_em TEXT NOT NULL,
            rota_tecnica TEXT NOT NULL,
            tipo_atendimento TEXT NOT NULL,
            eh_recomendacao INTEGER NOT NULL DEFAULT 0
                CHECK (eh_recomendacao IN (0, 1)),
            eh_comparacao INTEGER NOT NULL DEFAULT 0
                CHECK (eh_comparacao IN (0, 1)),
            avaliacao INTEGER CHECK (avaliacao IN (0, 1)),
            pergunta TEXT,
            resposta TEXT
        )
        """
    )
    conexao.commit()


def resposta_eh_avaliavel(categoria: str) -> bool:
    return categoria not in CATEGORIAS_NAO_AVALIAVEIS


def eh_pergunta_de_recomendacao(pergunta: str) -> bool:
    return bool(PADRAO_RECOMENDACAO.search(pergunta))


def registrar_resposta_elegivel(
    message_id: str,
    session_id: str,
    rota_tecnica: str,
    tipo_atendimento: str,
    eh_recomendacao: bool = False,
    eh_comparacao: bool = False,
    caminho_banco: Path | str = CAMINHO_BANCO,
    criada_em: str | None = None,
) -> bool:
    instante = criada_em or datetime.now(timezone.utc).isoformat()

    with abrir_banco(caminho_banco) as conexao:
        cursor = conexao.execute(
            """
            INSERT OR IGNORE INTO avaliacoes (
                message_id,
                session_id,
                criada_em,
                rota_tecnica,
                tipo_atendimento,
                eh_recomendacao,
                eh_comparacao
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                instante,
                rota_tecnica,
                tipo_atendimento,
                int(eh_recomendacao),
                int(eh_comparacao),
            ),
        )

    return cursor.rowcount == 1


def _remover_parametros_url(resultado: re.Match) -> str:
    url = resultado.group()
    pontuacao = ""

    while url and url[-1] in ".,);]":
        pontuacao = url[-1] + pontuacao
        url = url[:-1]

    partes = urlsplit(url)
    url_sem_parametros = urlunsplit(
        (partes.scheme, partes.netloc, partes.path, "", "")
    )
    return f"{url_sem_parametros}{pontuacao}"


def sanitizar_texto(
    texto: str,
    termos_sensiveis: Iterable[str] = (),
) -> str:
    resultado = PADRAO_EMAIL.sub("[E-MAIL REDIGIDO]", texto)
    resultado = PADRAO_CPF.sub("[CPF REDIGIDO]", resultado)
    resultado = PADRAO_TELEFONE.sub("[TELEFONE REDIGIDO]", resultado)
    resultado = PADRAO_NOME_DECLARADO.sub(
        "[NOME REDIGIDO]",
        resultado,
    )
    resultado = PADRAO_URL.sub(_remover_parametros_url, resultado)

    for termo in termos_sensiveis:
        termo = termo.strip()

        if termo:
            resultado = re.sub(
                re.escape(termo),
                "[NOME REDIGIDO]",
                resultado,
                flags=re.IGNORECASE,
            )

    return resultado


def avaliar_resposta(
    message_id: str,
    avaliacao: bool,
    pergunta: str,
    resposta: str,
    termos_sensiveis: Iterable[str] = (),
    caminho_banco: Path | str = CAMINHO_BANCO,
) -> bool:
    pergunta_segura = sanitizar_texto(pergunta, termos_sensiveis)
    resposta_segura = sanitizar_texto(resposta, termos_sensiveis)

    with abrir_banco(caminho_banco) as conexao:
        cursor = conexao.execute(
            """
            UPDATE avaliacoes
            SET avaliacao = ?, pergunta = ?, resposta = ?
            WHERE message_id = ? AND avaliacao IS NULL
            """,
            (
                int(avaliacao),
                pergunta_segura,
                resposta_segura,
                message_id,
            ),
        )

    return cursor.rowcount == 1


def obter_avaliacao(
    message_id: str,
    caminho_banco: Path | str = CAMINHO_BANCO,
) -> int | None:
    with abrir_banco(caminho_banco) as conexao:
        linha = conexao.execute(
            "SELECT avaliacao FROM avaliacoes WHERE message_id = ?",
            (message_id,),
        ).fetchone()

    return None if linha is None else linha["avaliacao"]


def obter_metricas(
    caminho_banco: Path | str = CAMINHO_BANCO,
) -> dict:
    with abrir_banco(caminho_banco) as conexao:
        linha = conexao.execute(
            """
            SELECT
                COUNT(*) AS elegiveis,
                COUNT(avaliacao) AS avaliadas,
                COALESCE(SUM(avaliacao = 1), 0) AS positivas,
                COALESCE(SUM(avaliacao = 0), 0) AS negativas,
                COALESCE(SUM(eh_recomendacao), 0) AS recomendacoes,
                COALESCE(SUM(eh_comparacao), 0) AS comparacoes
            FROM avaliacoes
            """
        ).fetchone()

    avaliadas = linha["avaliadas"]
    elegiveis = linha["elegiveis"]
    positivas = linha["positivas"]

    return {
        "respostas_elegiveis": elegiveis,
        "respostas_avaliadas": avaliadas,
        "positivas": positivas,
        "negativas": linha["negativas"],
        "percentual_positivo": (
            100 * positivas / avaliadas if avaliadas else 0.0
        ),
        "taxa_participacao": (
            100 * avaliadas / elegiveis if elegiveis else 0.0
        ),
        "recomendacoes": linha["recomendacoes"],
        "comparacoes": linha["comparacoes"],
    }


def obter_contexto(
    caminho_banco: Path | str = CAMINHO_BANCO,
) -> list[dict]:
    with abrir_banco(caminho_banco) as conexao:
        linhas = conexao.execute(
            """
            SELECT
                tipo_atendimento,
                COUNT(avaliacao) AS respostas_avaliadas,
                COALESCE(SUM(avaliacao = 1), 0) AS positivas,
                COALESCE(SUM(avaliacao = 0), 0) AS negativas
            FROM avaliacoes
            GROUP BY tipo_atendimento
            ORDER BY tipo_atendimento
            """
        ).fetchall()

    contexto = []

    for linha in linhas:
        avaliadas = linha["respostas_avaliadas"]
        positivas = linha["positivas"]
        contexto.append(
            {
                "Tipo de atendimento": linha["tipo_atendimento"],
                "Respostas avaliadas": avaliadas,
                "Positivas": positivas,
                "Negativas": linha["negativas"],
                "Percentual positivo": (
                    100 * positivas / avaliadas if avaliadas else 0.0
                ),
            }
        )

    return contexto


def obter_avaliacoes_detalhadas(
    caminho_banco: Path | str = CAMINHO_BANCO,
) -> list[dict]:
    with abrir_banco(caminho_banco) as conexao:
        linhas = conexao.execute(
            """
            SELECT
                criada_em,
                pergunta,
                resposta,
                avaliacao,
                tipo_atendimento,
                rota_tecnica
            FROM avaliacoes
            WHERE avaliacao IS NOT NULL
            ORDER BY criada_em DESC
            """
        ).fetchall()

    return [
        {
            "Data": datetime.fromisoformat(linha["criada_em"]),
            "Pergunta": linha["pergunta"],
            "Resposta": linha["resposta"],
            "Avaliação": (
                "Positivo" if linha["avaliacao"] else "Negativo"
            ),
            "Tipo de atendimento": linha["tipo_atendimento"],
            "Rota técnica": linha["rota_tecnica"],
        }
        for linha in linhas
    ]
