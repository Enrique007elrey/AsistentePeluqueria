"""
Asistente Virtual para una Peluquería con IA
--------------------------------------------
Flujo de la aplicación:  GUI (Tkinter) -> Python -> API de Gemini -> JSON -> GUI

- La API Key se lee de un fichero .env (nunca está escrita en el código).
- Los datos de la peluquería se leen de servicios.txt y se le pasan a Gemini
  como contexto (in-context learning): el modelo NO se entrena, solo recibe
  la información en cada consulta.
- La respuesta de la API se convierte a JSON y se extrae solo el texto.
"""

import os
import json
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, messagebox

from dotenv import load_dotenv
from google import genai
from google.genai import types


# ---------------------------------------------------------------------------
# 1. CONFIGURACIÓN: variables de entorno y ficheros
# ---------------------------------------------------------------------------

# Carpeta donde está este script. La usamos para encontrar .env y servicios.txt
# aunque el programa se ejecute desde otra carpeta.
CARPETA = os.path.dirname(os.path.abspath(__file__))

# load_dotenv lee el fichero .env y mete sus líneas (API_KEY=...) como
# variables de entorno del proceso. Así la clave no aparece en el código
# y, como .env está en .gitignore, tampoco se sube a GitHub.
load_dotenv(os.path.join(CARPETA, ".env"))

# os.getenv busca la variable de entorno por su nombre. Si no existe devuelve
# None (o el valor por defecto que le pasemos), en lugar de dar error.
API_KEY = os.getenv("API_KEY")
MODELO = os.getenv("MODELO", "gemini-3.5-flash")

RUTA_SERVICIOS = os.path.join(CARPETA, "servicios.txt")


def cargar_servicios():
    """Lee servicios.txt. Este texto es el 'conocimiento' que tendrá la IA."""
    with open(RUTA_SERVICIOS, "r", encoding="utf-8") as fichero:
        return fichero.read()


def crear_instrucciones(servicios):
    """
    Construye las instrucciones de sistema (system instruction).
    Aquí está el 'prompt engineering': le decimos a Gemini QUIÉN es, QUÉ datos
    puede usar y QUÉ hacer si le preguntan algo fuera de la peluquería.
    Los datos van entre marcas (<<< >>>) para que el modelo sepa exactamente
    dónde empieza y acaba la información fiable.
    """
    return f"""Eres el asistente virtual de una peluquería. Respondes en español,
de forma amable, breve y clara.

Solo puedes usar la información que hay entre <<< y >>>:
<<<
{servicios}
>>>

Reglas:
1. Responde ÚNICAMENTE sobre la peluquería: servicios, precios, horarios,
   pagos, ubicación y cosas parecidas.
2. No inventes servicios, precios ni horarios que no estén en la información.
   Si no aparece, di que no tienes ese dato y sugiere llamar por teléfono.
3. Si te preguntan algo que no tiene nada que ver con la peluquería
   (deberes, política, programación...), dilo con educación y vuelve a
   ofrecer ayuda sobre la peluquería.
4. Escribe en texto plano, sin Markdown (nada de asteriscos ni almohadillas).
"""


# ---------------------------------------------------------------------------
# 2. COMUNICACIÓN CON GEMINI
# ---------------------------------------------------------------------------

def preguntar_a_gemini(cliente, instrucciones, pregunta):
    """
    Envía la pregunta a Gemini y devuelve solo el texto de la respuesta.
    """
    respuesta = cliente.models.generate_content(
        model=MODELO,
        contents=pregunta,
        config=types.GenerateContentConfig(
            system_instruction=instrucciones,
            # Temperatura baja = respuestas más fieles a los datos y menos
            # "creativas". Para precios no queremos que se invente nada.
            temperature=0.3,
        ),
    )

    # La API responde con un JSON. La librería lo envuelve en un objeto, así que
    # lo pasamos a texto JSON y con json.loads lo convertimos en un diccionario
    # de Python para recorrerlo como en clase.
    datos = json.loads(respuesta.model_dump_json(exclude_none=True))

    # Estructura (simplificada) del JSON que devuelve Gemini:
    # {
    #   "candidates": [
    #     { "content": { "parts": [ { "text": "...respuesta..." } ] },
    #       "finish_reason": "STOP" }
    #   ],
    #   "usage_metadata": { ... tokens usados ... }
    # }
    candidatos = datos.get("candidates", [])
    if not candidatos:
        return "No he podido generar una respuesta. Prueba a reformular la pregunta."

    partes = candidatos[0].get("content", {}).get("parts", [])

    # Una respuesta puede venir dividida en varias "parts": las juntamos.
    texto = ""
    for parte in partes:
        texto += parte.get("text", "")

    if texto == "":
        return "No he podido generar una respuesta. Prueba a reformular la pregunta."
    return texto


