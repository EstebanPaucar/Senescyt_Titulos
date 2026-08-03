import time
import random
import io
import os
import json
from collections import Counter
import openpyxl
import cv2
import pytesseract
from PIL import Image
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# --- 1. PARCHE CRÍTICO PARA WINDOWS + STREAMLIT + PLAYWRIGHT ---
import asyncio
import sys
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
# ---------------------------------------------------------------

# RUTA TESSERACT: Verifica tu instalación local en Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ARCHIVO DE CACHÉ LOCAL
ARCHIVO_CACHE = "historial_auditorias.json"

def cargar_cache():
    if os.path.exists(ARCHIVO_CACHE):
        try:
            with open(ARCHIVO_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Error leyendo caché: {e}. Se iniciará caché vacía.")
            return {}
    return {}

def guardar_cache(data_cache):
    try:
        with open(ARCHIVO_CACHE, "w", encoding="utf-8") as f:
            json.dump(data_cache, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[!] No se pudo guardar el historial: {e}")

def resolver_captcha(ruta_imagen):
    """
    Versión Reforzada: Limpieza de ruido avanzada (Denoising) + Morfología
    para máxima precisión de Tesseract en CAPTCHAs de SENESCYT.
    """
    try:
        # 1. Cargar en escala de grises
        img = cv2.imread(ruta_imagen, cv2.IMREAD_GRAYSCALE)
        
        # 2. Upscaling x3.0 (Más grande para que Tesseract distinga mejor los bordes)
        img_agrandada = cv2.resize(img, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        
        # 3. Denoising Avanzado: Elimina los puntos de fondo del SENESCYT sin difuminar las letras
        img_limpia = cv2.fastNlMeansDenoising(img_agrandada, None, h=15, templateWindowSize=7, searchWindowSize=21)
        
        # 4. Inversión y Binarización Otsu
        img_invertida = cv2.bitwise_not(img_limpia)
        _, img_bin = cv2.threshold(img_invertida, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 5. Morfología (Cierre): Engrosa ligeramente los trazos de las letras si están rotos o delgados
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        img_morf = cv2.morphologyEx(img_bin, cv2.MORPH_CLOSE, kernel)
        
        # Guardamos la imagen procesada en disco para auditoría visual
        cv2.imwrite("captcha_procesado.png", img_morf)
        
        # 6. Configuración Tesseract: PSM 7 (Línea de texto simple) supera a PSM 8 en este portal
        config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        texto = pytesseract.image_to_string(Image.open("captcha_procesado.png"), config=config)
        
        # Limpieza estricta: nos quedamos solo con letras y números reales
        texto_limpio = "".join(filter(str.isalnum, texto.strip()))
        return texto_limpio
    except Exception as e:
        print(f"[!] Error en visión artificial OpenCV/Tesseract: {e}")
        return ""

def consultar_senescyt_web(page, cedula):
    """
    Navega con Playwright, extrae por ESTRUCTURA HTML PURA (Cero Regex en títulos)
    y valida por CONSENSO. Respeto absoluto a los paneles del SENESCYT.
    """
    muestras_obtenidas = []
    intentos_navegacion = 0
    max_intentos_navegacion = 6
    
    print(f"\n==========================================================")
    print(f"--> [AUDITORÍA ESTRUCTURAL INICIADA] Cédula: {cedula}")
    print(f"==========================================================")
    
    while len(muestras_obtenidas) < 3 and intentos_navegacion < max_intentos_navegacion:
        intentos_navegacion += 1
        print(f"\n[Muestra {len(muestras_obtenidas)+1}/3 | Intento {intentos_navegacion}/{max_intentos_navegacion}] Conectando al portal...")
        
        try:
            page.goto("https://www.senescyt.gob.ec/web/guest/consultas", timeout=60000)
            page.wait_for_load_state('networkidle')
            
            # 1. LIMPIEZA FORZADA DE MODALES / POP-UPS
            try:
                selector_cierre = 'a.ui-dialog-titlebar-close, span.ui-icon-closethick'
                if page.locator(selector_cierre).first.is_visible(timeout=2000):
                    page.locator(selector_cierre).first.click()
                    print("    [LOG-UI] Pop-up institucional cerrado mediante clic.")
            except:
                pass
            finally:
                try:
                    page.evaluate("""
                        document.querySelectorAll('.ui-dialog, .ui-widget-overlay').forEach(el => el.remove());
                        document.body.classList.remove('ui-overflow-hidden');
                    """)
                except:
                    pass
            
            # 2. INGRESO Y VALIDACIÓN DE CÉDULA EN EL INPUT
            selector_cedula = 'input[id="formPrincipal:identificacion"]'
            page.wait_for_selector(selector_cedula, state="visible", timeout=5000)
            page.locator(selector_cedula).click()
            page.locator(selector_cedula).clear()
            page.locator(selector_cedula).press_sequentially(cedula, delay=80)
            
            if page.locator(selector_cedula).input_value() != cedula:
                print("    [LOG-WARN] El campo de cédula perdió el foco. Forzando re-llenado...")
                page.locator(selector_cedula).fill(cedula)
                if page.locator(selector_cedula).input_value() != cedula:
                    continue
            print("    [LOG-INPUT] Cédula confirmada en el DOM del navegador.")

            # 3. RESOLUCIÓN DE CAPTCHA POR VISIÓN ARTIFICIAL
            selector_img_captcha = 'img[id="formPrincipal:capimg"]'
            page.locator(selector_img_captcha).screenshot(path="captcha_temp.png")
            texto_captcha = resolver_captcha("captcha_temp.png")
            
            print(f"    [LOG-OCR] Tesseract procesó la imagen -> Lectura: '{texto_captcha}'")
            
            # 👉 ESCUDO LOCAL ANTI-BAN: Los CAPTCHAs de SENESCYT tienen estrictamente entre 4 y 5 caracteres.
            # Si Tesseract lee menos de 4 o más de 6, lo descartamos localmente sin provocar al servidor.
            if not texto_captcha or len(texto_captcha) < 4 or len(texto_captcha) > 6:
                print(f"    [LOG-ERR] Lectura dudosa ({len(texto_captcha)} caracteres: '{texto_captcha}'). Descartando localmente para evitar bloqueo...")
                time.sleep(1.2) # Pequeña pausa local
                continue
                
            selector_input_captcha = 'input[id="formPrincipal:captchaSellerInput"]'
            page.locator(selector_input_captcha).fill(texto_captcha)
            if page.locator(selector_input_captcha).input_value() != texto_captcha:
                page.locator(selector_input_captcha).fill(texto_captcha)

            # 4. ENVÍO DEL FORMULARIO Y AUDITORÍA DE RESPUESTA AJAX
            selector_boton = 'button[id="formPrincipal:boton-buscar"]'
            page.wait_for_selector(f'{selector_boton}:not([disabled])', timeout=5000)
            print("    [LOG-ACCIÓN] Enviando formulario (Clic en botón 'Buscar')...")
            page.click(selector_boton)
            
            print("    [LOG-ESPERA] Analizando respuesta del servidor SENESCYT tras validación...")
            
            tiempo_inicio = time.time()
            tabla_encontrada = False
            estado_servidor = "DESCONOCIDO"
            
            # Bucle de espera de 9.5 segundos adaptado al tráfico de la web
            while time.time() - tiempo_inicio < 9.5:
                contenido_html = page.content().lower()
                
                # ¿Aparecieron las tablas con los datos?
                if page.locator('tbody.ui-datatable-data').count() > 0 and page.locator('tbody.ui-datatable-data').first.is_visible():
                    tabla_encontrada = True
                    estado_servidor = "TABLAS_CARGADAS"
                    break
                
                # Búsqueda rápida en texto puro de rechazo de CAPTCHA
                if any(x in contenido_html for x in ["código de seguridad incorrecto", "código incorrecto", "captcha incorrecto", "texto de la imagen"]):
                    estado_servidor = "ERROR_GOBIERNO: 'CAPTCHA rechazado por el servidor'"
                    break
                    
                # Capturamos también las notificaciones flotantes (ui-growl-message)
                if page.locator('.ui-messages-error, .ui-message-error, .ui-growl-message').count() > 0:
                    msj_error = page.locator('.ui-messages-error, .ui-message-error, .ui-growl-message').first.inner_text().strip().replace('\n', ' - ')
                    if msj_error:
                        estado_servidor = f"ERROR_GOBIERNO: '{msj_error}'"
                        break
                
                # ¿Confirmación oficial de que no cuenta con títulos?
                if any(x in contenido_html for x in ["no se encontr", "sin registro", "ningún registro"]):
                    tabla_encontrada = True
                    estado_servidor = "CONFIRMADO_SIN_REGISTROS"
                    break
                    
                time.sleep(0.3)
            
            print(f"    [LOG-DIAGNÓSTICO] Resultado de validación -> Estado: {estado_servidor}")
            
            if not tabla_encontrada and "ERROR_GOBIERNO" in estado_servidor:
                print("    [LOG-REINICIO] El servidor rechazó el CAPTCHA. Enfriando 3 segundos para evitar ban del firewall...")
                time.sleep(3.0) # 👉 PAUSA ANTI-FIREWALL: Evita el Timeout de 60 segundos
                continue
            elif not tabla_encontrada:
                print("    [LOG-REINICIO] Tiempo de espera agotado sin respuesta clara de PrimeFaces AJAX. Reintentando...")
                continue
                
            # ==========================================================
            # 5. EXTRACCIÓN ESTRUCTURAL PURA (CERO REGEX)
            # ==========================================================
            print("    [LOG-BS4] Extrayendo por aislamiento de contenedores (Paneles DOM)...")
            time.sleep(1.2) # Pausa para renderizado completo de AJAX
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            titulos_tercer = []
            titulos_cuarto = []
            
            encabezados_panel = soup.find_all('h4', class_='panel-title')
            print(f"    [LOG-BS4] Se detectaron {len(encabezados_panel)} paneles de títulos en la página.")
            
            for encabezado in encabezados_panel:
                texto_encabezado = encabezado.get_text(strip=True).lower()
                
                panel_padre = encabezado.find_parent('div', class_='panel')
                if not panel_padre:
                    tbody = encabezado.find_next('tbody', class_='ui-datatable-data')
                else:
                    tbody = panel_padre.find('tbody', class_='ui-datatable-data')
                
                if not tbody:
                    continue
                
                filas = tbody.find_all('tr')
                titulos_del_panel = []
                
                for fila in filas:
                    celdas = fila.find_all('td')
                    if celdas and len(celdas) >= 1:
                        celda_titulo = celdas[0]
                        
                        span_responsive = celda_titulo.find('span', class_='ui-column-title')
                        if span_responsive:
                            span_responsive.decompose()
                            
                        titulo_puro = celda_titulo.get_text(separator=' ', strip=True)
                        
                        if titulo_puro and not any(x in titulo_puro.lower() for x in ["no se encontr", "ningún", "sin registro"]):
                            if titulo_puro not in titulos_del_panel:
                                titulos_del_panel.append(titulo_puro)
                
                if "cuarto nivel" in texto_encabezado or "posgrado" in texto_encabezado:
                    for t in titulos_del_panel:
                        if t not in titulos_cuarto:
                            titulos_cuarto.append(t)
                elif "tercer nivel" in texto_encabezado or "grado" in texto_encabezado:
                    for t in titulos_del_panel:
                        if t not in titulos_tercer:
                            titulos_tercer.append(t)
            
            if not titulos_tercer and not titulos_cuarto:
                texto_pagina_completa = soup.get_text().lower()
                if "no se encontr" not in texto_pagina_completa and "ningún" not in texto_pagina_completa:
                    print("    [LOG-ALERTA] Tablas vacías pero falta confirmación oficial 'No registra'. Fallo AJAX.")
                    continue
            
            texto_3er = " | ".join(titulos_tercer) if titulos_tercer else "No registra"
            texto_4to = " | ".join(titulos_cuarto) if titulos_cuarto else "No registra"
            
            muestra_actual = (texto_3er, texto_4to)
            muestras_obtenidas.append(muestra_actual)
            print(f"    [✓ MUESTRA EXITOSA #{len(muestras_obtenidas)}] 3er Nivel ({len(titulos_tercer)}): '{texto_3er[:35]}...' | 4to Nivel ({len(titulos_cuarto)}): '{texto_4to[:35]}...'")
            
            conteo = Counter(muestras_obtenidas)
            respuesta_mas_comun, repeticiones = conteo.most_common(1)[0]
            if repeticiones >= 2:
                print(f"--> [🏆 CONSENSO VERÍDICO ALCANZADO] Respuesta confirmada con {repeticiones} coincidencias idénticas.")
                return respuesta_mas_comun[0], respuesta_mas_comun[1], True
                        
        except Exception as e:
            print(f"    [LOG-EXCEPCIÓN] Error inesperado en el ciclo: {e}")
            time.sleep(1.5)
            
    if muestras_obtenidas:
        conteo = Counter(muestras_obtenidas)
        ganador = conteo.most_common(1)[0][0]
        print("--> [⚠️ CONSENSO POR MAYORÍA SIMPLE] Se aplicó la respuesta más frecuente de las muestras capturadas.")
        return ganador[0], ganador[1], True
    
    print("--> [❌ FALLO TOTAL] No se pudo obtener consenso ni superar el CAPTCHA tras los 6 intentos.")
    return "No registra", "No registra", False

def procesar_excel_completo(
    archivo_bytes, 
    progress_callback, 
    col_cedula_idx=3,     # Columna C
    col_3er_idx=6,        # Columna F
    col_4to_idx=7,        # Columna G
    col_materia_idx=None, 
    col_semestre_idx=None,
    col_codigo_idx=None,  
    forzar_reevaluacion=False, 
    ver_navegador=False,
    reverificar_no_registra=False, # 👉 PARÁMETRO DE REVERIFICACIÓN INTELIGENTE
    **kwargs              
):
    """
    Procesa la plantilla de carga horaria. Permite reverificar selectivamente 
    aquellos docentes que hayan quedado marcados como 'No registra'.
    """
    wb = openpyxl.load_workbook(io.BytesIO(archivo_bytes))
    ws = wb.active
    
    fila_inicio = 3 
    fila_fin = ws.max_row
    total_registros = fila_fin - fila_inicio + 1
    
    cache = cargar_cache()
    hubo_cambios_cache = False
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not ver_navegador, slow_mo=350 if ver_navegador else 0)
        context = browser.new_context()
        page = context.new_page()
        
        for num_fila in range(fila_inicio, fila_fin + 1):
            celda_cedula = ws.cell(row=num_fila, column=col_cedula_idx).value
            
            if not celda_cedula:
                progress_callback((num_fila - fila_inicio + 1) / total_registros, f"Fila {num_fila} vacía saltada...")
                continue
                
            # Normalización a 10 dígitos
            cedula_limpia = ''.join(filter(str.isdigit, str(celda_cedula).split('.')[0]))
            if len(cedula_limpia) < 10:
                cedula = cedula_limpia.zfill(10)
            else:
                cedula = cedula_limpia[:10]
            
            # --- EVALUACIÓN DE ESTADO ACTUAL EN CACHÉ Y EN EXCEL ---
            t3_cache = cache.get(cedula, {}).get("tercer_nivel", "No registra")
            t4_cache = cache.get(cedula, {}).get("cuarto_nivel", "No registra")
            es_no_registra_en_cache = (t3_cache == "No registra" and t4_cache == "No registra")
            
            val_3er_excel = str(ws.cell(row=num_fila, column=col_3er_idx).value or "").strip()
            val_4to_excel = str(ws.cell(row=num_fila, column=col_4to_idx).value or "").strip()
            es_no_registra_en_excel = (val_3er_excel in ["", "None", "No registra"] and val_4to_excel in ["", "None", "No registra"])
            
            # --- ÁRBOL DE DECISIÓN: ¿DEBEMOS RASPAR EN VIVO ESTA CÉDULA? ---
            necesita_raspar = False
            
            if forzar_reevaluacion:
                necesita_raspar = True
            elif reverificar_no_registra:
                # 👉 EN MODO REVERIFICAR: Solo raspamos si ambas columnas están en "No registra" o vacías
                if cedula not in cache or es_no_registra_en_cache or es_no_registra_en_excel:
                    necesita_raspar = True
                    print(f"[LOG-REVERIFICACIÓN] Cédula {cedula} sin títulos en registros previos. Reintentando consulta web...")
                else:
                    necesita_raspar = False
                    print(f"[LOG-REVERIFICACIÓN] Cédula {cedula} ya cuenta con títulos. Se salta consulta en vivo.")
            elif cedula not in cache:
                necesita_raspar = True
            else:
                necesita_raspar = False
            
            # --- EJECUCIÓN O LECTURA RÁPIDA ---
            if not necesita_raspar and cedula in cache:
                progress_callback((num_fila - fila_inicio + 1) / total_registros, f"[{cedula}] Títulos recuperados desde caché...")
                texto_3er = cache[cedula].get("tercer_nivel", "No registra")
                texto_4to = cache[cedula].get("cuarto_nivel", "No registra")
            elif not necesita_raspar and cedula not in cache:
                progress_callback((num_fila - fila_inicio + 1) / total_registros, f"[{cedula}] Saltado (Ya cuenta con datos en el archivo Excel)...")
                continue # Respetamos las celdas intocadas
            else:
                progress_callback((num_fila - fila_inicio + 1) / total_registros, f"[{cedula}] Auditando en portal SENESCYT...")
                texto_3er, texto_4to, exito = consultar_senescyt_web(page, cedula)
                
                if exito:
                    cache[cedula] = {
                        "tercer_nivel": texto_3er,
                        "cuarto_nivel": texto_4to,
                        "ultima_actualizacion": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    hubo_cambios_cache = True
                
                time.sleep(random.uniform(1.5, 3.0))
            
            # Inyectar Títulos en el Excel en Columna F (6) y Columna G (7)
            ws.cell(row=num_fila, column=col_3er_idx).value = texto_3er
            ws.cell(row=num_fila, column=col_4to_idx).value = texto_4to
            
        browser.close()
        
    if hubo_cambios_cache:
        guardar_cache(cache)
        print("\n--> [LOG-SISTEMA] Historial de caché guardado en disco exitosamente.")
        
    output_buffer = io.BytesIO()
    wb.save(output_buffer)
    return output_buffer.getvalue(), cache