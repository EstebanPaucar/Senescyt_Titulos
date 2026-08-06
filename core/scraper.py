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

# --- PARCHE CRÍTICO PARA WINDOWS + STREAMLIT + PLAYWRIGHT ---
import asyncio
import sys
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
# ---------------------------------------------------------------

# RUTA TESSERACT: Funciona en local. En la nube Streamlit usa la variable global de Linux automáticamente.
if sys.platform == 'win32':
    # Solo usará la ruta de Windows si detecta que estás en tu computadora local
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

ARCHIVO_CACHE = "historial_auditorias.json"

def cargar_cache():
    if os.path.exists(ARCHIVO_CACHE):
        try:
            with open(ARCHIVO_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {}
    return {}

def guardar_cache(data_cache):
    try:
        with open(ARCHIVO_CACHE, "w", encoding="utf-8") as f:
            json.dump(data_cache, f, ensure_ascii=False, indent=4)
    except Exception as e:
        pass

def resolver_captcha(ruta_imagen, log_callback=None):
    def l(msg):
        if log_callback: log_callback(msg)
        print(msg)
        
    try:
        img = cv2.imread(ruta_imagen, cv2.IMREAD_GRAYSCALE)
        img_agrandada = cv2.resize(img, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        img_limpia = cv2.fastNlMeansDenoising(img_agrandada, None, h=15, templateWindowSize=7, searchWindowSize=21)
        img_invertida = cv2.bitwise_not(img_limpia)
        _, img_bin = cv2.threshold(img_invertida, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        img_morf = cv2.morphologyEx(img_bin, cv2.MORPH_CLOSE, kernel)
        
        cv2.imwrite("captcha_procesado.png", img_morf)
        
        config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        texto = pytesseract.image_to_string(Image.open("captcha_procesado.png"), config=config)
        
        texto_limpio = "".join(filter(str.isalnum, texto.strip()))
        return texto_limpio
    except Exception as e:
        l(f"[!] Error en visión artificial OpenCV/Tesseract: {e}")
        return ""

def consultar_senescyt_web(page, cedula, log_callback=None):
    """
    Versión con Logs Inyectados para detectar fallos en la nube.
    """
    def l(msg):
        if log_callback: log_callback(msg)
        print(msg)

    muestras_obtenidas = []
    intentos_navegacion = 0
    max_intentos_navegacion = 6
    
    l(f"--- INICIANDO AUDITORÍA WEB PARA CÉDULA: {cedula} ---")
    
    while len(muestras_obtenidas) < 3 and intentos_navegacion < max_intentos_navegacion:
        intentos_navegacion += 1
        l(f"[Intento {intentos_navegacion}/{max_intentos_navegacion}] Navegando al portal Senescyt...")
        
        try:
            page.goto("https://www.senescyt.gob.ec/web/guest/consultas", timeout=60000)
            page.wait_for_load_state('networkidle')
            l("Portal cargado. Cerrando modales...")
            
            try:
                selector_cierre = 'a.ui-dialog-titlebar-close, span.ui-icon-closethick'
                if page.locator(selector_cierre).first.is_visible(timeout=2000):
                    page.locator(selector_cierre).first.click()
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
            
            selector_cedula = 'input[id="formPrincipal:identificacion"]'
            page.wait_for_selector(selector_cedula, state="visible", timeout=5000)
            page.locator(selector_cedula).click()
            page.locator(selector_cedula).clear()
            page.locator(selector_cedula).press_sequentially(cedula, delay=80)
            
            l(f"Cédula {cedula} ingresada en el input.")

            selector_img_captcha = 'img[id="formPrincipal:capimg"]'
            page.locator(selector_img_captcha).screenshot(path="captcha_temp.png")
            texto_captcha = resolver_captcha("captcha_temp.png", log_callback)
            
            l(f"Tesseract leyó: '{texto_captcha}'")
            
            if not texto_captcha or len(texto_captcha) < 4 or len(texto_captcha) > 6:
                l(f"Lectura descartada por tamaño incorrecto ({len(texto_captcha)} chars). Reintentando...")
                time.sleep(1.2)
                continue
                
            selector_input_captcha = 'input[id="formPrincipal:captchaSellerInput"]'
            page.locator(selector_input_captcha).fill(texto_captcha)

            selector_boton = 'button[id="formPrincipal:boton-buscar"]'
            page.wait_for_selector(f'{selector_boton}:not([disabled])', timeout=5000)
            l("Clic en botón Buscar...")
            page.click(selector_boton)
            
            l("Esperando respuesta del servidor SENESCYT...")
            tiempo_inicio = time.time()
            tabla_encontrada = False
            estado_servidor = "DESCONOCIDO"
            
            while time.time() - tiempo_inicio < 9.5:
                contenido_html = page.content().lower()
                
                if page.locator('tbody.ui-datatable-data').count() > 0 and page.locator('tbody.ui-datatable-data').first.is_visible():
                    tabla_encontrada = True
                    estado_servidor = "TABLAS_CARGADAS"
                    break
                
                if any(x in contenido_html for x in ["código de seguridad incorrecto", "código incorrecto", "captcha incorrecto", "texto de la imagen"]):
                    estado_servidor = "CAPTCHA_RECHAZADO"
                    break
                    
                if page.locator('.ui-messages-error, .ui-message-error, .ui-growl-message').count() > 0:
                    msj_error = page.locator('.ui-messages-error, .ui-message-error, .ui-growl-message').first.inner_text().strip().replace('\n', ' - ')
                    if msj_error:
                        estado_servidor = f"ERROR_GOBIERNO: '{msj_error}'"
                        break
                
                if any(x in contenido_html for x in ["no se encontr", "sin registro", "ningún registro"]):
                    tabla_encontrada = True
                    estado_servidor = "CONFIRMADO_SIN_REGISTROS"
                    break
                    
                time.sleep(0.5)
            
            l(f"Estado de red devuelto: {estado_servidor}")
            
            if not tabla_encontrada and "CAPTCHA" in estado_servidor:
                l("El servidor rechazó el CAPTCHA. Reintentando de inmediato...")
                time.sleep(3.0)
                continue
            elif not tabla_encontrada:
                l("Timeout: La tabla no cargó en el tiempo esperado. Posible caída de Senescyt.")
                continue
                
            l("Extrayendo HTML mediante BeautifulSoup...")
            time.sleep(1.2)
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            titulos_tercer = []
            titulos_cuarto = []
            
            encabezados_panel = soup.find_all('h4', class_='panel-title')
            l(f"Detectados {len(encabezados_panel)} paneles en la vista.")
            
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
                    l("Alerta: Tablas vacías pero sin mensaje oficial. Error de renderizado AJAX.")
                    continue
            
            texto_3er = " | ".join(titulos_tercer) if titulos_tercer else "No registra"
            texto_4to = " | ".join(titulos_cuarto) if titulos_cuarto else "No registra"
            
            muestra_actual = (texto_3er, texto_4to)
            muestras_obtenidas.append(muestra_actual)
            l(f"Extracción #{len(muestras_obtenidas)} exitosa: T3({len(titulos_tercer)}) T4({len(titulos_cuarto)})")
            
            conteo = Counter(muestras_obtenidas)
            respuesta_mas_comun, repeticiones = conteo.most_common(1)[0]
            if repeticiones >= 2:
                l(">>> CONSENSO LOGRADO <<<")
                return respuesta_mas_comun[0], respuesta_mas_comun[1], True
                        
        except Exception as e:
            l(f"Error inesperado Playwright: {str(e)}")
            time.sleep(1.5)
            
    if muestras_obtenidas:
        conteo = Counter(muestras_obtenidas)
        ganador = conteo.most_common(1)[0][0]
        l(">>> CONSENSO POR MAYORIA SIMPLE <<<")
        return ganador[0], ganador[1], True
    
    l(f"FALLO TOTAL: No se extrajeron datos para {cedula}.")
    return "No registra", "No registra", False

def procesar_excel_completo(
    archivo_bytes, 
    progress_callback, 
    log_callback=None,
    col_cedula_idx=3,     
    col_3er_idx=6,        
    col_4to_idx=7,        
    col_materia_idx=None, 
    col_semestre_idx=None,
    col_codigo_idx=None,  
    forzar_reevaluacion=False, 
    ver_navegador=False,
    reverificar_no_registra=False,
    **kwargs              
):
    
    def l(msg):
        if log_callback: log_callback(msg)
        print(msg)
        
    wb = openpyxl.load_workbook(io.BytesIO(archivo_bytes))
    ws = wb.active
    
    fila_inicio = 3 
    fila_fin = ws.max_row
    total_registros = fila_fin - fila_inicio + 1
    
    cache = cargar_cache()
    hubo_cambios_cache = False
    
    with sync_playwright() as p:
        # En Streamlit Cloud forzamos headless para evitar crashes del display server
        modo_headless = True if not sys.platform == 'win32' else not ver_navegador
        
        l(f"Inicializando Playwright (Headless: {modo_headless})...")
        browser = p.chromium.launch(headless=modo_headless, slow_mo=350 if ver_navegador and sys.platform == 'win32' else 0)
        context = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36')
        page = context.new_page()
        
        for num_fila in range(fila_inicio, fila_fin + 1):
            celda_cedula = ws.cell(row=num_fila, column=col_cedula_idx).value
            
            if not celda_cedula:
                continue
                
            cedula_limpia = ''.join(filter(str.isdigit, str(celda_cedula).split('.')[0]))
            cedula = cedula_limpia.zfill(10) if len(cedula_limpia) < 10 else cedula_limpia[:10]
            
            t3_cache = cache.get(cedula, {}).get("tercer_nivel", "No registra")
            t4_cache = cache.get(cedula, {}).get("cuarto_nivel", "No registra")
            es_no_registra_en_cache = (t3_cache == "No registra" and t4_cache == "No registra")
            
            val_3er_excel = str(ws.cell(row=num_fila, column=col_3er_idx).value or "").strip()
            val_4to_excel = str(ws.cell(row=num_fila, column=col_4to_idx).value or "").strip()
            es_no_registra_en_excel = (val_3er_excel in ["", "None", "No registra"] and val_4to_excel in ["", "None", "No registra"])
            
            necesita_raspar = False
            
            if forzar_reevaluacion:
                necesita_raspar = True
            elif reverificar_no_registra:
                if cedula not in cache or es_no_registra_en_cache or es_no_registra_en_excel:
                    necesita_raspar = True
            elif cedula not in cache:
                necesita_raspar = True
            
            if not necesita_raspar and cedula in cache:
                progress_callback((num_fila - fila_inicio + 1) / total_registros, f"[{cedula}] Recuperado de caché")
                texto_3er = cache[cedula].get("tercer_nivel", "No registra")
                texto_4to = cache[cedula].get("cuarto_nivel", "No registra")
            elif not necesita_raspar and cedula not in cache:
                continue 
            else:
                progress_callback((num_fila - fila_inicio + 1) / total_registros, f"[{cedula}] Consultando en web...")
                texto_3er, texto_4to, exito = consultar_senescyt_web(page, cedula, log_callback)
                
                if exito:
                    cache[cedula] = {
                        "tercer_nivel": texto_3er,
                        "cuarto_nivel": texto_4to,
                        "ultima_actualizacion": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    hubo_cambios_cache = True
                
                time.sleep(random.uniform(1.5, 3.0))
            
            ws.cell(row=num_fila, column=col_3er_idx).value = texto_3er
            ws.cell(row=num_fila, column=col_4to_idx).value = texto_4to
            
        browser.close()
        
    if hubo_cambios_cache:
        guardar_cache(cache)
        l("Caché guardada exitosamente.")
        
    output_buffer = io.BytesIO()
    wb.save(output_buffer)
    return output_buffer.getvalue(), cache