def limpiar_markdown(texto):
    """
    Aunque le pedimos texto plano, a veces Gemini usa Markdown (**negrita**,
    listas con *). Tkinter no interpreta Markdown y se verían los símbolos,
    así que los quitamos para que el chat se lea limpio.
    """
    lineas_limpias = []
    for linea in texto.splitlines():
        linea = linea.replace("**", "").replace("__", "")
        sin_espacios = linea.lstrip()

        if sin_espacios.startswith("#"):            # títulos: "## Precios"
            linea = sin_espacios.lstrip("#").strip()
        elif sin_espacios.startswith(("* ", "- ")):  # listas: "* Tinte"
            linea = "  • " + sin_espacios[2:]

        lineas_limpias.append(linea)
    return "\n".join(lineas_limpias).strip()


# ---------------------------------------------------------------------------
# 3. INTERFAZ GRÁFICA (Tkinter)
# ---------------------------------------------------------------------------

class AsistenteApp:
    def __init__(self, ventana, cliente, instrucciones):
        self.ventana = ventana
        self.cliente = cliente
        self.instrucciones = instrucciones

        ventana.title("Asistente de Peluquería")
        ventana.geometry("620x520")
        ventana.minsize(420, 350)

        # Área del chat. ScrolledText = Text + barra de scroll, para que las
        # respuestas largas no se corten.
        self.chat = scrolledtext.ScrolledText(
            ventana, wrap=tk.WORD, font=("Segoe UI", 11), state=tk.DISABLED
        )
        self.chat.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # Estilos (tags) para distinguir quién habla
        self.chat.tag_config("usuario", foreground="#1a4fd6", font=("Segoe UI", 11, "bold"))
        self.chat.tag_config("asistente", foreground="#1b7a3a")
        self.chat.tag_config("sistema", foreground="#555555")
        self.chat.tag_config("error", foreground="#c0392b")

        # Zona inferior: caja de texto + botón
        zona_inferior = tk.Frame(ventana)
        zona_inferior.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.entrada = tk.Entry(zona_inferior, font=("Segoe UI", 11))
        self.entrada.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        # Pulsar Intro también envía la pregunta
        self.entrada.bind("<Return>", lambda evento: self.enviar())
        self.entrada.focus()

        self.boton = tk.Button(
            zona_inferior, text="Enviar", command=self.enviar,
            bg="#0078d7", fg="white", font=("Segoe UI", 10, "bold"), padx=12
        )
        self.boton.pack(side=tk.LEFT, padx=(8, 0))

        self.escribir("Bienvenido al Asistente de Peluquería.\n"
                      "Escribe tu pregunta abajo y pulsa 'Enviar'.\n\n", "sistema")

    def escribir(self, texto, estilo):
        """Añade texto al chat. El widget está bloqueado para que el usuario
        no pueda escribir en él, así que lo desbloqueamos un momento."""
        self.chat.config(state=tk.NORMAL)
        self.chat.insert(tk.END, texto, estilo)
        self.chat.config(state=tk.DISABLED)
        self.chat.see(tk.END)  # baja el scroll hasta el último mensaje

    def enviar(self):
        pregunta = self.entrada.get().strip()
        if pregunta == "":
            return  # no enviamos preguntas vacías

        self.entrada.delete(0, tk.END)  # limpiamos el input tras enviar
        self.escribir(f"Tú: {pregunta}\n", "usuario")
        self.escribir("Asistente: escribiendo...\n", "sistema")

        # Bloqueamos el botón para no lanzar varias peticiones a la vez
        self.boton.config(state=tk.DISABLED)
        self.entrada.config(state=tk.DISABLED)

        # La llamada a la API tarda unos segundos. Si la hiciéramos aquí
        # directamente, Tkinter no podría redibujar la ventana y se quedaría
        # congelada. Por eso la hacemos en un hilo (thread) aparte.
        hilo = threading.Thread(target=self.consultar, args=(pregunta,), daemon=True)
        hilo.start()

    def consultar(self, pregunta):
        """Se ejecuta en el hilo secundario: habla con la API."""
        # Hasta 3 intentos: si Google está saturado (error 503) suele ser algo
        # de unos segundos, así que esperamos un poco y lo volvemos a probar
        # antes de mostrarle un error al usuario.
        intentos = 3
        for intento in range(1, intentos + 1):
            try:
                texto = preguntar_a_gemini(self.cliente, self.instrucciones, pregunta)
                texto = limpiar_markdown(texto)
                estilo = "asistente"
                break  # ha ido bien: salimos del bucle
            except Exception as error:
                # Sin internet, clave incorrecta, límite de uso... avisamos al
                # usuario en lugar de dejar que el programa se cierre.
                texto = traducir_error(error)
                estilo = "error"
                saturado = "503" in str(error) or "unavailable" in str(error).lower()
                if not saturado or intento == intentos:
                    break  # otro tipo de error o último intento: no reintentamos
                # Esperamos 2 s, luego 4 s. time.sleep no congela la ventana
                # porque esto se ejecuta en el hilo secundario.
                time.sleep(2 * intento)

        # Tkinter solo se puede tocar desde el hilo principal. ventana.after(0, ...)
        # le pide al hilo principal que ejecute mostrar_respuesta en cuanto pueda.
        self.ventana.after(0, self.mostrar_respuesta, texto, estilo)

    def mostrar_respuesta(self, texto, estilo):
        # Borramos la línea "escribiendo..." (es la última línea del chat)
        self.chat.config(state=tk.NORMAL)
        self.chat.delete("end-2l", "end-1l")
        self.chat.config(state=tk.DISABLED)

        self.escribir(f"Asistente: {texto}\n\n", estilo)

        self.boton.config(state=tk.NORMAL)
        self.entrada.config(state=tk.NORMAL)
        self.entrada.focus()


