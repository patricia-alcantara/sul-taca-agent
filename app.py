import re
from uuid import uuid4

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import errors

from atendimento import (
    EtapaFalha,
    EtapaTarefa,
    Intencao,
    Mecanismo,
    NaturezaResposta,
    OrigemTarefa,
    Resultado,
    StatusResultado,
    TipoAtendimento,
    atualizar_tarefa_por_mensagem,
    concluir_tarefa,
    criar_envelope_resultado,
    iniciar_tarefa,
    limpar_tarefa,
)
from busca_semantica import (
    carregar_chunks,
    criar_indice,
    gerar_embeddings,
    recuperar_contexto,
    responder_pergunta,
)
from consulta_url import (
    atualizar_comparacao_pendente,
    comparar_dados_fornecidos,
    comparacao_tem_dados_suficientes,
    consultar_pagina_vinho,
    criar_comparacao_pendente,
    decidir_rota,
    eh_continuacao_comparacao,
    extrair_url,
    identificar_produto_catalogo,
)
from qualidade import (
    TIPO_CATALOGO,
    TIPO_COMPARACAO,
    TIPO_FLUXO_GUIADO,
    TIPO_ORIENTACAO,
    avaliar_resposta,
    obter_avaliacao,
    registrar_interacao,
    registrar_resposta_elegivel,
)


load_dotenv()

st.set_page_config(
    page_title="Jessi | Sul Taça",
    page_icon="🍷",
    layout="centered",
)

LARGURA_BOTAO_MENU = 224

MENSAGEM_INICIAL = (
    "Oi! Eu sou a **Jessi**, assistente virtual da Sul Taça. "
    "Posso ajudar você a escolher um vinho, tirar dúvidas "
    "sobre compras ou entender nossas políticas."
)

MENSAGEM_NOME = (
    "Que bom ter você por aqui! Como posso te chamar?"
)

MENSAGEM_MENU_PRINCIPAL = (
    "Como posso ajudar?"
)

MENSAGEM_SUBMENU_ESCOLHA = (
    "Como você gostaria de começar?"
)

MENSAGEM_LIMITE_COMPRA = (
    "Por este chat, consigo explicar os procedimentos da "
    "Sul Taça e ajudar você a identificar as informações "
    "necessárias. Ainda não consigo acessar ou alterar "
    "pedidos, emitir nota fiscal, acompanhar entregas ou "
    "abrir solicitações.\n\n"
    "Se quiser, conte o que aconteceu e eu ajudo a preparar "
    "o contato com o canal oficial."
)

MENSAGEM_SUBMENU_POLITICAS = (
    "Sobre qual assunto você quer saber?"
)

MENSAGEM_COTA_INDISPONIVEL = (
    "Não consegui responder agora porque o serviço está "
    "temporariamente indisponível. Sua mensagem ficou "
    "registrada na conversa. Tente novamente mais tarde."
)

MENSAGEM_PEDIR_VINHO = (
    "Me conta qual vinho você quer comparar e mais características:\n"
    "ex: **uva, safra ou preço**. \n"
    "Com essas informações, consigo fazer uma comparação inicial. "
    "Se achar mais fácil, você também pode enviar o link direto da "
    "página do produto."
)

MENSAGEM_PEDIR_DETALHES = (
    "Encontrei o vinho. Me conta o que você quer comparar: pode ser "
    "**o preço, o sabor, o que você sente ao beber ou com quais pratos "
    "ele combina**. Me diga o que souber. Se for mais fácil, mande o "
    "link direto da página."
)

MENSAGEM_PEDIR_DADOS = (
    "Entendi. E o que você sabe sobre isso no outro vinho? "
    "Se for mais fácil, mande o link direto da página."
)

MENSAGEM_BLOQUEIO_CONSULTA = (
    "Para proteger seus dados, não acesso páginas externas "
    "quando a mensagem pode conter informação pessoal ou de "
    "pedido. Reformule usando somente o nome do vinho e o "
    "link direto da página do produto."
)

MENSAGEM_PAGINA_INSUFICIENTE = (
    "Consegui acessar o site, mas essa página não traz detalhes "
    "suficientes sobre o vinho. Se puder, envie a página específica "
    "do rótulo."
)

