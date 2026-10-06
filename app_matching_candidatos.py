import streamlit as st
import pandas as pd
import re
import unicodedata
import io

st.set_page_config(
    page_title="People Analytics - Matching de candidatos",
    page_icon="👥",
    layout="wide"
)

# ============================================================
# NORMALIZACIÓN
# ============================================================

def quitar_tildes(texto):
    if pd.isna(texto):
        return ""
    texto = str(texto)
    texto = unicodedata.normalize("NFD", texto)
    return "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )


def normalizar_texto(texto):
    if pd.isna(texto):
        return ""

    texto = str(texto).upper()
    texto = quitar_tildes(texto)
    texto = re.sub(r"[^A-Z0-9ÑÜ\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()

    return texto


def normalizar_palabra(palabra):
    palabra = normalizar_texto(palabra)

    if not palabra:
        return ""

    palabras = palabra.split()
    resultado = []

    for p in palabras:

        # Plural sencillo
        if len(p) > 4 and p.endswith("ES"):
            p = p[:-2]
        elif len(p) > 4 and p.endswith("S"):
            p = p[:-1]

        # Tratamiento conservador de género
        if len(p) > 5:
            if p.endswith("A"):
                p = p[:-1]
            elif p.endswith("O"):
                p = p[:-1]

        resultado.append(p)

    return " ".join(resultado)


def tokenizar(texto):
    texto = normalizar_texto(texto)
    palabras = texto.split()

    tokens = set()

    for palabra in palabras:
        palabra_norm = normalizar_palabra(palabra)

        if palabra_norm:
            tokens.add(palabra_norm)

    return tokens


# ============================================================
# CARGA DE ARCHIVOS
# ============================================================

def cargar_archivo(uploaded_file):

    if uploaded_file is None:
        return None

    nombre = uploaded_file.name.lower()

    try:

        if nombre.endswith((".xlsx", ".xls")):
            return pd.read_excel(uploaded_file)

        elif nombre.endswith(".csv"):

            try:
                return pd.read_csv(uploaded_file)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                return pd.read_csv(
                    uploaded_file,
                    encoding="latin-1"
                )

        elif nombre.endswith(".txt"):

            contenido = uploaded_file.read()

            try:
                contenido = contenido.decode("utf-8")
            except UnicodeDecodeError:
                contenido = contenido.decode("latin-1")

            lineas = [
                linea.strip()
                for linea in contenido.splitlines()
                if linea.strip()
            ]

            return pd.DataFrame({"TAG": lineas})

    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return None

    return None


# ============================================================
# TAGS
# ============================================================

def obtener_tags(df):

    if df is None or df.empty:
        return []

    columnas = list(df.columns)

    posibles = [
        "TAG",
        "TAGS",
        "PALABRA",
        "PALABRAS",
        "KEYWORD",
        "KEYWORDS",
        "PALABRA CLAVE",
        "PALABRAS CLAVE"
    ]

    columna = None

    for c in columnas:
        if str(c).strip().upper() in posibles:
            columna = c
            break

    if columna is None:
        columna = columnas[0]

    tags = (
        df[columna]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    return list(dict.fromkeys(tags))


def preparar_tags(tags):

    resultado = {}

    for tag in tags:

        palabras = tokenizar(tag)

        if palabras:
            resultado[tag] = palabras

    return resultado


# ============================================================
# MATCHING
# ============================================================

def encontrar_coincidencias(
    texto_cv,
    tags_seleccionados,
    pesos,
    obligatorios
):

    tokens_cv = tokenizar(texto_cv)

    coincidencias = []
    puntuacion = 0
    puntuacion_maxima = 0
    faltan_obligatorios = []

    tags_normalizados = preparar_tags(
        tags_seleccionados
    )

    for tag in tags_seleccionados:

        palabras_tag = tags_normalizados[tag]
        peso = pesos.get(tag, 1)

        puntuacion_maxima += peso

        palabras_encontradas = (
            palabras_tag.intersection(tokens_cv)
        )

        if palabras_encontradas:
            coincidencias.append(tag)
            puntuacion += peso

        elif tag in obligatorios:
            faltan_obligatorios.append(tag)

    porcentaje = (
        puntuacion / puntuacion_maxima * 100
        if puntuacion_maxima > 0
        else 0
    )

    return {
        "coincidencias": len(coincidencias),
        "puntuacion": puntuacion,
        "puntuacion_maxima": puntuacion_maxima,
        "porcentaje": porcentaje,
        "tags_encontrados": coincidencias,
        "faltan_obligatorios": faltan_obligatorios
    }


def procesar_candidatos(
    df_candidatos,
    columnas_cv,
    columna_id,
    columna_nombre,
    tags_seleccionados,
    pesos,
    obligatorios,
    minimo_coincidencias
):

    resultados = []

    for indice, fila in df_candidatos.iterrows():

        candidato_id = (
            fila[columna_id]
            if columna_id
            else indice + 1
        )

        nombre = (
            fila[columna_nombre]
            if columna_nombre
            else f"Candidato {indice + 1}"
        )

        partes_texto = []

        for columna in columnas_cv:

            valor = fila[columna]

            if pd.notna(valor):
                partes_texto.append(str(valor))

        texto_cv = " ".join(partes_texto)

        resultado = encontrar_coincidencias(
            texto_cv,
            tags_seleccionados,
            pesos,
            obligatorios
        )

        if resultado["coincidencias"] < minimo_coincidencias:
            continue

        if resultado["faltan_obligatorios"]:
            continue

        resultados.append({
            "ID": candidato_id,
            "Candidato": nombre,
            "Coincidencias": resultado["coincidencias"],
            "Puntuación": resultado["puntuacion"],
            "Puntuación máxima": resultado["puntuacion_maxima"],
            "% Ajuste": resultado["porcentaje"],
            "TAGS encontrados": ", ".join(
                resultado["tags_encontrados"]
            ),
            "TAGS obligatorios faltantes": ", ".join(
                resultado["faltan_obligatorios"]
            )
        })

    if not resultados:
        return pd.DataFrame()

    df_resultados = pd.DataFrame(resultados)

    df_resultados = df_resultados.sort_values(
        by=[
            "Puntuación",
            "Coincidencias",
            "% Ajuste"
        ],
        ascending=False
    )

    df_resultados.insert(
        0,
        "Ranking",
        range(1, len(df_resultados) + 1)
    )

    return df_resultados


def dataframe_a_excel(df):

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Ranking"
        )

    return output.getvalue()


# ============================================================
# INTERFAZ
# ============================================================

st.title("👥 People Analytics - Matching de candidatos")

st.write(
    "Sistema de matching de candidatos mediante palabras clave "
    "entre la descripción de un puesto y los currículums."
)

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Configuración")

    minimo_coincidencias = st.number_input(
        "Mínimo de coincidencias",
        min_value=1,
        max_value=50,
        value=2
    )

    max_candidatos = st.number_input(
        "Máximo de candidatos",
        min_value=1,
        max_value=1000,
        value=20
    )

# ============================================================
# PUESTOS
# ============================================================

st.header("1️⃣ Fichero de descripción de puestos")

archivo_tags = st.file_uploader(
    "Carga el Excel, CSV o TXT con los TAGS",
    type=["xlsx", "xls", "csv", "txt"],
    key="tags"
)

df_tags = None
tags_disponibles = []

if archivo_tags:

    df_tags = cargar_archivo(
        archivo_tags
    )

    if df_tags is not None:

        tags_disponibles = obtener_tags(
            df_tags
        )

        st.success(
            f"Se han encontrado {len(tags_disponibles)} TAGS."
        )

        with st.expander("Ver TAGS"):
            st.write(tags_disponibles)

# ============================================================
# CANDIDATOS
# ============================================================

st.header("2️⃣ Fichero de candidatos")

archivo_cvs = st.file_uploader(
    "Carga el Excel o CSV con los candidatos",
    type=["xlsx", "xls", "csv"],
    key="cvs"
)

df_candidatos = None

if archivo_cvs:

    df_candidatos = cargar_archivo(
        archivo_cvs
    )

    if df_candidatos is not None:

        st.success(
            f"Se han cargado {len(df_candidatos)} candidatos."
        )

# ============================================================
# CONFIGURACIÓN CANDIDATOS
# ============================================================

if df_candidatos is not None:

    st.header("3️⃣ Configuración de candidatos")

    columnas = list(df_candidatos.columns)

    col1, col2 = st.columns(2)

    with col1:

        columna_id = st.selectbox(
            "Identificador del candidato",
            ["-- Ninguna --"] + columnas
        )

    with col2:

        columna_nombre = st.selectbox(
            "Nombre del candidato",
            ["-- Ninguna --"] + columnas
        )

    if columna_id == "-- Ninguna --":
        columna_id = None

    if columna_nombre == "-- Ninguna --":
        columna_nombre = None

    columnas_cv = st.multiselect(
        "Columnas que contienen información del CV",
        columnas,
        default=columnas
    )

# ============================================================
# SELECCIÓN TAGS
# ============================================================

if tags_disponibles:

    st.header("4️⃣ Selección de TAGS")

    tags_seleccionados = st.multiselect(
        "Selecciona las palabras clave",
        tags_disponibles
    )

    if tags_seleccionados:

        st.subheader("⚖️ Ponderación")

        pesos = {}
        obligatorios = []

        for i, tag in enumerate(tags_seleccionados):

            col1, col2, col3 = st.columns([3, 2, 2])

            with col1:
                st.write(tag)

            with col2:

                importancia = st.selectbox(
                    "Importancia",
                    [
                        "Deseable",
                        "Importante",
                        "Muy importante"
                    ],
                    key=f"peso_{i}",
                    label_visibility="collapsed"
                )

            if importancia == "Deseable":
                pesos[tag] = 1
            elif importancia == "Importante":
                pesos[tag] = 2
            else:
                pesos[tag] = 3

            with col3:

                obligatorio = st.checkbox(
                    "Obligatorio",
                    key=f"obligatorio_{i}"
                )

                if obligatorio:
                    obligatorios.append(tag)

# ============================================================
# EJECUCIÓN
# ============================================================

if (
    df_candidatos is not None
    and tags_disponibles
    and "tags_seleccionados" in locals()
    and tags_seleccionados
    and columnas_cv
):

    st.header("5️⃣ Ejecutar matching")

    if st.button(
        "🔍 BUSCAR Y CREAR RANKING",
        type="primary",
        use_container_width=True
    ):

        with st.spinner(
            "Analizando los currículums..."
        ):

            resultados = procesar_candidatos(
                df_candidatos,
                columnas_cv,
                columna_id,
                columna_nombre,
                tags_seleccionados,
                pesos,
                obligatorios,
                minimo_coincidencias
            )

        st.header("6️⃣ Ranking de candidatos")

        if resultados.empty:

            st.warning(
                "No se han encontrado candidatos que cumplan "
                "los criterios establecidos."
            )

        else:

            resultados_top = resultados.head(
                max_candidatos
            ).copy()

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "Candidatos analizados",
                    len(df_candidatos)
                )

            with col2:
                st.metric(
                    "Candidatos que cumplen",
                    len(resultados)
                )

            with col3:
                st.metric(
                    "Candidatos mostrados",
                    len(resultados_top)
                )

            st.dataframe(
                resultados_top,
                use_container_width=True,
                hide_index=True
            )

            # ==================================================
            # MEJOR CANDIDATO
            # ==================================================

            mejor = resultados_top.iloc[0]

            st.subheader("🥇 Mayor puntuación")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "Candidato",
                    str(mejor["Candidato"])
                )

            with col2:
                st.metric(
                    "Coincidencias",
                    int(mejor["Coincidencias"])
                )

            with col3:
                st.metric(
                    "Score",
                    f'{mejor["Puntuación"]:.0f}'
                )

            st.write("**TAGS encontrados:**")
            st.success(
                mejor["TAGS encontrados"]
            )

            # ==================================================
            # DESCARGAS
            # ==================================================

            st.subheader("📥 Descargar resultados")

            col1, col2 = st.columns(2)

            with col1:

                excel = dataframe_a_excel(
                    resultados_top
                )

                st.download_button(
                    "📊 Descargar Excel",
                    data=excel,
                    file_name="ranking_candidatos.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    use_container_width=True
                )

            with col2:

                csv = resultados_top.to_csv(
                    index=False,
                    encoding="utf-8-sig"
                )

                st.download_button(
                    "📄 Descargar CSV",
                    data=csv,
                    file_name="ranking_candidatos.csv",
                    mime="text/csv",
                    use_container_width=True
                )

# ============================================================
# INFORMACIÓN
# ============================================================

with st.expander("ℹ️ Cómo funciona"):

    st.markdown("""
    ### Proceso

    **1. Normalización**

    Se convierten los textos a mayúsculas y se eliminan las tildes.

    **2. Tratamiento lingüístico**

    Se realizan ajustes básicos para tratar de forma equivalente
    determinadas variantes de género y plural.

    **3. Matching**

    Se comparan las palabras del CV con los TAGS seleccionados.

    **4. Ponderación**

    - Deseable = 1 punto
    - Importante = 2 puntos
    - Muy importante = 3 puntos

    **5. TAG obligatorio**

    Si un TAG está marcado como obligatorio y no aparece en el CV,
    el candidato queda excluido.

    **6. Ranking**

    Los candidatos se ordenan por puntuación ponderada y número
    de coincidencias.

    **Importante:** el resultado representa un grado de coincidencia
    con los criterios definidos, no una decisión automática de contratación.
    """)

