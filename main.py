import os
import asyncio
import json
import requests
import random
import subprocess
from google import genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import edge_tts

# ── Configuración ────────────────────────────────────────────────────────────
TEMAS = [
    "psicología oscura",
    "datos que podrían salvarte la vida",
    "curiosidades aterradoras",
    "hechos históricos que nadie te contó",
    "secretos de la mente humana",
]

VOCES = [
    "es-AR-TomasNeural",
    "es-AR-ElenaNeural",
]

QUERIES_VIDEO = [
    "mysterious dark forest",
    "deep ocean",
    "abstract texture",
    "dark sky stars",
    "cinematic nature",
]

TITULOS = [
    "Esto te cambiará la mente 🧠 #shorts",
    "Nadie te lo dijo... hasta hoy 👁️ #shorts",
    "Dato que necesitás saber 🔥 #shorts",
    "¿Lo sabías? 😱 #shorts",
    "La verdad detrás de todo #shorts",
]

# ── Funciones principales ─────────────────────────────────────────────────────

def generar_guion(tema: str) -> str:
    """Genera el guion usando Gemini 2.0 Flash (modelo estable y gratuito)."""
    client = genai.Client(api_key=os.environ["GEMINI_API"])
    prompt = (
        f"Escribe un guion para un Short de YouTube sobre '{tema}'. "
        "Debe ser impactante, intrigante y generar curiosidad desde la primera palabra. "
        "Máximo 40 palabras. Devuelve solo el texto del guion, sin títulos ni aclaraciones."
    )
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return response.text.strip()


async def generar_audio(texto: str, archivo: str = "audio.mp3") -> None:
    """Convierte el guion a voz con edge-tts."""
    voz = random.choice(VOCES)
    comunicador = edge_tts.Communicate(texto, voz)
    await comunicador.save(archivo)
    print(f"🔊 Audio generado con voz: {voz}")


def descargar_video_fondo(archivo: str = "raw.mp4") -> None:
    """Descarga un video de fondo desde Pexels."""
    query = random.choice(QUERIES_VIDEO)
    headers = {"Authorization": os.environ["PEXELS_API"]}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait"

    respuesta = requests.get(url, headers=headers, timeout=30)
    respuesta.raise_for_status()
    datos = respuesta.json()

    # Elegir un video aleatorio entre los resultados
    video = random.choice(datos["videos"])

    # Preferir archivo en resolución HD si existe
    archivos = video["video_files"]
    hd = [f for f in archivos if f.get("quality") in ("hd", "sd")]
    link = hd[0]["link"] if hd else archivos[0]["link"]

    contenido = requests.get(link, timeout=60).content
    with open(archivo, "wb") as f:
        f.write(contenido)
    print(f"🎬 Video de fondo descargado ({query})")


def procesar_video(entrada: str = "raw.mp4", audio: str = "audio.mp3", salida: str = "final.mp4") -> None:
    """Combina video y audio con FFmpeg en formato vertical para Shorts."""
    cmd = [
        "ffmpeg", "-y",
        "-i", entrada,
        "-i", audio,
        "-vf", (
            # Recortar a 9:16, forzar dimensiones pares, agregar negro si es necesario
            "scale=iw*min(1080/iw\\,1920/ih):ih*min(1080/iw\\,1920/ih),"
            "pad=1080:1920:(1080-iw)/2:(1920-ih)/2:black,"
            "setsar=1"
        ),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        salida,
    ]
    subprocess.run(cmd, check=True)

    if not os.path.exists(salida):
        raise RuntimeError("FFmpeg no generó el archivo final.mp4")
    print("✂️  Video procesado correctamente")


def subir_a_youtube(archivo: str = "final.mp4") -> None:
    """Sube el video a YouTube usando las credenciales OAuth."""
    info = json.loads(os.environ["YT_TOKEN"])
    creds = Credentials.from_authorized_user_info(info)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    yt = build("youtube", "v3", credentials=creds)

    titulo = random.choice(TITULOS)
    body = {
        "snippet": {
            "title": titulo,
            "description": "🔥 Suscribite para más datos increíbles cada día.",
            "tags": ["shorts", "psicologia", "datos", "curiosidades", "viral"],
            "categoryId": "22",
            "defaultLanguage": "es",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(archivo, chunksize=-1, resumable=True)
    yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    print(f"🚀 Video subido: '{titulo}'")


# ── Flujo principal ───────────────────────────────────────────────────────────

async def fabricar_video():
    tema = random.choice(TEMAS)
    print(f"📌 Tema seleccionado: {tema}")

    # 1. Guion
    guion = generar_guion(tema)
    print(f"📝 Guion: {guion}")

    # 2. Audio
    await generar_audio(guion)

    # 3. Video de fondo
    descargar_video_fondo()

    # 4. FFmpeg
    procesar_video()

    # 5. Subir a YouTube
    subir_a_youtube()

    print("✅ ¡Video publicado exitosamente!")


if __name__ == "__main__":
    asyncio.run(fabricar_video())