CABECALHO_HTML = """
<style>
.sultaca-header {
    align-items: flex-start;
    display: flex;
    gap: clamp(0.75rem, 2vw, 1rem);
    padding: 0.35rem 0 clamp(1.75rem, 4vw, 2.5rem);
}

.sultaca-copy {
    min-width: 0;
}

.sultaca-title {
    color: #5A356A;
    font-family: ui-serif, Georgia, "Times New Roman", serif;
    font-size: clamp(2.25rem, 8vw, 3.45rem);
    font-weight: 700;
    letter-spacing: -0.025em;
    line-height: 1.02;
    margin: 0;
    overflow-wrap: break-word;
}

.sultaca-subtitle {
    color: #26212A;
    font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
    font-size: clamp(1rem, 2.4vw, 1.125rem);
    line-height: 1.45;
    margin: 0.45rem 0 0;
}

.st-key-sultaca-menu-principal,
.st-key-sultaca-menu-escolha,
.st-key-sultaca-menu-politicas {
    padding-inline-start: 3.5rem;
}

.st-key-sultaca-menu-principal button,
.st-key-sultaca-menu-escolha button,
.st-key-sultaca-menu-politicas button {
    justify-content: flex-start;
    text-align: left;
}

/* Estrutura interna do Streamlit 1.61.1; revalidar ao atualizar. */
.st-key-sultaca-menu-principal button > div,
.st-key-sultaca-menu-escolha button > div,
.st-key-sultaca-menu-politicas button > div {
    justify-content: flex-start;
}
</style>
<header class="sultaca-header">
    <div class="sultaca-copy">
        <h1 class="sultaca-title">Sul Taça</h1>
        <p class="sultaca-subtitle">
            Encontre o vinho certo para cada momento.
        </p>
    </div>
</header>
"""

def criar_mensagens_iniciais() -> list[dict]:
    return [
        {
            "papel": "jessi",
            "conteudo": MENSAGEM_INICIAL,
        },
        {
            "papel": "jessi",
            "conteudo": MENSAGEM_NOME,
        },
    ]


def reiniciar_conversa() -> None:
    mensagens_iniciais = criar_mensagens_iniciais()

    st.session_state.nome_usuario = None
    st.session_state.etapa_atual = "nome"
    st.session_state.comparacao_pendente = None
    st.session_state.tarefa_atual = None
    st.session_state.mensagens = mensagens_iniciais.copy()
    st.session_state.historico = mensagens_iniciais.copy()

def adicionar_mensagem(
    papel: str,
    conteudo: str,
    incluir_no_historico: bool = True,
    *,
    avaliavel: bool = False,
    pergunta_origem: str = "",
    rota_tecnica: str = "",
    tipo_atendimento: str = "",
    eh_recomendacao: bool = False,
    eh_comparacao: bool = False,
    envelope=None,
    task_id: str | None = None,
) -> None:
    mensagem = {
        "papel": papel,
        "conteudo": conteudo,
    }

    if papel == "jessi" and envelope is not None:
        message_id = str(uuid4())
        mensagem["message_id"] = message_id
        mensagem["avaliavel"] = envelope.elegivel
        if envelope.elegivel:
            mensagem.update(
                {
                    "pergunta_origem": pergunta_origem,
                    "rota_tecnica": envelope.rota_tecnica,
                    "tipo_atendimento": tipo_atendimento,
                    "eh_recomendacao": (
                        Resultado.RECOMENDACAO in envelope.resultados
                    ),
                    "eh_comparacao": (
                        Resultado.COMPARACAO in envelope.resultados
                    ),
                }
            )
        registrar_interacao(
            message_id=message_id,
            session_id=st.session_state.session_id,
            envelope=envelope,
            task_id=task_id,
        )
    elif papel == "jessi" and avaliavel:
        mensagem.update(
            {
                "message_id": str(uuid4()),
                "avaliavel": True,
                "pergunta_origem": pergunta_origem,
                "rota_tecnica": rota_tecnica,
                "tipo_atendimento": tipo_atendimento,
                "eh_recomendacao": eh_recomendacao,
                "eh_comparacao": eh_comparacao,
            }
        )
        registrar_resposta_elegivel(
            message_id=mensagem["message_id"],
            session_id=st.session_state.session_id,
            rota_tecnica=rota_tecnica,
            tipo_atendimento=tipo_atendimento,
            eh_recomendacao=eh_recomendacao,
            eh_comparacao=eh_comparacao,
        )

    st.session_state.mensagens.append(mensagem)

    if incluir_no_historico:
        st.session_state.historico.append(
            mensagem.copy()
        )

