import re

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import errors

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


load_dotenv()

st.set_page_config(
    page_title="Jessi | Sul Taça",
    page_icon="🍷",
    layout="centered",
)

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
    st.session_state.mensagens = mensagens_iniciais.copy()
    st.session_state.historico = mensagens_iniciais.copy()

def adicionar_mensagem(
    papel: str,
    conteudo: str,
    incluir_no_historico: bool = True,
) -> None:
    mensagem = {
        "papel": papel,
        "conteudo": conteudo,
    }

    st.session_state.mensagens.append(mensagem)

    if incluir_no_historico:
        st.session_state.historico.append(
            mensagem.copy()
        )

def registrar_escolha(
    escolha: str,
    resposta: str,
    proxima_etapa: str,
) -> None:
    adicionar_mensagem("usuario", escolha)
    adicionar_mensagem("jessi", resposta)
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

@st.cache_resource
def inicializar_rag():
    cliente = genai.Client()
    chunks = carregar_chunks()
    vetores = gerar_embeddings(chunks, cliente)
    indice = criar_indice(vetores)

    return cliente, chunks, indice

def processar_pergunta(pergunta: str) -> None:
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
                if rota != "pedir_detalhes":
                    atualizar_comparacao_pendente(
                        comparacao_pendente,
                        pergunta,
                    )

                if not comparacao_tem_dados_suficientes(
                    comparacao_pendente
                ):
                    resposta = (
                        MENSAGEM_PEDIR_DADOS
                        if comparacao_pendente["criterios"]
                        else MENSAGEM_PEDIR_DETALHES
                    )
                else:
                    produto = comparacao_pendente[
                        "produto_sul_taca"
                    ]
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
            elif rota in ("url", "hibrida"):
                contexto = ""
                fontes_internas = ""

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
                else:
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

        adicionar_mensagem("usuario", pergunta)
        adicionar_mensagem(
            "jessi",
            MENSAGEM_COTA_INDISPONIVEL,
            incluir_no_historico=False,
        )
        st.session_state.etapa_atual = "conversa"
        st.rerun()

    adicionar_mensagem("usuario", pergunta)
    adicionar_mensagem("jessi", resposta)
    st.session_state.etapa_atual = "conversa"
    st.rerun()

def exibir_resposta_jessi(conteudo: str) -> None:
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

st.title("Sul Taça")
st.caption("Encontre o vinho certo para cada momento.")


if "acesso_maioridade" not in st.session_state:
    st.session_state.acesso_maioridade = None


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
        use_container_width=True,
        type="primary",
    ):
        st.session_state.acesso_maioridade = True
        st.rerun()

    if coluna_nao.button(
        "Não",
        use_container_width=True,
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
            exibir_resposta_jessi(
                mensagem["conteudo"]
            )
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
            use_container_width=True,
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
        use_container_width=True,
    ):
        registrar_escolha(
            "Prefiro não informar",
            MENSAGEM_MENU_PRINCIPAL,
            "menu_principal",
        )

elif st.session_state.etapa_atual == "menu_principal":
    if st.button(
        "Quero ajuda para escolher",
        key="menu_escolher",
        use_container_width=True,
        icon=":material/wine_bar:",
    ):
        registrar_escolha(
            "Quero ajuda para escolher",
            MENSAGEM_SUBMENU_ESCOLHA,
            "menu_escolha",
        )

    if st.button(
        "Tenho um vinho em mente",
        key="menu_vinho_especifico",
        use_container_width=True,
        icon=":material/search:",
    ):
        registrar_escolha(
            "Tenho um vinho em mente",
            (
                "Qual vinho você tem em mente? "
                "Pode escrever o nome ou o que lembra do rótulo."
            ),
            "conversa",
        )

    if st.button(
        "Ajuda com uma compra",
        key="menu_ajuda_compra",
        use_container_width=True,
        icon=":material/receipt_long:",
    ):
        registrar_escolha(
            "Ajuda com uma compra",
            MENSAGEM_LIMITE_COMPRA,
            "conversa",
        )

    if st.button(
        "Políticas e privacidade",
        key="menu_politicas",
        use_container_width=True,
        icon=":material/policy:",
    ):
        registrar_escolha(
            "Políticas e privacidade",
            MENSAGEM_SUBMENU_POLITICAS,
            "menu_politicas",
        )

    if st.button(
        "Outras dúvidas e sugestões",
        key="menu_outras_duvidas",
        use_container_width=True,
        icon=":material/chat:",
    ):
        registrar_escolha(
            "Outras dúvidas e sugestões",
            "Pode me contar como posso ajudar?",
            "conversa",
        )

elif st.session_state.etapa_atual == "menu_escolha":
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
        if st.button(
            opcao,
            key=f"submenu_escolha_{indice}",
            use_container_width=True,
            icon=icone,
        ):
            registrar_escolha(
                opcao,
                resposta,
                "conversa",
            )


elif st.session_state.etapa_atual == "menu_politicas":
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
        if st.button(
            opcao,
            key=f"submenu_politicas_{indice}",
            use_container_width=True,
            icon=icone,
        ):
            processar_pergunta(pergunta_da_politica)

pergunta = (
    None
    if st.session_state.etapa_atual == "nome"
    else st.chat_input("Digite sua mensagem")
)

if pergunta:
    processar_pergunta(pergunta)
