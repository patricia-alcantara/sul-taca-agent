import streamlit as st

from qualidade import (
    obter_avaliacoes_detalhadas,
    obter_contexto,
    obter_funcionamento,
    obter_mecanismos,
    obter_metricas,
)


st.set_page_config(
    page_title="Qualidade do atendimento | Sul Taça",
    page_icon="📋",
    layout="wide",
)

st.title("Painel de qualidade do atendimento")

metricas = obter_metricas()

st.subheader("Qualidade das respostas")
colunas_qualidade = st.columns(6)
colunas_qualidade[0].metric(
    "Disponíveis para avaliação",
    metricas["respostas_elegiveis"],
    help="Respostas em que a pessoa pode enviar uma avaliação.",
)
colunas_qualidade[1].metric(
    "Respostas avaliadas",
    metricas["respostas_avaliadas"],
)
colunas_qualidade[2].metric("Positivas", metricas["positivas"])
colunas_qualidade[3].metric("Negativas", metricas["negativas"])
colunas_qualidade[4].metric(
    "Percentual positivo",
    f'{metricas["percentual_positivo"]:.1f}%',
)
colunas_qualidade[5].metric(
    "Taxa de participação",
    f'{metricas["taxa_participacao"]:.1f}%',
    help=(
        "Respostas avaliadas divididas pelas respostas disponíveis "
        "para avaliação."
    ),
)

st.subheader("Avaliações por forma de atendimento")
contexto = obter_contexto()

if contexto:
    st.dataframe(
        contexto,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Percentual positivo": st.column_config.NumberColumn(
                format="%.1f%%"
            ),
            "Taxa de participação": st.column_config.NumberColumn(
                format="%.1f%%"
            ),
        },
    )
else:
    st.info("Ainda não há respostas disponíveis para avaliação.")

st.subheader("Recomendações e comparações")
(
    coluna_recomendacoes,
    coluna_comparacoes,
    coluna_sobreposicao,
) = st.columns(3)
coluna_recomendacoes.metric(
    "Recomendações realizadas",
    metricas["recomendacoes"],
)
coluna_comparacoes.metric(
    "Comparações realizadas",
    metricas["comparacoes"],
)
coluna_sobreposicao.metric(
    "Recomendação e comparação",
    metricas["recomendacoes_e_comparacoes"],
    help="Respostas que recomendaram e compararam ao mesmo tempo.",
)
st.caption(
    "As métricas consideram resultados entregues, avaliados ou não. "
    "Não representam compra, conversão, receita ou intenção comercial "
    "confirmada."
)

st.subheader("Funcionamento do atendimento")
funcionamento = obter_funcionamento()
colunas_funcionamento = st.columns(5)
colunas_funcionamento[0].metric(
    "Interações registradas",
    funcionamento["interacoes"],
)
colunas_funcionamento[1].metric("Sucessos", funcionamento["sucessos"])
colunas_funcionamento[2].metric(
    "Informações insuficientes",
    funcionamento["insuficiencias"],
)
colunas_funcionamento[3].metric(
    "Falhas registradas",
    funcionamento["falhas"],
)
colunas_funcionamento[4].metric(
    "Bloqueios registrados",
    funcionamento["bloqueios"],
)

st.subheader("Como a Jessi respondeu")
mecanismos = obter_mecanismos()

if mecanismos:
    st.dataframe(
        mecanismos,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Ainda não há interações registradas.")

st.subheader("Detalhes das respostas avaliadas")
avaliacoes = obter_avaliacoes_detalhadas()

if avaliacoes:
    st.dataframe(
        avaliacoes,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Data": st.column_config.DatetimeColumn(
                format="DD/MM/YYYY HH:mm"
            ),
            "Pergunta": st.column_config.TextColumn(width="medium"),
            "Resposta": st.column_config.TextColumn(width="large"),
            "Resultado": st.column_config.TextColumn(width="medium"),
            "Como a Jessi respondeu": st.column_config.TextColumn(
                width="medium"
            ),
            "Rota técnica": st.column_config.TextColumn(width="small"),
        },
    )
else:
    st.info("Ainda não há respostas avaliadas.")

with st.expander("Sobre os dados", expanded=False):
    st.write(
        "Este painel usa dados locais e não deve ser publicado sem "
        "autenticação. Parte do histórico foi preservada a partir de uma "
        "versão anterior, por isso análises históricas de intenção, "
        "latência e falhas são limitadas."
    )
