import google.generativeai as genai

# Pega tu clave AIzaSy... aquí entre las comillas
api_key = "AQ.Ab8RN6J95CDno6XSfU9e5SjVUk-MMHMR80ZC3NtpPdi09IeNlw" 
genai.configure(api_key=api_key)

print("🤖 Lista de modelos activos y autorizados para tu API Key:")
for modelo in genai.list_models():
    if "generateContent" in modelo.supported_generation_methods:
        print(f" -> {modelo.name}")