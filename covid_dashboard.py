import streamlit as st
import pandas as pd
import plotly.express as px
from snowflake.snowpark import Session
from datetime import datetime

CSV_URL = "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv"
TABLE_NAME = "COVID_DATA"
PAISES = ["Brazil", "United States", "India", "Germany", "South Africa", "Japan"]
DATA_INICIAL = "2021-01-01"

st.set_page_config(
    page_title="COVID-19 Dashboard",
    page_icon="🦠",
    layout="wide",
)

connection_parameters = {
    "user": st.secrets["snowflake"]["user"],
    "password": st.secrets["snowflake"]["password"],
    "account": st.secrets["snowflake"]["account"],
    "warehouse": st.secrets["snowflake"]["warehouse"],
    "database": "TEST_DB",
    "schema": "PUBLIC",
    "role": st.secrets["snowflake"]["role"],
}


def carregar_dados():
    """Lê a tabela do Snowflake e guarda em st.session_state['covid_df']."""
    session = Session.builder.configs(connection_parameters).create()
    df = session.table(TABLE_NAME).to_pandas()
    session.close()

    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])

    st.session_state["covid_df"] = df
    return df


pagina = st.sidebar.radio(
    "📂 Navegação",
    options=[
        "⬆️ Subir Dados",
        "📊 Dashboard",
        "📄 Baixar Arquivos",
        "🔎 Query SQL",
    ],
)

st.title("🦠 COVID-19 Dashboard")
st.caption("Fonte: Our World in Data • Dados armazenados no Snowflake")


if pagina == "⬆️ Subir Dados":
    st.subheader("⬆️ Subir Dados")
    st.caption(
        "Baixe o CSV mais recente e grave no Snowflake, depois carregue os "
        "dados em memória para visualizar o Dashboard."
    )

    # ---- Botão: Carregar Dados no Snowflake -------------------------------
    if st.button("⬆️ Carregar Dados no Snowflake"):
        with st.spinner("Baixando CSV e enviando ao Snowflake..."):
            # 1) Baixar o CSV
            df = pd.read_csv(CSV_URL)

            # 2) Filtrar países e período para reduzir o volume
            df = df[df["location"].isin(PAISES)]
            df = df[df["date"] >= DATA_INICIAL]

            # 3) Selecionar colunas úteis e tratar nulos
            colunas = [
                "iso_code",
                "continent",
                "location",
                "date",
                "total_cases",
                "new_cases",
                "total_deaths",
                "new_deaths",
                "people_vaccinated",
                "people_fully_vaccinated",
                "population",
            ]
            colunas = [c for c in colunas if c in df.columns]
            df = df[colunas].copy()

            # Normaliza nomes de colunas para MAIÚSCULAS (padrão Snowflake)
            df.columns = [c.upper() for c in df.columns]

            # 4) Conectar e gravar a tabela
            session = Session.builder.configs(connection_parameters).create()
            session.write_pandas(
                df,
                table_name=TABLE_NAME,
                auto_create_table=True,
                overwrite=True,
            )
            session.close()

        # Invalida o cache em memória para que Dashboard/Baixar Arquivos
        # releiam a versão recém-gravada do Snowflake.
        st.session_state.pop("covid_df", None)

        st.success(f"{len(df):,} linhas gravadas em {TABLE_NAME}.")

    st.divider()
    st.caption(f"Atualizado em {datetime.now():%d/%m/%Y %H:%M}")
    st.stop()


if pagina == "🔎 Query SQL":
    st.subheader("🔎 Query SQL")
    st.caption(
        "Execute consultas SELECT direto no Snowflake. "
        f"Tabela disponível: `{connection_parameters['database']}."
        f"{connection_parameters['schema']}.{TABLE_NAME}`"
    )

    query = st.text_area(
        "Digite sua consulta SQL",
        value=f"SELECT * FROM {TABLE_NAME} LIMIT 10",
        height=120,
    )

    if st.button("▶️ Executar Query"):
        # Permite apenas consultas de leitura (SELECT/WITH) para evitar comandos
        # destrutivos acidentais (DROP, DELETE, UPDATE, etc.).
        primeira_palavra = (
            query.strip().lstrip("(").split(None, 1)[0].lower() if query.strip() else ""
        )
        if primeira_palavra not in ("select", "with"):
            st.error("Apenas consultas SELECT/WITH são permitidas.")
        else:
            try:
                with st.spinner("Executando no Snowflake..."):
                    session = Session.builder.configs(connection_parameters).create()
                    resultado = session.sql(query).to_pandas()
                    session.close()
                st.success(f"{len(resultado):,} linhas retornadas.")
                st.dataframe(resultado, use_container_width=True)

                csv_query = resultado.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="⬇️ Exportar resultado (CSV)",
                    data=csv_query,
                    file_name="query_resultado.csv",
                    mime="text/csv",
                )
            except Exception as exc:
                st.error(f"Erro ao executar a query: {exc}")

    st.divider()
    st.caption(f"Atualizado em {datetime.now():%d/%m/%Y %H:%M}")
    st.stop()


