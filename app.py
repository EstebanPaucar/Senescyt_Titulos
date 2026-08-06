import io
import streamlit as st
import pandas as pd
from core.scraper import procesar_excel_completo
from core.merger import unificar_excels_docentes
import os

@st.cache_resource
def instalar_navegadores():
    os.system("playwright install chromium")
    os.system("playwright install-deps chromium")

# Ejecutamos la instalación de forma invisible al arrancar
instalar_navegadores()

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
    st.caption("🚀 Arquitectura Scalable para +1,000 Docentes | Motor Playwright + Tesseract OCR")

# =====================================================================
# CREACIÓN DE LAS 3 PESTAÑAS ESTRUCTURALES
# =====================================================================
pestaña_scraping, pestaña_unificacion, pestaña_ia = st.tabs([
    "🔍 1. Extracción SENESCYT (Scraping)", 
    "🔗 2. Consolidación (Títulos + Materias)", 
    "🤖 3. Auditoría por IA (Fase 2)"
])

# =====================================================================
# PESTAÑA 1: MOTOR DE SCRAPING SENESCYT 
# =====================================================================
with pestaña_scraping:
    st.subheader("Extracción Estructural de Títulos (3er y 4to Nivel)")
    st.write("Sube la plantilla con las cédulas en la **Columna C (desde fila 3)**. El sistema leerá el portal gubernamental por contenedores HTML (`div.panel`) y evitará colisiones de texto.")
    
    col_izq, col_der = st.columns([1, 1])
    with col_izq:
        archivo_scraping = st.file_uploader(
            "📥 Subir Excel Plantilla (Con Cédulas en Col C)", 
            type=["xlsx"], 
            key="uplo_scraping"
        )
    with col_der:
        st.markdown("#### Configuración de Ejecución")
        ver_nav = st.checkbox("👁️ Ver navegador en tiempo (Modo Visual Slow-Mo)", value=False)
        forzar_cache = st.checkbox("🔄 Forzar re-evaluación en web (Ignorar Caché del disco)", value=False)
        
    if archivo_scraping is not None:
        st.markdown("---")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            btn_normal = st.button("🚀 Iniciar Extracción Oficial SENESCYT", key="btn_ejecutar_scraping", type="primary", use_container_width=True)
        with col_btn2:
            btn_reverificar = st.button("🔄 Reverificar solo 'No registra'", key="btn_reverificar", type="secondary", use_container_width=True)
            
        if btn_normal or btn_reverificar:
            es_modo_reverificacion = True if btn_reverificar else False
            
            if es_modo_reverificacion:
                st.info("💡 **Modo Reverificar activo:** Se saltarán instantáneamente los docentes que ya tengan títulos y solo se consultará en vivo a los pendientes ('No registra').")
            
            # --- CONSOLA DE LOGS EN UI ---
            st.markdown("#### 🖥️ Consola de Ejecución en Vivo")
            consola_ui = st.empty()
            
            if 'historial_logs' not in st.session_state:
                st.session_state.historial_logs = []
            st.session_state.historial_logs.clear()
            
            def registrar_log(mensaje):
                """Añade el log al estado y actualiza el contenedor de código"""
                st.session_state.historial_logs.append(f"> {mensaje}")
                # Mostramos solo los últimos 15 mensajes para que no se sature la pantalla
                consola_ui.code('\n'.join(st.session_state.historial_logs[-15:]), language='bash')
            
            cont_barra = st.empty()
            barra_progreso = cont_barra.progress(0.0, text="Iniciando Chromium y Tesseract OCR...")
            
            def actualizar_ui(porcentaje, texto):
                barra_progreso.progress(min(porcentaje, 1.0), text=texto)
            
            try:
                # OJO: Aquí pasamos registrar_log como log_callback
                bytes_resultado, cache_actualizada = procesar_excel_completo(
                    archivo_bytes=archivo_scraping.getvalue(),
                    progress_callback=actualizar_ui,
                    log_callback=registrar_log,
                    forzar_reevaluacion=forzar_cache,
                    ver_navegador=ver_nav,
                    reverificar_no_registra=es_modo_reverificacion
                )
                
                cont_barra.empty()
                st.success("✅ ¡Extracción completada con éxito! Los títulos oficiales se inyectaron en las columnas F y G.")
                
                st.download_button(
                    label="📥 Descargar Excel Auditado (Títulos Extraídos)",
                    data=bytes_resultado,
                    file_name="1_Titulos_SENESCYT_Extraidos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
            except Exception as e:
                cont_barra.empty()
                st.error(f"❌ Ocurrió un error en la extracción: {str(e)}")
                registrar_log(f"ERROR CRÍTICO: {str(e)}")
    else:
        st.info("👆 Sube tu archivo Excel en el recuadro superior para activar el motor de scraping.")

# =====================================================================
# PESTAÑA 2: CRUCE RELACIONAL Y EXPANSIÓN DE FILAS (MERGER)
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
# PESTAÑA 3: CEREBRO ANALÍTICO (FASE 2 - ACTIVA)
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