from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import re
import unicodedata
from uuid import uuid4


class NaturezaResposta(StrEnum):
    SUBSTANTIVA = "resposta_substantiva"
    ESCLARECIMENTO = "pedido_esclarecimento"
    NAVEGACAO = "navegacao"
    OPERACIONAL = "mensagem_operacional"
    ORIENTACAO_RECUPERACAO = "orientacao_recuperacao"


class TipoAtendimento(StrEnum):
    CATALOGO_DOCUMENTOS = "catalogo_documentos"
    COMPARACAO_EXTERNA = "comparacao_externa"
    FLUXO_GUIADO = "fluxo_guiado"
    ORIENTACAO_SEM_CONSULTA = "orientacao_sem_consulta"


class Mecanismo(StrEnum):
    RAG_INTERNO = "rag_interno"
    URL_CONTEXT = "url_context"
    HIBRIDO = "hibrido"
    REGRA_LOCAL = "regra_local"
    NENHUM = "nenhum"


class StatusResultado(StrEnum):
    SUCESSO = "sucesso"
    INSUFICIENTE = "insuficiente"
    FALHA_TECNICA = "falha_tecnica"
    BLOQUEIO_SEGURANCA = "bloqueio_seguranca"


class Intencao(StrEnum):
    RECOMENDACAO = "recomendacao"
    COMPARACAO = "comparacao"
    CONSULTA_CATALOGO_POLITICA = "consulta_catalogo_politica"
    ORIENTACAO_OPERACIONAL = "orientacao_operacional"


class Resultado(StrEnum):
    RECOMENDACAO = "recomendacao"
    COMPARACAO = "comparacao"
    RESPOSTA_CATALOGO_POLITICA = "resposta_catalogo_politica"
    ORIENTACAO_OPERACIONAL = "orientacao_operacional"


class EtapaFalha(StrEnum):
    INICIALIZACAO = "inicializacao"
    ROTEAMENTO = "roteamento"
    RECUPERACAO_INTERNA = "recuperacao_interna"
    RECUPERACAO_EXTERNA = "recuperacao_externa"
    GERACAO = "geracao"
    PERSISTENCIA = "persistencia"
    RENDERIZACAO = "renderizacao"


class EtapaTarefa(StrEnum):
    AGUARDANDO_NECESSIDADE = "aguardando_necessidade"
    AGUARDANDO_PRODUTO = "aguardando_produto"
    AGUARDANDO_CRITERIOS = "aguardando_criterios"
    AGUARDANDO_DADOS_EXTERNOS = "aguardando_dados_externos"
    PRONTA = "pronta"
    EM_EXECUCAO = "em_execucao"


class OrigemTarefa(StrEnum):
    DIRETA = "direta"
    MENU_GUIADO = "menu_guiado"


class EstadoTarefa(StrEnum):
    ATIVA = "ativa"
    CONCLUIDA = "concluida"
    SUBSTITUIDA = "substituida"
    LIMPA = "limpa"


PADRAO_INTENCAO_RECOMENDACAO = re.compile(
    r"\b(recomend\w*|indic\w*|suger\w*|qual vinho|vinho para|"
    r"(?:quero|procuro|preciso de)\s+(?:um\s+|uma\s+)?"
    r"(?:vinho|espumante)|"
    r"acompanhar um prato|presentear|faixa de pre[cç]o|"
    r"descobrir algo novo)\b",
    re.IGNORECASE,
)
PADRAO_INTENCAO_COMPARACAO = re.compile(
    r"\b(compar\w*|versus|vs\.?|diferen[cç]a entre)\b",
    re.IGNORECASE,
)
PADRAO_INTENCAO_POLITICA = re.compile(
    r"\b(privacidade|pol[ií]tica de privacidade|uso de dados|"
    r"dados pessoais|lgpd)\b",
    re.IGNORECASE,
)
PADRAO_INTENCAO_OPERACIONAL = re.compile(
    r"\b(?:acompanhar|rastrear|cancelar) (?:meu )?pedido\b|"
    r"\bstatus do (?:meu )?pedido\b|"
    r"\b(?:prazo|forma) de (?:entrega|pagamento)\b|"
    r"\bcomo (?:fa[cç]o para )?comprar\b",
    re.IGNORECASE,
)
PADRAO_ADEQUACAO = re.compile(
    r"\b(recomend\w*|indic\w*|adequad[oa]s?|boa escolha|"
    r"[oó]tima escolha|ideal|combina bem|vai bem)\b",
    re.IGNORECASE,
)
PADRAO_PRODUTO_CATALOGO = re.compile(
    r"^(?P<nome>.+?)\s+\((?P<codigo>ST-\d{3})\)\s*$"
)


