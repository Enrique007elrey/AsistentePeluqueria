# Asistente Virtual para una Peluquería con IA

Chat de escritorio hecho con **Tkinter** que responde preguntas sobre la peluquería
"Brillo Estelar" usando la **API de Google Gemini**. Los datos de la peluquería
están en `servicios.txt` y se le pasan al modelo como contexto.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `asistente_gui.py` | Programa principal (interfaz + llamada a Gemini) |
| `servicios.txt` | Servicios, precios y horarios: el contexto de la IA |
| `requirements.txt` | Librerías que hay que instalar |
| `.env.example` | Plantilla del `.env` (sin clave real) |
| `.gitignore` | Evita que el `.env` se suba a GitHub |

## Instalación y ejecución

```bash
pip install -r requirements.txt
```

1. Copia `.env.example` como `.env`.
2. Pon tu clave en `API_KEY=` (se saca en https://aistudio.google.com/app/apikey).
3. Ejecuta:

```bash
python asistente_gui.py
```

> Tkinter viene incluido con Python en Windows, por eso no está en `requirements.txt`.

## Cómo funciona

```
Usuario escribe → Tkinter → preguntar_a_gemini() → API Gemini
                                                       ↓
Chat muestra texto ← limpiar_markdown() ← JSON → candidates[0].content.parts[].text
```

- **Clave API:** `load_dotenv()` carga el `.env` y `os.getenv("API_KEY")` la lee.
- **Contexto:** el contenido de `servicios.txt` se mete en la *system instruction*
  junto con unas reglas (solo hablar de la peluquería, no inventar precios).
- **JSON:** la respuesta se pasa a diccionario con `json.loads` y se recorre hasta el texto.
- **Sin congelarse:** la llamada a la API va en un `threading.Thread` y la respuesta
  vuelve a la ventana con `ventana.after()`.
- **Errores:** sin internet, clave mala o límite superado se muestra un aviso en rojo.
