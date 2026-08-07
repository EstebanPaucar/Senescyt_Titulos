import io
import streamlit as st
import pandas as pd
from core.merger import unificar_excels_docentes
import os
from github import Github

# --- INYECCIÓN PARA GITHUB ACTIONS ---
try:
    GH_TOKEN = st.secrets.get("GITHUB_TOKEN", None)
    REPO_NAME = st.secrets.get("REPO_NAME", None)
except Exception:
    GH_TOKEN = None
    REPO_NAME = None

def subir_a_github(archivo_bytes, ruta_destino, mensaje_commit):
    g = Github(GH_TOKEN)
    repo = g.get_repo(REPO_NAME)
    try:
        contents = repo.get_contents(ruta_destino)
        repo.update_file(contents.path, mensaje_commit, archivo_bytes, contents.sha)
    except Exception:
        repo.create_file(ruta_destino, mensaje_commit, archivo_bytes)

def descargar_de_github(ruta_origen):
    g = Github(GH_TOKEN)
    repo = g.get_repo(REPO_NAME)
    contents = repo.get_contents(ruta_origen)
    return contents.decoded_content
# -------------------------------------

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Sistema de Auditoría Docente - LOES / SENESCYT",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ENCABEZADO INSTITUCIONAL ---
st.title("🏛️ Sistema Integral de Auditoría y Validación Docente")
st.markdown("---")

# --- BARRA LATERAL (INSTRUCCIONES / METRICS) ---
with st.sidebar:
    st.header("⚙️ Panel de Control")
    st.info("""
    **Flujo del Pipeline Académico:**
    1. **Scraping:** Consulta oficial en el portal SENESCYT (Aislamiento DOM sin Regex).
    2. **Unificación:** Cruce relacional 1 a N (Docente x Materia asignada).
    3. **Evaluación IA:** Análisis curricular técnico con IA.
    """)
    st.markdown("---")
    st.caption("🚀 Arquitectura Scalable para +1,000 Docentes | Motor GitHub Actions (5 Hilos)")

# =====================================================================
# CREACIÓN DE LAS 3 PESTAÑAS ESTRUCTURALES
# =====================================================================
pestaña_scraping, pestaña_unificacion, pestaña_ia = st.tabs([
    "🔍 1. Extracción SENESCYT (Scraping)", 
    "🔗 2. Consolidación (Títulos + Materias)", 
    "🤖 3. Auditoría por IA (Fase 2)"
])

