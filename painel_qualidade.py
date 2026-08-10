import streamlit as st

from qualidade import (
    obter_avaliacoes_detalhadas,
    obter_contexto,
    obter_metricas,
)


st.set_page_config(
    page_title="Qualidade do atendimento | Sul Taça",
    page_icon="📋",
    layout="wide",
)

st.title("Painel de qualidade do atendimento")
st.caption(
    "Uso local. Este painel não deve ser publicado sem autenticação."
)

metricas = obter_metricas()

st.subheader("Qualidade")
colunas_qualidade = st.columns(5)
colunas_qualidade[0].metric(
    "Respostas avaliadas",
    metricas["respostas_avaliadas"],
)
colunas_qualidade[1].metric("Positivas", metricas["positivas"])
colunas_qualidade[2].metric("Negativas", metricas["negativas"])
colunas_qualidade[3].metric(
    "Percentual positivo",
    f'{metricas["percentual_positivo"]:.1f}%',
)
colunas_qualidade[4].metric(
    "Taxa de participação",
    f'{metricas["taxa_participacao"]:.1f}%',
    help="Respostas avaliadas / respostas elegíveis registradas.",
)

st.subheader("Uso comercial")
coluna_recomendacoes, coluna_comparacoes = st.columns(2)
coluna_recomendacoes.metric(
    "Recomendações realizadas",
    metricas["recomendacoes"],
)
coluna_comparacoes.metric(
    "Comparações realizadas",
    metricas["comparacoes"],
)
st.caption(
    "As métricas contabilizam respostas elegíveis classificadas, "
    "avaliadas ou não. Não representam compra, conversão, receita "
    "ou intenção comercial confirmada."
)

st.subheader("Qualidade por tipo de atendimento")
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
        },
    )
else:
    st.info("Ainda não há respostas elegíveis registradas.")

st.subheader("Respostas avaliadas")
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
            "Rota técnica": st.column_config.TextColumn(width="small"),
        },
    )
else:
    st.info("Ainda não há respostas avaliadas.")
