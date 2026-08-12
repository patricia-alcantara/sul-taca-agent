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

TIPOS_ATENDIMENTO_V1 = {
    "catalogo_documentos": TIPO_CATALOGO,
    "comparacao_externa": TIPO_COMPARACAO,
    "fluxo_guiado": TIPO_FLUXO_GUIADO,
    "orientacao_sem_consulta": TIPO_ORIENTACAO,
}

def _tipo_v2(tipo_atendimento: str) -> str:
    for valor_v2, rotulo_v1 in TIPOS_ATENDIMENTO_V1.items():
        if tipo_atendimento in (valor_v2, rotulo_v1):
            return valor_v2
    return "catalogo_documentos"


MECANISMOS_PAINEL = {
    "rag_interno": (
        "Base interna Sul Taça",
        "Consulta ao catálogo e aos documentos internos.",
    ),
    "url_context": (
        "Página externa",
        "Consulta delimitada à página enviada pela pessoa.",
    ),
    "hibrido": (
        "Base interna + página externa",
        "Combina dados Sul Taça com uma página externa.",
    ),
    "regra_local": (
        "Regra ou fluxo local",
        "Resposta definida pelo fluxo, sem consulta ao modelo.",
    ),
    "nenhum": (
        "Sem consulta técnica",
        "Navegação ou operação que não exigiu uma consulta.",
    ),
}


def conectar(caminho_banco: Path | str = CAMINHO_BANCO) -> sqlite3.Connection:
    caminho = Path(caminho_banco)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    migrar_schema(conexao)
    return conexao


@contextmanager
def abrir_banco(caminho_banco: Path | str = CAMINHO_BANCO):
    conexao = conectar(caminho_banco)

    try:
        yield conexao
        conexao.commit()
    finally:
        conexao.close()


def _criar_schema_v2(conexao: sqlite3.Connection) -> None:
    conexao.executescript(
        """
        CREATE TABLE IF NOT EXISTS interacoes (
            message_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            task_id TEXT,
            criada_em TEXT NOT NULL,
            elegivel INTEGER NOT NULL CHECK (elegivel IN (0, 1)),
            natureza_resposta TEXT NOT NULL CHECK (natureza_resposta IN (
                'resposta_substantiva', 'pedido_esclarecimento', 'navegacao',
                'mensagem_operacional', 'orientacao_recuperacao'
            )),
            tipo_atendimento TEXT NOT NULL CHECK (tipo_atendimento IN (
                'catalogo_documentos', 'comparacao_externa', 'fluxo_guiado',
                'orientacao_sem_consulta'
            )),
            rota_tecnica TEXT NOT NULL,
            mecanismo TEXT NOT NULL CHECK (mecanismo IN (
                'rag_interno', 'url_context', 'hibrido', 'regra_local',
                'nenhum'
            )),
            status TEXT NOT NULL CHECK (status IN (
                'sucesso', 'insuficiente', 'falha_tecnica',
                'bloqueio_seguranca'
            )),
            etapa_falha TEXT CHECK (etapa_falha IS NULL OR etapa_falha IN (
                'inicializacao', 'roteamento', 'recuperacao_interna',
                'recuperacao_externa', 'geracao', 'persistencia',
                'renderizacao'
            )),
            latencia_ms INTEGER CHECK (latencia_ms IS NULL OR latencia_ms >= 0)
        );

        CREATE TABLE IF NOT EXISTS classificacoes_interacao (
            message_id TEXT NOT NULL REFERENCES interacoes(message_id)
                ON DELETE CASCADE,
            dimensao TEXT NOT NULL CHECK (dimensao IN ('intencao', 'resultado')),
            classificacao TEXT NOT NULL CHECK (classificacao IN (
                'recomendacao', 'comparacao', 'consulta_catalogo_politica',
                'orientacao_operacional', 'resposta_catalogo_politica'
            )),
            PRIMARY KEY (message_id, dimensao, classificacao)
        );

        CREATE TABLE IF NOT EXISTS avaliacoes (
            message_id TEXT PRIMARY KEY REFERENCES interacoes(message_id)
                ON DELETE CASCADE,
            avaliacao INTEGER NOT NULL CHECK (avaliacao IN (0, 1)),
            criada_em TEXT NOT NULL,
            pergunta_sanitizada TEXT NOT NULL,
            resposta_sanitizada TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_interacoes_criada_em
            ON interacoes(criada_em);
        CREATE INDEX IF NOT EXISTS idx_interacoes_tipo
            ON interacoes(tipo_atendimento);
        CREATE INDEX IF NOT EXISTS idx_classificacoes_resultado
            ON classificacoes_interacao(dimensao, classificacao);
        """
    )