def registrar_escolha(
    escolha: str,
    resposta: str,
    proxima_etapa: str,
    *,
    avaliavel: bool = False,
    tipo_atendimento: str = "",
    eh_recomendacao: bool = False,
) -> None:
    adicionar_mensagem("usuario", escolha)
    adicionar_mensagem(
        "jessi",
        resposta,
        avaliavel=avaliavel,
        pergunta_origem=escolha,
        rota_tecnica="fluxo_guiado",
        tipo_atendimento=tipo_atendimento,
        eh_recomendacao=eh_recomendacao,
    )
    st.session_state.etapa_atual = proxima_etapa
    st.rerun()

def anexar_fontes(
    resposta: str,
    *fontes: str,
) -> str:
    fontes_disponiveis = [
        fonte
        for fonte in fontes
        if fonte
    ]

    if not fontes_disponiveis:
        return resposta

    return (
        f"{resposta.strip()}\n---\n"
        + "\n\n".join(fontes_disponiveis)
    )

def preparar_markdown(conteudo: str) -> str:
    return re.sub(
        r"(?<!\\)R\$",
        r"R\\$",
        conteudo,
    )


TIPOS_ATENDIMENTO_DOMINIO = {
    TIPO_CATALOGO: TipoAtendimento.CATALOGO_DOCUMENTOS,
    TIPO_COMPARACAO: TipoAtendimento.COMPARACAO_EXTERNA,
    TIPO_FLUXO_GUIADO: TipoAtendimento.FLUXO_GUIADO,
    TIPO_ORIENTACAO: TipoAtendimento.ORIENTACAO_SEM_CONSULTA,
}


def mecanismo_da_rota(rota: str) -> Mecanismo:
    if rota == "url":
        return Mecanismo.URL_CONTEXT
    if rota == "hibrida":
        return Mecanismo.HIBRIDO
    if rota in {
        "pedir_detalhes",
        "pedir_vinho",
        "bloquear_url",
    }:
        return Mecanismo.REGRA_LOCAL
    return Mecanismo.RAG_INTERNO

@st.cache_resource
def inicializar_rag():
    cliente = genai.Client()
    chunks = carregar_chunks()
    vetores = gerar_embeddings(chunks, cliente)
    indice = criar_indice(vetores)

    return cliente, chunks, indice