@dataclass(frozen=True)
class TarefaConversacional:
    task_id: str
    intencoes: frozenset[Intencao]
    origem: OrigemTarefa
    etapa: EtapaTarefa
    estado: EstadoTarefa = EstadoTarefa.ATIVA
    continuacoes: int = 0

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("task_id é obrigatório")
        if not self.intencoes:
            raise ValueError("a tarefa precisa de ao menos uma intenção")


@dataclass(frozen=True)
class ProdutoSulTaca:
    codigo: str
    nome: str
    adequacao_declarada: bool = False


@dataclass(frozen=True)
class EvidenciasExecucao:
    produtos_sul_taca: tuple[ProdutoSulTaca, ...] = ()
    participantes_comparacao: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnvelopeResultado:
    texto_exibicao: str
    natureza: NaturezaResposta
    elegivel: bool
    tipo_atendimento: TipoAtendimento
    rota_tecnica: str
    mecanismo: Mecanismo
    status: StatusResultado
    intencoes: frozenset[Intencao] = frozenset()
    resultados: frozenset[Resultado] = frozenset()
    produtos_sul_taca: tuple[ProdutoSulTaca, ...] = ()
    etapa_falha: EtapaFalha | None = None

    def __post_init__(self) -> None:
        if Resultado.RECOMENDACAO in self.resultados and not any(
            produto.adequacao_declarada
            for produto in self.produtos_sul_taca
        ):
            raise ValueError(
                "recomendação exige produto Sul Taça com adequação declarada"
            )

        if self.status in {
            StatusResultado.FALHA_TECNICA,
            StatusResultado.BLOQUEIO_SEGURANCA,
        }:
            if self.elegivel or self.resultados:
                raise ValueError(
                    "falha e bloqueio não podem ser avaliáveis ou comerciais"
                )

        if (
            self.status == StatusResultado.FALHA_TECNICA
            and self.etapa_falha is None
        ):
            raise ValueError("falha técnica exige etapa controlada")

        if self.status == StatusResultado.INSUFICIENTE:
            if not self.elegivel or self.resultados:
                raise ValueError(
                    "insuficiência deve ser elegível e sem resultado comercial"
                )

    @property
    def permite_persistir_textos(self) -> bool:
        return self.elegivel and self.status not in {
            StatusResultado.FALHA_TECNICA,
            StatusResultado.BLOQUEIO_SEGURANCA,
        }


def inferir_intencoes(texto: str) -> frozenset[Intencao]:
    intencoes = set()

    if PADRAO_INTENCAO_RECOMENDACAO.search(texto):
        intencoes.add(Intencao.RECOMENDACAO)
    if PADRAO_INTENCAO_COMPARACAO.search(texto):
        intencoes.add(Intencao.COMPARACAO)
    if PADRAO_INTENCAO_POLITICA.search(texto):
        intencoes.add(Intencao.CONSULTA_CATALOGO_POLITICA)
    if PADRAO_INTENCAO_OPERACIONAL.search(texto):
        intencoes.add(Intencao.ORIENTACAO_OPERACIONAL)

    return frozenset(intencoes)