# =====================================================================
# PESTAÑA 1: MOTOR DE SCRAPING SENESCYT (VERSIÓN NUBE)
# =====================================================================
with pestaña_scraping:
    st.subheader("Extracción Estructural de Títulos (3er y 4to Nivel) - Motor CI/CD")
    st.write("Sube la plantilla. El servidor de GitHub encenderá 5 hilos asíncronos para extraer los títulos sin consumir la memoria de tu aplicación.")
    
    if not GH_TOKEN or not REPO_NAME:
        st.error("⚠️ Faltan configurar GITHUB_TOKEN y REPO_NAME en los secretos de Streamlit (st.secrets). El motor de scraping remoto no funcionará.")
    
    archivo_scraping = st.file_uploader(
        "📥 1. Subir Excel Plantilla (Con Cédulas en Col C)", 
        type=["xlsx"], 
        key="uplo_scraping"
    )

    if archivo_scraping is not None:
        if st.button("🚀 Enviar al Servidor de GitHub (5 Hilos)", key="btn_ejecutar_scraping", type="primary"):
            with st.spinner("Inyectando archivo en la cola de procesamiento..."):
                try:
                    subir_a_github(archivo_scraping.getvalue(), "inputs/matriz_a_procesar.xlsx", "⏳ Nuevo lote de docentes subido por Streamlit")
                    st.success("✅ ¡Archivo enviado exitosamente!")
                    st.info("💡 El servidor de GitHub ya está trabajando en segundo plano. Ve a la pestaña 'Actions' de tu repositorio para ver el progreso.")
                except Exception as e:
                    st.error(f"❌ Error al enviar el archivo a GitHub: {e}")

    st.markdown("---")
    st.subheader("📥 2. Recuperar Resultados")
    
    if st.button("🔄 Comprobar y Descargar Resultados", key="btn_recuperar"):
        with st.spinner("Buscando el archivo procesado en el servidor..."):
            try:
                bytes_resultado = descargar_de_github("outputs/matriz_procesada.xlsx")
                st.success("✅ ¡Archivo recuperado con éxito!")
                st.download_button(
                    label="📥 Descargar Excel Auditado (Títulos Extraídos)",
                    data=bytes_resultado,
                    file_name="1_Titulos_SENESCYT_Extraidos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
            except Exception:
                st.warning("⏳ El archivo aún no está listo o el servidor sigue procesándolo. Espera unos minutos e intenta de nuevo.")

# =====================================================================
# PESTAÑA 2: CRUCE RELACIONAL Y EXPANSIÓN DE FILAS (MERGER) - [INTACTA]
# =====================================================================
with pestaña_unificacion:
    st.subheader("Consolidación Relacional (Expansión de 1 a Muchos)")
    st.write("""
    Este módulo toma el Excel de títulos y el Excel de materias, normaliza las cédulas a 10 dígitos y realiza una unión exacta. 
    **Si un docente imparte 3 materias, el sistema genera automáticamente 3 filas** (repitiendo sus datos y títulos) y asignando cada materia a la **Columna H**.
    """)
    
    col_t, col_m = st.columns(2)
    with col_t:
        excel_1_titulos = st.file_uploader(
            "📥 1. Subir Excel de Títulos (Salida del Paso 1)", 
            type=["xlsx"], 
            key="uplo_titulos"
        )
    with col_m:
        excel_2_materias = st.file_uploader(
            "📥 2. Subir Excel de Carga Horaria (Col L, M, N)", 
            type=["xlsx"], 
            key="uplo_materias"
        )
        
    if excel_1_titulos and excel_2_materias:
        st.markdown("---")
        if st.button("🔗 Cruce Relacional y Generar Matriz Maestra", key="btn_merger", type="primary"):
            with st.spinner("Normalizando cédulas, procesando celdas combinadas y expandiendo filas..."):
                try:
                    bytes_unificado = unificar_excels_docentes(
                        bytes_excel_titulos=excel_1_titulos.getvalue(),
                        bytes_excel_materias=excel_2_materias.getvalue()
                    )
                    
                    st.success("✅ ¡Unificación exitosa! Las columnas H (Materia), I (Obs. IA) y J (Análisis Técnico) están listas.")
                    
                    st.markdown("#### 👀 Vista Previa de la Matriz Auditada (Primeras 15 filas generadas)")
                    df_preview = pd.read_excel(io.BytesIO(bytes_unificado), skiprows=1)
                    st.dataframe(df_preview.head(15), use_container_width=True)
                    
                    st.download_button(
                        label="📥 Descargar Matriz Maestra Unificada (Lista para IA)",
                        data=bytes_unificado,
                        file_name="2_Distributivo_Unificado_Maestro.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"❌ Error al unificar los archivos: {str(e)}")
    else:
        st.warning("⚠️ Debes subir **ambos** archivos Excel en los recuadros de arriba para poder realizar el cruce relacional.")

# =====================================================================
# PESTAÑA 3: CEREBRO ANALÍTICO (FASE 2 - ACTIVA) - [INTACTA]
# =====================================================================
with pestaña_ia:
    from core.evaluator import evaluar_matriz_completa_ia
    
    st.subheader("Evaluación de Idoneidad Académica por Inteligencia Artificial")
    st.write("Sube el archivo unificado (**Salida de la Pestaña 2**). El sistema evaluará automáticamente la compatibilidad entre los títulos y las asignaturas aplicando criterios de afinidad LOES/CES.")
    
    col_ia1, col_ia2 = st.columns([1, 1])
    with col_ia1:
        excel_para_ia = st.file_uploader(
            "📥 Subir Excel Unificado (Distributivo Maestro)", 
            type=["xlsx"], 
            key="uplo_ia_final"
        )
    with col_ia2:
        st.markdown("#### Estado del Motor de Auditoría")
        
        try:
            api_key_input = st.secrets.get("OPENAI_API_KEY", None)
        except Exception:
            api_key_input = None
            
        modelo_select = "gpt-4o-mini"
        
        if api_key_input:
            st.success("🟢 Motor de Inteligencia Artificial conectado y asegurado.")
        else:
            st.error("🔴 Error: Motor IA desconectado. Contacte al administrador.")

    if excel_para_ia is not None:
        st.markdown("---")
        if not api_key_input:
            st.error("⚠️ Error Interno del Servidor: La API Key no ha sido configurada por el administrador en los secretos (st.secrets).")
        else:
            if st.button("🤖 Iniciar Auditoría Curricular con IA", key="btn_ejecutar_ia", type="primary"):
                
                cont_barra_ia = st.empty()
                barra_ia = cont_barra_ia.progress(0.0, text="Conectando con la API protegida...")
                
                def actualizar_ui_ia(porz, txt):
                    barra_ia.progress(min(porz, 1.0), text=txt)
                    
                try:
                    bytes_auditados = evaluar_matriz_completa_ia(
                        archivo_bytes=excel_para_ia.getvalue(),
                        api_key=api_key_input,
                        progress_callback=actualizar_ui_ia,
                        modelo_nombre=modelo_select
                    )
                    
                    cont_barra_ia.empty()
                    st.success("✅ ¡Auditoría Académica Completada! Se ha evaluado cada docente y sus materias con éxito.")
                    
                    df_resumen_ia = pd.read_excel(io.BytesIO(bytes_auditados), skiprows=1)
                    st.markdown("#### 👀 Vista Previa del Dictamen IA")
                    st.dataframe(df_resumen_ia[['Cédula', 'Nombres y Apellidos', 'Materia Asignada (Col H)', 'Observación IA (Col I)', 'Análisis Técnico (Col J)']].head(15), use_container_width=True)
                    
                    st.download_button(
                        label="📥 Descargar Distributivo Auditado por IA (Reporte Final)",
                        data=bytes_auditados,
                        file_name="3_Distributivo_Auditado_IA_Final.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                except Exception as e:
                    cont_barra_ia.empty()
                    st.error(f"❌ Ocurrió un error en la evaluación con IA: {str(e)}")
    else:
        st.info("👆 Sube tu Excel Unificado (`2_Distributivo_Unificado_Maestro.xlsx`) en el recuadro de arriba para procesarlo.")