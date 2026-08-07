import os
from scraper import procesar_excel_concurrente

def main():
    ruta_input = "inputs/matriz_a_procesar.xlsx"
    ruta_output = "outputs/matriz_procesada.xlsx"
    
    if not os.path.exists(ruta_input):
        print(f"❌ Error crítico: No se encontró el archivo en {ruta_input}")
        return

    print("📥 Leyendo matriz de entrada...")
    with open(ruta_input, "rb") as f:
        bytes_entrada = f.read()
        
    bytes_salida = procesar_excel_concurrente(bytes_entrada)
    
    # Crear carpeta de salida si no existe y guardar el archivo procesado
    os.makedirs(os.path.dirname(ruta_output), exist_ok=True)
    with open(ruta_output, "wb") as f:
        f.write(bytes_salida)
        
    print(f"💾 Excel auditado guardado con éxito en {ruta_output}")

if __name__ == "__main__":
    main()