def iniciar_tarefa(
    intencoes: frozenset[Intencao] | set[Intencao],
    origem: OrigemTarefa,
    etapa: EtapaTarefa,
    task_id: str | None = None,
) -> TarefaConversacional:
    return TarefaConversacional(
        task_id=task_id or str(uuid4()),
        intencoes=frozenset(intencoes),
        origem=origem,
        etapa=etapa,
    )


def registrar_continuacao(
    tarefa: TarefaConversacional,
    etapa: EtapaTarefa | None = None,
) -> TarefaConversacional:
    _exigir_tarefa_ativa(tarefa)
    return replace(
        tarefa,
        etapa=etapa or tarefa.etapa,
        continuacoes=tarefa.continuacoes + 1,
    )


def concluir_tarefa(
    tarefa: TarefaConversacional,
) -> TarefaConversacional:
    _exigir_tarefa_ativa(tarefa)
    return replace(tarefa, estado=EstadoTarefa.CONCLUIDA)


def substituir_tarefa(
    tarefa: TarefaConversacional,
    intencoes: frozenset[Intencao] | set[Intencao],
    origem: OrigemTarefa,
    etapa: EtapaTarefa,
    task_id: str | None = None,
) -> tuple[TarefaConversacional, TarefaConversacional]:
    _exigir_tarefa_ativa(tarefa)
    substituida = replace(tarefa, estado=EstadoTarefa.SUBSTITUIDA)
    nova = iniciar_tarefa(intencoes, origem, etapa, task_id)
    return substituida, nova


def limpar_tarefa(
    tarefa: TarefaConversacional,
) -> TarefaConversacional:
    _exigir_tarefa_ativa(tarefa)
    return replace(tarefa, estado=EstadoTarefa.LIMPA)


def atualizar_tarefa_por_mensagem(
    tarefa: TarefaConversacional | None,
    texto: str,
    task_id: str | None = None,
) -> TarefaConversacional | None:
    detectadas = inferir_intencoes(texto)

    if tarefa is None:
        if not detectadas:
            return None
        return iniciar_tarefa(
            detectadas,
            OrigemTarefa.DIRETA,
            EtapaTarefa.EM_EXECUCAO,
            task_id,
        )

    _exigir_tarefa_ativa(tarefa)

    if detectadas and not detectadas.issubset(tarefa.intencoes):
        _, nova = substituir_tarefa(
            tarefa,
            detectadas,
            OrigemTarefa.DIRETA,
            EtapaTarefa.EM_EXECUCAO,
            task_id,
        )
        return nova

    return registrar_continuacao(tarefa, EtapaTarefa.EM_EXECUCAO)


def extrair_catalogo(
    chunks: list[dict],
) -> tuple[ProdutoSulTaca, ...]:
    produtos = {}

    for chunk in chunks:
        for linha in chunk["texto"].splitlines():
            resultado = PADRAO_PRODUTO_CATALOGO.match(linha.strip())
            if resultado:
                codigo = resultado.group("codigo")
                produtos[codigo] = ProdutoSulTaca(
                    codigo=codigo,
                    nome=resultado.group("nome").strip(),
                )

    return tuple(produtos[codigo] for codigo in sorted(produtos))


def identificar_produtos_execucao(
    texto: str,
    chunks: list[dict],
) -> tuple[ProdutoSulTaca, ...]:
    texto_sem_fontes = texto.rsplit("\n---\n", 1)[0]
    catalogo = extrair_catalogo(chunks)
    segmentos = [
        segmento.strip()
        for segmento in re.split(r"(?<=[.!?])\s+|\n+", texto_sem_fontes)
        if segmento.strip()
    ]
    identificados = []

    for produto in catalogo:
        aliases = _aliases_unicos(produto, catalogo)
        segmentos_produto = [
            segmento
            for segmento in segmentos
            if (
                any(
                    alias in _normalizar(segmento)
                    for alias in aliases
                )
                or produto.codigo.casefold() in segmento.casefold()
            )
        ]

        if not segmentos_produto:
            continue

        adequacao = any(
            PADRAO_ADEQUACAO.search(segmento)
            for segmento in segmentos_produto
        )
        identificados.append(
            replace(produto, adequacao_declarada=adequacao)
        )

    if (
        identificados
        and not any(
            produto.adequacao_declarada
            for produto in identificados
        )
        and PADRAO_ADEQUACAO.search(texto_sem_fontes)
    ):
        identificados = [
            replace(produto, adequacao_declarada=True)
            for produto in identificados
        ]

    return tuple(identificados)