def processar_pergunta(pergunta: str) -> None:
    natureza = NaturezaResposta.SUBSTANTIVA
    status = StatusResultado.SUCESSO
    participantes_comparacao = ()
    tarefa_anterior = st.session_state.tarefa_atual
    tarefa = atualizar_tarefa_por_mensagem(
        tarefa_anterior,
        pergunta,
    )
    tipo_atendimento = (
        TIPO_FLUXO_GUIADO
        if tarefa and tarefa.origem == OrigemTarefa.MENU_GUIADO
        else TIPO_CATALOGO
    )
    st.session_state.tarefa_atual = tarefa
    if (
        tarefa_anterior
        and (tarefa is None or tarefa.task_id != tarefa_anterior.task_id)
    ):
        st.session_state.comparacao_pendente = None

    try:
        with st.spinner("Consultando a adega..."):
            cliente, chunks, indice = inicializar_rag()
            rota = decidir_rota(pergunta, chunks)
            comparacao_pendente = (
                st.session_state.comparacao_pendente
            )
            pergunta_consulta = pergunta

            if comparacao_pendente and extrair_url(pergunta):
                pergunta_consulta = (
                    "Compare "
                    f"{comparacao_pendente['produto_sul_taca']} "
                    "com "
                    f"{comparacao_pendente['vinho_externo']}: "
                    f"{pergunta}"
                )
                rota = decidir_rota(
                    pergunta_consulta,
                    chunks,
                )

            if rota == "pedir_detalhes":
                comparacao_pendente = criar_comparacao_pendente(
                    pergunta,
                    chunks,
                )
                atualizar_comparacao_pendente(
                    comparacao_pendente,
                    pergunta,
                )
                st.session_state.comparacao_pendente = (
                    comparacao_pendente
                )

            if comparacao_pendente and (
                rota == "pedir_detalhes"
                or (
                    rota not in ("url", "hibrida", "bloquear_url")
                    and eh_continuacao_comparacao(pergunta)
                )
            ):
                tipo_atendimento = TIPO_COMPARACAO

                if rota != "pedir_detalhes":
                    atualizar_comparacao_pendente(
                        comparacao_pendente,
                        pergunta,
                    )

                if not comparacao_tem_dados_suficientes(
                    comparacao_pendente
                ):
                    natureza = NaturezaResposta.ESCLARECIMENTO
                    resposta = (
                        MENSAGEM_PEDIR_DADOS
                        if comparacao_pendente["criterios"]
                        else MENSAGEM_PEDIR_DETALHES
                    )
                else:
                    produto = comparacao_pendente[
                        "produto_sul_taca"
                    ]
                    participantes_comparacao = (
                        produto,
                        comparacao_pendente["vinho_externo"],
                    )
                    contexto, fontes_internas = recuperar_contexto(
                        pergunta_consulta,
                        chunks,
                        indice,
                        cliente,
                        produto,
                    )
                    resposta = comparar_dados_fornecidos(
                        comparacao_pendente,
                        contexto,
                        cliente,
                    )
                    resposta = anexar_fontes(
                        resposta,
                        fontes_internas,
                    )
                    st.session_state.comparacao_pendente = None
            elif rota == "pedir_vinho":
                st.session_state.comparacao_pendente = None
                resposta = MENSAGEM_PEDIR_VINHO
                tipo_atendimento = TIPO_COMPARACAO
                natureza = NaturezaResposta.ESCLARECIMENTO
            elif (
                comparacao_pendente
                and rota not in ("url", "hibrida")
            ):
                st.session_state.comparacao_pendente = None
                resposta = responder_pergunta(
                    pergunta,
                    chunks,
                    indice,
                    st.session_state.historico,
                    cliente,
                )
            elif rota == "bloquear_url":
                resposta = MENSAGEM_BLOQUEIO_CONSULTA
                natureza = NaturezaResposta.OPERACIONAL
                status = StatusResultado.BLOQUEIO_SEGURANCA
            elif rota in ("url", "hibrida"):
                tipo_atendimento = TIPO_COMPARACAO
                contexto = ""
                fontes_internas = ""
                produto = ""

                if rota == "hibrida":
                    produto = (
                        comparacao_pendente["produto_sul_taca"]
                        if comparacao_pendente
                        else identificar_produto_catalogo(
                            pergunta_consulta,
                            chunks,
                        )
                    )
                    contexto, fontes_internas = recuperar_contexto(
                        pergunta,
                        chunks,
                        indice,
                        cliente,
                        produto,
                    )

                resposta_url, fonte_externa = consultar_pagina_vinho(
                    pergunta_consulta,
                    cliente,
                    contexto,
                )

                if not resposta_url or not fonte_externa:
                    resposta = MENSAGEM_PAGINA_INSUFICIENTE
                    natureza = NaturezaResposta.ORIENTACAO_RECUPERACAO
                    status = StatusResultado.INSUFICIENTE
                else:
                    if comparacao_pendente:
                        participantes_comparacao = (
                            comparacao_pendente["produto_sul_taca"],
                            comparacao_pendente["vinho_externo"],
                        )
                    elif produto:
                        participantes_comparacao = (
                            produto,
                            extrair_url(pergunta_consulta),
                        )
                    resposta = anexar_fontes(
                        resposta_url,
                        fontes_internas,
                        fonte_externa,
                    )
                    st.session_state.comparacao_pendente = None
            else:
                resposta = responder_pergunta(
                    pergunta,
                    chunks,
                    indice,
                    st.session_state.historico,
                    cliente,
                )

    except errors.APIError as erro:
        if erro.code != 429:
            raise

        envelope = criar_envelope_resultado(
            texto=MENSAGEM_COTA_INDISPONIVEL,
            natureza=NaturezaResposta.OPERACIONAL,
            tipo_atendimento=TIPOS_ATENDIMENTO_DOMINIO[
                tipo_atendimento
            ],
            rota_tecnica="erro_api",
            mecanismo=Mecanismo.RAG_INTERNO,
            status=StatusResultado.FALHA_TECNICA,
            tarefa=tarefa,
            etapa_falha=EtapaFalha.GERACAO,
        )

        if tarefa:
            limpar_tarefa(tarefa)
            st.session_state.tarefa_atual = None

        adicionar_mensagem("usuario", pergunta)
        adicionar_mensagem(
            "jessi",
            envelope.texto_exibicao,
            incluir_no_historico=False,
            pergunta_origem=pergunta,
            tipo_atendimento=tipo_atendimento,
            envelope=envelope,
            task_id=tarefa.task_id if tarefa else None,
        )
        st.session_state.etapa_atual = "conversa"
        st.rerun()

    envelope = criar_envelope_resultado(
        texto=resposta,
        natureza=natureza,
        tipo_atendimento=TIPOS_ATENDIMENTO_DOMINIO[tipo_atendimento],
        rota_tecnica=rota,
        mecanismo=mecanismo_da_rota(rota),
        status=status,
        tarefa=tarefa,
        chunks=chunks,
        participantes_comparacao=participantes_comparacao,
    )

    if tarefa and (
        envelope.natureza == NaturezaResposta.SUBSTANTIVA
        and envelope.status == StatusResultado.SUCESSO
    ):
        concluir_tarefa(tarefa)
        st.session_state.tarefa_atual = None
    elif tarefa and envelope.status == StatusResultado.BLOQUEIO_SEGURANCA:
        limpar_tarefa(tarefa)
        st.session_state.tarefa_atual = None

    adicionar_mensagem("usuario", pergunta)
    adicionar_mensagem(
        "jessi",
        envelope.texto_exibicao,
        avaliavel=envelope.elegivel,
        pergunta_origem=pergunta,
        rota_tecnica=rota,
        tipo_atendimento=tipo_atendimento,
        eh_recomendacao=(
            Resultado.RECOMENDACAO in envelope.resultados
        ),
        eh_comparacao=(
            Resultado.COMPARACAO in envelope.resultados
        ),
        envelope=envelope,
        task_id=tarefa.task_id if tarefa else None,
    )
    st.session_state.etapa_atual = "conversa"
    st.rerun()