def _tabela_legada_avaliacoes(conexao: sqlite3.Connection) -> bool:
    colunas = {
        linha["name"]
        for linha in conexao.execute("PRAGMA table_info(avaliacoes)")
    }
    return "session_id" in colunas and "eh_recomendacao" in colunas


def migrar_schema(conexao: sqlite3.Connection) -> None:
    conexao.execute("BEGIN")

    try:
        if _tabela_legada_avaliacoes(conexao):
            conexao.execute(
                "ALTER TABLE avaliacoes RENAME TO avaliacoes_v1_migracao"
            )
            _criar_schema_v2(conexao)
            conexao.execute(
                """
                INSERT INTO interacoes (
                    message_id, session_id, task_id, criada_em, elegivel,
                    natureza_resposta, tipo_atendimento, rota_tecnica,
                    mecanismo, status, etapa_falha, latencia_ms
                )
                SELECT
                    message_id, session_id, NULL, criada_em, 1,
                    'resposta_substantiva',
                    CASE tipo_atendimento
                        WHEN 'Catálogo e documentos' THEN 'catalogo_documentos'
                        WHEN 'Comparação externa' THEN 'comparacao_externa'
                        WHEN 'Fluxo guiado' THEN 'fluxo_guiado'
                        WHEN 'Orientação sem consulta' THEN 'orientacao_sem_consulta'
                        ELSE 'catalogo_documentos'
                    END,
                    rota_tecnica,
                    CASE rota_tecnica
                        WHEN 'url' THEN 'url_context'
                        WHEN 'hibrida' THEN 'hibrido'
                        WHEN 'fluxo_guiado' THEN 'regra_local'
                        ELSE 'rag_interno'
                    END,
                    'sucesso', NULL, NULL
                FROM avaliacoes_v1_migracao
                """
            )
            conexao.execute(
                """
                INSERT INTO classificacoes_interacao
                    (message_id, dimensao, classificacao)
                SELECT message_id, 'resultado', 'recomendacao'
                FROM avaliacoes_v1_migracao
                WHERE eh_recomendacao = 1
                """
            )
            conexao.execute(
                """
                INSERT INTO classificacoes_interacao
                    (message_id, dimensao, classificacao)
                SELECT message_id, 'resultado', 'comparacao'
                FROM avaliacoes_v1_migracao
                WHERE eh_comparacao = 1
                """
            )
            conexao.execute(
                """
                INSERT INTO avaliacoes (
                    message_id, avaliacao, criada_em,
                    pergunta_sanitizada, resposta_sanitizada
                )
                SELECT message_id, avaliacao, criada_em,
                    COALESCE(pergunta, ''), COALESCE(resposta, '')
                FROM avaliacoes_v1_migracao
                WHERE avaliacao IS NOT NULL
                """
            )
            conexao.execute("DROP TABLE avaliacoes_v1_migracao")
        else:
            _criar_schema_v2(conexao)

        conexao.commit()
    except Exception:
        conexao.rollback()
        raise