def criar_envelope_resultado(
    texto: str,
    natureza: NaturezaResposta,
    tipo_atendimento: TipoAtendimento,
    rota_tecnica: str,
    mecanismo: Mecanismo,
    status: StatusResultado,
    tarefa: TarefaConversacional | None = None,
    chunks: list[dict] | None = None,
    participantes_comparacao: tuple[str, ...] = (),
    etapa_falha: EtapaFalha | None = None,
) -> EnvelopeResultado:
    intencoes = tarefa.intencoes if tarefa else frozenset()
    produtos = identificar_produtos_execucao(texto, chunks or [])
    evidencias = EvidenciasExecucao(
        produtos_sul_taca=produtos,
        participantes_comparacao=participantes_comparacao,
    )
    resultados = _classificar_resultados(
        natureza,
        status,
        evidencias,
    )
    elegivel = _resposta_elegivel(natureza, status)

    return EnvelopeResultado(
        texto_exibicao=texto,
        natureza=natureza,
        elegivel=elegivel,
        tipo_atendimento=tipo_atendimento,
        rota_tecnica=rota_tecnica,
        mecanismo=mecanismo,
        status=status,
        intencoes=intencoes,
        resultados=resultados,
        produtos_sul_taca=produtos,
        etapa_falha=etapa_falha,
    )


def _classificar_resultados(
    natureza: NaturezaResposta,
    status: StatusResultado,
    evidencias: EvidenciasExecucao,
) -> frozenset[Resultado]:
    if (
        natureza != NaturezaResposta.SUBSTANTIVA
        or status != StatusResultado.SUCESSO
    ):
        return frozenset()

    resultados = set()

    if any(
        produto.adequacao_declarada
        for produto in evidencias.produtos_sul_taca
    ):
        resultados.add(Resultado.RECOMENDACAO)

    participantes = {
        _normalizar(participante)
        for participante in evidencias.participantes_comparacao
        if participante.strip()
    }
    if len(participantes) >= 2:
        resultados.add(Resultado.COMPARACAO)

    return frozenset(resultados)


def _resposta_elegivel(
    natureza: NaturezaResposta,
    status: StatusResultado,
) -> bool:
    if status == StatusResultado.INSUFICIENTE:
        return True
    if status in {
        StatusResultado.FALHA_TECNICA,
        StatusResultado.BLOQUEIO_SEGURANCA,
    }:
        return False
    return natureza == NaturezaResposta.SUBSTANTIVA


def _exigir_tarefa_ativa(tarefa: TarefaConversacional) -> None:
    if tarefa.estado != EstadoTarefa.ATIVA:
        raise ValueError("a transição exige uma tarefa ativa")


def _normalizar(texto: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKD", texto)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
        .split()
    )


def _aliases_unicos(
    produto: ProdutoSulTaca,
    catalogo: tuple[ProdutoSulTaca, ...],
) -> tuple[str, ...]:
    nome = re.sub(r"\s+(?:19|20)\d{2}$", "", produto.nome)
    nome_normalizado = _normalizar(nome)
    palavras = nome_normalizado.split()
    aliases = {nome_normalizado}

    for quantidade in range(2, len(palavras) + 1):
        prefixo = " ".join(palavras[:quantidade])
        correspondencias = sum(
            _normalizar(item.nome).startswith(prefixo)
            for item in catalogo
        )
        if correspondencias == 1:
            aliases.add(prefixo)
            break

    return tuple(sorted(aliases, key=len, reverse=True))