def exibir_resposta_jessi(mensagem: dict) -> None:
    conteudo = mensagem["conteudo"]
    partes = conteudo.rsplit("\n---\n", 1)

    if (
        len(partes) == 2
        and "fonte" in partes[1].lower()
    ):
        resposta, fonte = partes

        st.markdown(
            preparar_markdown(resposta.strip())
        )

        with st.expander("Ver fontes consultadas"):
            st.markdown(
                preparar_markdown(fonte.strip())
            )
    else:
        st.markdown(
            preparar_markdown(conteudo)
        )

    if not mensagem.get("avaliavel"):
        return

    message_id = mensagem["message_id"]
    avaliacao = obter_avaliacao(message_id)

    if avaliacao is not None:
        st.caption("✓ Feedback recebido.")
        return

    st.caption("Esta resposta foi útil?")

    def registrar_avaliacao(valor: bool) -> None:
        nome = st.session_state.get("nome_usuario") or ""
        avaliar_resposta(
            message_id=message_id,
            avaliacao=valor,
            pergunta=mensagem.get("pergunta_origem", ""),
            resposta=conteudo,
            termos_sensiveis=(nome,),
        )
        st.rerun()

    with st.container(horizontal=True, gap="xsmall"):
        if st.button(
            "👍",
            key=f"avaliacao_positiva_{message_id}",
            help="Gostei",
            width="content",
        ):
            registrar_avaliacao(True)

        if st.button(
            "👎",
            key=f"avaliacao_negativa_{message_id}",
            help="Não gostei",
            width="content",
        ):
            registrar_avaliacao(False)

