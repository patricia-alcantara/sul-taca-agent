import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import errors

from busca_semantica import (
    carregar_chunks,
    criar_indice,
    gerar_embeddings,
    responder_pergunta,
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

        st.markdown(resposta.strip())

        with st.expander("Ver fonte consultada"):
            st.markdown(fonte.strip())
    else:
        st.markdown(conteudo)

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
    ):
        registrar_escolha(
            "Outras dúvidas e sugestões",
            "Pode me contar como posso ajudar?",
            "conversa",
        )

elif st.session_state.etapa_atual == "menu_escolha":
    perguntas_de_escolha = {
        "Para acompanhar um prato": (
            "Qual prato você pretende servir?"
        ),
        "Para uma ocasião": (
            "Qual é a ocasião e que clima você imaginou?"
        ),
        "Para presentear": (
            "O que você sabe sobre as preferências "
            "de quem vai receber o presente?"
        ),
        "Por faixa de preço": (
            "Qual faixa de preço você gostaria de considerar?"
        ),
        "Quero descobrir algo novo": (
            "Você tem alguma preferência ou restrição "
            "que eu deva considerar?"
        ),
    }

    for indice, (
        opcao,
        resposta,
    ) in enumerate(perguntas_de_escolha.items()):
        if st.button(
            opcao,
            key=f"submenu_escolha_{indice}",
            use_container_width=True,
        ):
            registrar_escolha(
                opcao,
                resposta,
                "conversa",
            )


elif st.session_state.etapa_atual == "menu_politicas":
    perguntas_de_politicas = {
        "Privacidade e dados": (
            "Quero saber sobre privacidade e uso de dados."
        ),
        "Compras e entregas": (
            "Quero saber sobre compras e entregas."
        ),
        "Trocas e reembolsos": (
            "Quero saber sobre trocas e reembolsos."
        ),
    }

    for indice, (
        opcao,
        pergunta_da_politica,
    ) in enumerate(perguntas_de_politicas.items()):
        if st.button(
            opcao,
            key=f"submenu_politicas_{indice}",
            use_container_width=True,
        ):
            processar_pergunta(pergunta_da_politica)

placeholder = (
    "Digite seu nome"
    if st.session_state.etapa_atual == "nome"
    else "Digite sua mensagem"
)

pergunta = st.chat_input(placeholder)

if pergunta:
    if st.session_state.etapa_atual == "nome":
        nome_informado = pergunta.strip()

        respostas_sem_nome = {
            "prefiro não informar",
            "não quero informar",
            "pular",
        }

        if nome_informado.lower() in respostas_sem_nome:
            st.session_state.nome_usuario = None
            mensagem_usuario = "Prefiro não informar"
            mensagem_jessi = MENSAGEM_MENU_PRINCIPAL
        else:
            st.session_state.nome_usuario = nome_informado
            mensagem_usuario = nome_informado
            mensagem_jessi = (
                f"Prazer, **{nome_informado}**. "
                f"{MENSAGEM_MENU_PRINCIPAL}"
            )

        adicionar_mensagem(
            "usuario",
            mensagem_usuario,
        )
        adicionar_mensagem(
            "jessi",
            mensagem_jessi,
        )

        st.session_state.etapa_atual = "menu_principal"
        st.rerun()

    else:
        processar_pergunta(pergunta)