def criar_tabela(conexao: sqlite3.Connection) -> None:
    migrar_schema(conexao)


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
            INSERT OR IGNORE INTO interacoes (
                message_id, session_id, task_id, criada_em, elegivel,
                natureza_resposta, tipo_atendimento, rota_tecnica,
                mecanismo, status, etapa_falha, latencia_ms
            ) VALUES (?, ?, NULL, ?, 1, 'resposta_substantiva', ?, ?,
                'rag_interno', 'sucesso', NULL, NULL)
            """,
            (
                message_id,
                session_id,
                instante,
                _tipo_v2(tipo_atendimento),
                rota_tecnica,
            ),
        )
        classificacoes = []
        if eh_recomendacao:
            classificacoes.append("recomendacao")
        if eh_comparacao:
            classificacoes.append("comparacao")
        conexao.executemany(
            """
            INSERT OR IGNORE INTO classificacoes_interacao
                (message_id, dimensao, classificacao)
            VALUES (?, 'resultado', ?)
            """,
            ((message_id, item) for item in classificacoes),
        )

    return cursor.rowcount == 1


def registrar_interacao(
    message_id: str,
    session_id: str,
    envelope,
    task_id: str | None = None,
    caminho_banco: Path | str = CAMINHO_BANCO,
    criada_em: str | None = None,
    latencia_ms: int | None = None,
) -> bool:
    instante = criada_em or datetime.now(timezone.utc).isoformat()

    with abrir_banco(caminho_banco) as conexao:
        cursor = conexao.execute(
            """
            INSERT OR IGNORE INTO interacoes (
                message_id, session_id, task_id, criada_em, elegivel,
                natureza_resposta, tipo_atendimento, rota_tecnica,
                mecanismo, status, etapa_falha, latencia_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                task_id,
                instante,
                int(envelope.elegivel),
                envelope.natureza.value,
                envelope.tipo_atendimento.value,
                envelope.rota_tecnica,
                envelope.mecanismo.value,
                envelope.status.value,
                (
                    envelope.etapa_falha.value
                    if envelope.etapa_falha
                    else None
                ),
                latencia_ms,
            ),
        )
        classificacoes = [
            (message_id, "intencao", item.value)
            for item in envelope.intencoes
        ] + [
            (message_id, "resultado", item.value)
            for item in envelope.resultados
        ]
        conexao.executemany(
            """
            INSERT OR IGNORE INTO classificacoes_interacao
                (message_id, dimensao, classificacao)
            VALUES (?, ?, ?)
            """,
            classificacoes,
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
    instante = datetime.now(timezone.utc).isoformat()

    with abrir_banco(caminho_banco) as conexao:
        cursor = conexao.execute(
            """
            INSERT OR IGNORE INTO avaliacoes (
                message_id, avaliacao, criada_em,
                pergunta_sanitizada, resposta_sanitizada
            )
            SELECT message_id, ?, ?, ?, ?
            FROM interacoes
            WHERE message_id = ? AND elegivel = 1
            """,
            (
                int(avaliacao),
                instante,
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
                COUNT(a.avaliacao) AS avaliadas,
                COALESCE(SUM(a.avaliacao = 1), 0) AS positivas,
                COALESCE(SUM(a.avaliacao = 0), 0) AS negativas,
                COALESCE(SUM(EXISTS (
                    SELECT 1 FROM classificacoes_interacao c
                    WHERE c.message_id = i.message_id
                      AND c.dimensao = 'resultado'
                      AND c.classificacao = 'recomendacao'
                )), 0) AS recomendacoes,
                COALESCE(SUM(EXISTS (
                    SELECT 1 FROM classificacoes_interacao c
                    WHERE c.message_id = i.message_id
                      AND c.dimensao = 'resultado'
                      AND c.classificacao = 'comparacao'
                )), 0) AS comparacoes,
                COALESCE(SUM(
                    EXISTS (
                        SELECT 1 FROM classificacoes_interacao c
                        WHERE c.message_id = i.message_id
                          AND c.dimensao = 'resultado'
                          AND c.classificacao = 'recomendacao'
                    )
                    AND EXISTS (
                        SELECT 1 FROM classificacoes_interacao c
                        WHERE c.message_id = i.message_id
                          AND c.dimensao = 'resultado'
                          AND c.classificacao = 'comparacao'
                    )
                ), 0) AS recomendacoes_e_comparacoes
            FROM interacoes i
            LEFT JOIN avaliacoes a USING (message_id)
            WHERE i.elegivel = 1
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
        "recomendacoes_e_comparacoes": linha[
            "recomendacoes_e_comparacoes"
        ],
    }


def obter_contexto(
    caminho_banco: Path | str = CAMINHO_BANCO,
) -> list[dict]:
    with abrir_banco(caminho_banco) as conexao:
        linhas = conexao.execute(
            """
            SELECT
                i.tipo_atendimento,
                COUNT(*) AS respostas_elegiveis,
                COUNT(a.avaliacao) AS respostas_avaliadas,
                COALESCE(SUM(a.avaliacao = 1), 0) AS positivas,
                COALESCE(SUM(a.avaliacao = 0), 0) AS negativas
            FROM interacoes i
            LEFT JOIN avaliacoes a USING (message_id)
            WHERE i.elegivel = 1
            GROUP BY i.tipo_atendimento
            ORDER BY i.tipo_atendimento
            """
        ).fetchall()

    contexto = []

    for linha in linhas:
        avaliadas = linha["respostas_avaliadas"]
        elegiveis = linha["respostas_elegiveis"]
        positivas = linha["positivas"]
        contexto.append(
            {
                "Forma de atendimento": TIPOS_ATENDIMENTO_V1.get(
                    linha["tipo_atendimento"],
                    linha["tipo_atendimento"],
                ),
                "Disponíveis para avaliação": elegiveis,
                "Respostas avaliadas": avaliadas,
                "Positivas": positivas,
                "Negativas": linha["negativas"],
                "Percentual positivo": (
                    100 * positivas / avaliadas if avaliadas else 0.0
                ),
                "Taxa de participação": (
                    100 * avaliadas / elegiveis if elegiveis else 0.0
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
                a.criada_em,
                a.pergunta_sanitizada,
                a.resposta_sanitizada,
                a.avaliacao,
                i.tipo_atendimento,
                i.rota_tecnica,
                i.mecanismo,
                EXISTS (
                    SELECT 1 FROM classificacoes_interacao c
                    WHERE c.message_id = i.message_id
                      AND c.dimensao = 'resultado'
                      AND c.classificacao = 'recomendacao'
                ) AS eh_recomendacao,
                EXISTS (
                    SELECT 1 FROM classificacoes_interacao c
                    WHERE c.message_id = i.message_id
                      AND c.dimensao = 'resultado'
                      AND c.classificacao = 'comparacao'
                ) AS eh_comparacao
            FROM avaliacoes a
            JOIN interacoes i USING (message_id)
            ORDER BY a.criada_em DESC
            """
        ).fetchall()

    return [
        {
            "Data": datetime.fromisoformat(linha["criada_em"]),
            "Pergunta": linha["pergunta_sanitizada"],
            "Resposta": linha["resposta_sanitizada"],
            "Avaliação": (
                "Positivo" if linha["avaliacao"] else "Negativo"
            ),
            "Forma de atendimento": TIPOS_ATENDIMENTO_V1.get(
                linha["tipo_atendimento"],
                linha["tipo_atendimento"],
            ),
            "Resultado": _rotulo_resultado(
                linha["eh_recomendacao"],
                linha["eh_comparacao"],
            ),
            "Como a Jessi respondeu": MECANISMOS_PAINEL.get(
                linha["mecanismo"],
                (linha["mecanismo"], ""),
            )[0],
            "Rota técnica": linha["rota_tecnica"],
        }
        for linha in linhas
    ]


def obter_funcionamento(
    caminho_banco: Path | str = CAMINHO_BANCO,
) -> dict:
    with abrir_banco(caminho_banco) as conexao:
        linha = conexao.execute(
            """
            SELECT
                COUNT(*) AS interacoes,
                COALESCE(SUM(status = 'sucesso'), 0) AS sucessos,
                COALESCE(SUM(status = 'insuficiente'), 0) AS insuficiencias,
                COALESCE(SUM(status = 'falha_tecnica'), 0) AS falhas,
                COALESCE(SUM(status = 'bloqueio_seguranca'), 0) AS bloqueios
            FROM interacoes
            """
        ).fetchone()

    return {
        "interacoes": linha["interacoes"],
        "sucessos": linha["sucessos"],
        "insuficiencias": linha["insuficiencias"],
        "falhas": linha["falhas"],
        "bloqueios": linha["bloqueios"],
    }


def obter_mecanismos(
    caminho_banco: Path | str = CAMINHO_BANCO,
) -> list[dict]:
    with abrir_banco(caminho_banco) as conexao:
        linhas = conexao.execute(
            """
            SELECT mecanismo, COUNT(*) AS interacoes
            FROM interacoes
            GROUP BY mecanismo
            ORDER BY interacoes DESC, mecanismo
            """
        ).fetchall()

    return [
        {
            "Como a Jessi respondeu": MECANISMOS_PAINEL.get(
                linha["mecanismo"],
                (linha["mecanismo"], ""),
            )[0],
            "O que significa": MECANISMOS_PAINEL.get(
                linha["mecanismo"],
                (linha["mecanismo"], ""),
            )[1],
            "Interações": linha["interacoes"],
        }
        for linha in linhas
    ]


def _rotulo_resultado(
    eh_recomendacao: bool,
    eh_comparacao: bool,
) -> str:
    if eh_recomendacao and eh_comparacao:
        return "Recomendação e comparação"
    if eh_recomendacao:
        return "Recomendação"
    if eh_comparacao:
        return "Comparação"
    return "Nenhuma"