st.html(CABECALHO_HTML)


if "acesso_maioridade" not in st.session_state:
    st.session_state.acesso_maioridade = None

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid4())


if st.session_state.acesso_maioridade is None:
    with st.chat_message("assistant"):
        st.markdown(MENSAGEM_INICIAL)
        st.markdown(
            "Antes de continuar, preciso confirmar: "
            "você tem **18 anos ou mais**?"
        )

    coluna_sim, coluna_nao = st.columns(2)

    if coluna_sim.button(
        "Sim, tenho 18 anos ou mais",
        width="stretch",
        type="primary",
    ):
        st.session_state.acesso_maioridade = True
        st.rerun()

    if coluna_nao.button(
        "Não",
        width="stretch",
    ):
        st.session_state.acesso_maioridade = False
        st.rerun()

    st.stop()


if st.session_state.acesso_maioridade is False:
    st.warning(
        "Não posso orientar a compra de bebidas "
        "alcoólicas para menores de 18 anos."
    )

    if st.button("Voltar"):
        st.session_state.acesso_maioridade = None
        st.rerun()

    st.stop()


chaves_da_conversa = (
    "nome_usuario",
    "etapa_atual",
    "comparacao_pendente",
    "tarefa_atual",
    "mensagens",
    "historico",
)

if any(
    chave not in st.session_state
    for chave in chaves_da_conversa
):
    reiniciar_conversa()

for mensagem in st.session_state.mensagens:
    papel_streamlit = (
        "user"
        if mensagem["papel"] == "usuario"
        else "assistant"
    )

    with st.chat_message(papel_streamlit):
        if mensagem["papel"] == "jessi":
            exibir_resposta_jessi(mensagem)
        else:
            st.markdown(
                mensagem["conteudo"]
            )
if st.session_state.etapa_atual == "nome":
    with st.form("formulario_nome"):
        nome_informado = st.text_input(
            "Nome",
            placeholder="Digite seu nome",
            label_visibility="collapsed",
        )
        continuar = st.form_submit_button(
            "Continuar",
            width="stretch",
            type="primary",
        )

    if continuar and nome_informado.strip():
        nome_informado = nome_informado.strip()
        st.session_state.nome_usuario = nome_informado
        adicionar_mensagem(
            "usuario",
            nome_informado,
        )
        adicionar_mensagem(
            "jessi",
            (
                f"Prazer, **{nome_informado}**. "
                f"{MENSAGEM_MENU_PRINCIPAL}"
            ),
        )
        st.session_state.etapa_atual = "menu_principal"
        st.rerun()

    if st.button(
        "Prefiro não informar",
        key="pular_nome",
        width="stretch",
    ):
        registrar_escolha(
            "Prefiro não informar",
            MENSAGEM_MENU_PRINCIPAL,
            "menu_principal",
        )