def traducir_error(error):
    """Convierte el error técnico en un mensaje entendible para el usuario."""
    mensaje = str(error).lower()
    if "503" in mensaje or "unavailable" in mensaje or "overloaded" in mensaje:
        return ("El servicio de IA de Google está saturado ahora mismo. "
                "Espera unos segundos y vuelve a preguntar.")
    if "api key" in mensaje or "api_key" in mensaje or "permission" in mensaje:
        return "La API Key no es válida. Revisa el fichero .env."
    if "quota" in mensaje or "429" in mensaje or "exhausted" in mensaje:
        return "Se ha superado el límite de consultas. Espera un poco y vuelve a probar."
    if "not found" in mensaje or "404" in mensaje:
        return f"El modelo '{MODELO}' no está disponible. Cambia MODELO en el .env."
    if "connect" in mensaje or "network" in mensaje or "timed out" in mensaje or "getaddrinfo" in mensaje:
        return "No hay conexión a internet o el servidor no responde. Inténtalo de nuevo."
    # Para errores desconocidos mostramos un mensaje genérico; el detalle
    # técnico va a la consola por si hay que depurarlo.
    print("Error técnico:", error)
    return "Ha ocurrido un error al contactar con la IA. Inténtalo de nuevo."


# ---------------------------------------------------------------------------
# 4. PROGRAMA PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    ventana = tk.Tk()

    # Comprobaciones antes de abrir el chat: si falta algo, avisamos y salimos
    if not API_KEY:
        ventana.withdraw()
        messagebox.showerror("Falta la API Key",
                             "No se ha encontrado API_KEY.\n"
                             "Crea un fichero .env con la línea:\nAPI_KEY=tu_clave")
        return

    try:
        servicios = cargar_servicios()
    except FileNotFoundError:
        ventana.withdraw()
        messagebox.showerror("Falta servicios.txt",
                             "No se encuentra servicios.txt junto al programa.")
        return

    # El cliente es el objeto que se encarga de hablar con la API de Gemini
    cliente = genai.Client(api_key=API_KEY)
    instrucciones = crear_instrucciones(servicios)

    AsistenteApp(ventana, cliente, instrucciones)
    ventana.mainloop()  # bucle que mantiene la ventana abierta y atiende eventos


if __name__ == "__main__":
    main()