if "covid_df" not in st.session_state:
    try:
        with st.spinner("Carregando dados do Snowflake..."):
            carregar_dados()
    except Exception as exc:
        st.error(
            "Não foi possível carregar os dados do Snowflake. "
            "Vá em **⬆️ Subir Dados** e clique em **Carregar Dados no Snowflake** "
            f"primeiro.\n\nDetalhe: {exc}"
        )
        st.stop()

df = st.session_state["covid_df"]

# ---- Filtros interativos ---------------------------------------------------
paises_disponiveis = sorted(df["location"].unique())
paises_sel = st.multiselect(
    "Selecione os países",
    options=paises_disponiveis,
    default=paises_disponiveis,
)

dados = df[df["location"].isin(paises_sel)] if paises_sel else df

COLS_CUMULATIVAS = [
    "total_cases",
    "total_deaths",
    "people_vaccinated",
    "people_fully_vaccinated",
    "population",
]
dados_ff = dados.sort_values("date").copy()
for _col in COLS_CUMULATIVAS:
    if _col in dados_ff.columns:
        dados_ff[_col] = dados_ff.groupby("location")[_col].ffill()

ultimo = dados_ff.groupby("location", as_index=False).tail(1)


if pagina == "📄 Baixar Arquivos":
    st.subheader("📄 Baixar Arquivos")
    st.caption(f"{len(dados):,} linhas para os países selecionados.")
    st.dataframe(dados, use_container_width=True)

    csv = dados.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Exportar CSV",
        data=csv,
        file_name="covid_dados.csv",
        mime="text/csv",
    )

    st.divider()
    st.caption(f"Atualizado em {datetime.now():%d/%m/%Y %H:%M}")
    st.stop()

# ---- Métricas resumo (KPIs) ------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("Total de Casos", f"{int(ultimo['total_cases'].fillna(0).sum()):,}")
col2.metric("Total de Mortes", f"{int(ultimo['total_deaths'].fillna(0).sum()):,}")
col3.metric("Países selecionados", len(paises_sel))

st.divider()

# ---- Visualização 1: Evolução de casos novos ao longo do tempo ------------
st.subheader("1) Evolução de casos novos ao longo do tempo")
# new_cases vem em lotes (muitos zeros + picos semanais), o que faz a linha
# oscilar de 0 ao pico repetidamente, parecendo barras. Aplicamos uma média
# móvel de 7 dias por país para suavizar a curva.
dados_linha = dados.sort_values("date").copy()
dados_linha["new_cases_7d"] = (
    dados_linha.groupby("location")["new_cases"]
    .transform(lambda s: s.rolling(7, min_periods=1).mean())
)
fig1 = px.line(
    dados_linha,
    x="date",
    y="new_cases_7d",
    color="location",
    labels={
        "date": "Data",
        "new_cases_7d": "Novos casos (média 7 dias)",
        "location": "País",
    },
)
st.plotly_chart(fig1, use_container_width=True)

# ---- Visualização 2: Comparação do total de óbitos entre países -----------
st.subheader("2) Total de óbitos por país")
mortes_por_pais = (
    ultimo.groupby("location", as_index=False)["total_deaths"]
    .sum()
    .sort_values("total_deaths", ascending=False)
)
fig2 = px.bar(
    mortes_por_pais,
    x="location",
    y="total_deaths",
    color="location",
    labels={"location": "País", "total_deaths": "Total de óbitos"},
)
st.plotly_chart(fig2, use_container_width=True)

# ---- Visualização 3: Proporção de vacinados (1 dose) por país -------------
st.subheader("3) Proporção de pessoas vacinadas (1 dose) por país")
if "people_vaccinated" in ultimo.columns:
    vacinados = ultimo.dropna(subset=["people_vaccinated"])
    vacinados = vacinados[vacinados["people_vaccinated"] > 0]
    if vacinados.empty:
        st.info("Sem dados de vacinação disponíveis para os países selecionados.")
    else:
        fig3 = px.pie(
            vacinados,
            names="location",
            values="people_vaccinated",
            labels={"location": "País", "people_vaccinated": "Vacinados (1 dose)"},
        )
        st.plotly_chart(fig3, use_container_width=True)

# ---- Visualização 4: Relação entre população e total de casos -------------
st.subheader("4) População vs total de casos")
if "population" in ultimo.columns and "total_cases" in ultimo.columns:
    dados_disp = ultimo.dropna(subset=["population", "total_cases"])
    if dados_disp.empty:
        st.info("Sem dados suficientes para os países selecionados.")
    else:
        fig4 = px.scatter(
            dados_disp,
            x="population",
            y="total_cases",
            color="location",
            hover_name="location",
            labels={
                "population": "População",
                "total_cases": "Total de casos",
                "location": "País",
            },
        )
        st.plotly_chart(fig4, use_container_width=True)

st.divider()
st.caption(f"Atualizado em {datetime.now():%d/%m/%Y %H:%M}")