elif st.session_state.etapa_atual == "menu_principal":
    menu_principal = st.container(
        key="sultaca-menu-principal",
        horizontal_alignment="left",
    )

    if menu_principal.button(
        "Quero ajuda para escolher",
        key="menu_escolher",
        width=LARGURA_BOTAO_MENU,
        icon=":material/wine_bar:",
    ):
        registrar_escolha(
            "Quero ajuda para escolher",
            MENSAGEM_SUBMENU_ESCOLHA,
            "menu_escolha",
        )

    if menu_principal.button(
        "Tenho um vinho em mente",
        key="menu_vinho_especifico",
        width=LARGURA_BOTAO_MENU,
        icon=":material/search:",
    ):
        st.session_state.tarefa_atual = iniciar_tarefa(
            {Intencao.CONSULTA_CATALOGO_POLITICA},
            OrigemTarefa.MENU_GUIADO,
            EtapaTarefa.AGUARDANDO_PRODUTO,
        )
        registrar_escolha(
            "Tenho um vinho em mente",
            (
                "Qual vinho você tem em mente? "
                "Pode escrever o nome ou o que lembra do rótulo."
            ),
            "conversa",
        )

    if menu_principal.button(
        "Ajuda com uma compra",
        key="menu_ajuda_compra",
        width=LARGURA_BOTAO_MENU,
        icon=":material/receipt_long:",
    ):
        registrar_escolha(
            "Ajuda com uma compra",
            MENSAGEM_LIMITE_COMPRA,
            "conversa",
            avaliavel=True,
            tipo_atendimento=TIPO_ORIENTACAO,
        )

    if menu_principal.button(
        "Políticas e privacidade",
        key="menu_politicas",
        width=LARGURA_BOTAO_MENU,
        icon=":material/policy:",
    ):
        registrar_escolha(
            "Políticas e privacidade",
            MENSAGEM_SUBMENU_POLITICAS,
            "menu_politicas",
        )

    if menu_principal.button(
        "Outras dúvidas e sugestões",
        key="menu_outras_duvidas",
        width=LARGURA_BOTAO_MENU,
        icon=":material/chat:",
    ):
        registrar_escolha(
            "Outras dúvidas e sugestões",
            "Pode me contar como posso ajudar?",
            "conversa",
        )

elif st.session_state.etapa_atual == "menu_escolha":
    menu_escolha = st.container(
        key="sultaca-menu-escolha",
        horizontal_alignment="left",
    )
    perguntas_de_escolha = {
        "Para acompanhar um prato": (
            "Qual prato você pretende servir?",
            ":material/restaurant:",
        ),
        "Para uma ocasião": (
            "Qual é a ocasião e que clima você imaginou?",
            ":material/celebration:",
        ),
        "Para presentear": (
            "O que você sabe sobre as preferências "
            "de quem vai receber o presente?",
            ":material/featured_seasonal_and_gifts:",
        ),
        "Por faixa de preço": (
            "Qual faixa de preço você gostaria de considerar?",
            ":material/payments:",
        ),
        "Quero descobrir algo novo": (
            "Você tem alguma preferência ou restrição "
            "que eu deva considerar?",
            ":material/explore:",
        ),
    }

    for indice, (
        opcao,
        (resposta, icone),
    ) in enumerate(perguntas_de_escolha.items()):
        if menu_escolha.button(
            opcao,
            key=f"submenu_escolha_{indice}",
            width=LARGURA_BOTAO_MENU,
            icon=icone,
        ):
            st.session_state.tarefa_atual = iniciar_tarefa(
                {Intencao.RECOMENDACAO},
                OrigemTarefa.MENU_GUIADO,
                EtapaTarefa.AGUARDANDO_NECESSIDADE,
            )
            registrar_escolha(
                opcao,
                resposta,
                "conversa",
            )


elif st.session_state.etapa_atual == "menu_politicas":
    menu_politicas = st.container(
        key="sultaca-menu-politicas",
        horizontal_alignment="left",
    )
    perguntas_de_politicas = {
        "Privacidade e dados": (
            "Quero saber sobre privacidade e uso de dados.",
            ":material/lock:",
        ),
        "Compras e entregas": (
            "Quero saber sobre compras e entregas.",
            ":material/local_shipping:",
        ),
        "Trocas e reembolsos": (
            "Quero saber sobre trocas e reembolsos.",
            ":material/sync_alt:",
        ),
    }

    for indice, (
        opcao,
        (pergunta_da_politica, icone),
    ) in enumerate(perguntas_de_politicas.items()):
        if menu_politicas.button(
            opcao,
            key=f"submenu_politicas_{indice}",
            width=LARGURA_BOTAO_MENU,
            icon=icone,
        ):
            st.session_state.tarefa_atual = iniciar_tarefa(
                {Intencao.CONSULTA_CATALOGO_POLITICA},
                OrigemTarefa.MENU_GUIADO,
                EtapaTarefa.EM_EXECUCAO,
            )
            processar_pergunta(pergunta_da_politica)

pergunta = (
    None
    if st.session_state.etapa_atual == "nome"
    else st.chat_input("Digite sua mensagem")
)

if pergunta:
    processar_pergunta(pergunta)
