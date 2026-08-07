import streamlit as st
from dotenv import load_dotenv
from google import genai

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
    "Posso ajudar você a escolher um vinho, consultar pedidos "
    "ou entender nossas políticas."
)


@st.cache_resource
def inicializar_rag():
    cliente = genai.Client()
    chunks = carregar_chunks()
    vetores = gerar_embeddings(chunks, cliente)
    indice = criar_indice(vetores)

    return cliente, chunks, indice

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


with st.spinner("Preparando a adega..."):
    cliente, chunks, indice = inicializar_rag()


if "mensagens" not in st.session_state:
    st.session_state.mensagens = [
        {
            "papel": "jessi",
            "conteudo": MENSAGEM_INICIAL,
        }
    ]

if "historico" not in st.session_state:
    st.session_state.historico = [
        {
            "papel": "jessi",
            "conteudo": MENSAGEM_INICIAL,
        }
    ]


if st.sidebar.button(
    "↻ Nova conversa",
    use_container_width=True,
):
    st.session_state.mensagens = [
        {
            "papel": "jessi",
            "conteudo": MENSAGEM_INICIAL,
        }
    ]
    st.session_state.historico = [
        {
            "papel": "jessi",
            "conteudo": MENSAGEM_INICIAL,
        }
    ]
    st.rerun()


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
            st.markdown(mensagem["conteudo"])

pergunta = st.chat_input("Digite sua mensagem")

if pergunta:
    st.session_state.mensagens.append(
        {
            "papel": "usuario",
            "conteudo": pergunta,
        }
    )

    with st.chat_message("user"):
        st.markdown(pergunta)

    with st.chat_message("assistant"):
        with st.spinner("Consultando a adega..."):
            resposta = responder_pergunta(
                pergunta,
                chunks,
                indice,
                st.session_state.historico,
                cliente,
            )

        exibir_resposta_jessi(resposta)

    st.session_state.historico.append(
        {
            "papel": "usuario",
            "conteudo": pergunta,
        }
    )
    st.session_state.historico.append(
        {
            "papel": "jessi",
            "conteudo": resposta,
        }
    )
    st.session_state.mensagens.append(
        {
            "papel": "jessi",
            "conteudo": resposta,
        }
    )