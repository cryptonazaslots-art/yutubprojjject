"""
ViralEngine V4 — Human-in-the-Loop
Modelo: gemini-2.5-flash-lite (1000 req/día gratuito)
Input: tema pasado como argumento desde GitHub Actions
Output: Short de YouTube con subtítulos quemados
"""

import os
import sys
import asyncio
import json
import re
import requests
import random
import subprocess
from google import genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import edge_tts

# ── Modelo ─────────────────────────────────────────────────────────────────────
# gemini-2.5-flash-lite: máxima cuota gratuita (1000 req/día, 15 RPM)
# gemini-2.0-flash fue deprecado — se retira el 1 de junio de 2026
MODELO = "gemini-2.5-flash-lite"

# ── Banco de contenido (estoicismo + psicología + curiosidades) ────────────────
NICHOS_DEFAULT = [
    "Marco Aurelio y el control de las emociones",
    "Séneca sobre el uso del tiempo",
    "Epicteto y la dicotomía del control",
    "psicología oscura: el efecto ancla en decisiones",
    "sesgo de confirmación: por qué creemos lo que creemos",
    "El estoicismo aplicado al trabajo moderno",
    "curiosidad histórica perturbadora poco conocida",
    "truco mental respaldado por la ciencia",
]

VOCES = [
    "es-AR-TomasNeural",   # Masculina argentina
    "es-AR-ElenaNeural",   # Femenina argentina
]

QUERIES_VIDEO = [
    "ancient rome cinematic",
    "philosophy nature contemplation",
    "dark moody atmospheric",
    "abstract mind psychology",
    "stoic warrior silhouette",
    "ancient greece ruins",
    "ocean meditation calm",
    "dark forest cinematic",
]

TITULOS = [
    "Lo que {filosofo} te diría hoy 🧠 #shorts",
    "El secreto que cambió mi perspectiva 👁️ #shorts",
    "Esto nadie te lo enseñó #shorts",
    "La verdad que duele pero libera #shorts",
    "1 idea que cambia todo 🔥 #shorts",
    "Lo que los sabios sabían y nosotros olvidamos #shorts",
]

DESCRIPCION = (
    "🧠 Filosofía estoica y psicología aplicada — un dato por día.\n"
    "✅ Suscribite para no perderte ninguno.\n\n"
    "#shorts #estoicismo #filosofia #psicologia #mentalidad #viral #argentina"
)

# ── Paso 1: Generar guion con estructura narrativa ─────────────────────────────

def generar_guion(tema: str) -> dict:
    """
    Genera un guion con estructura narrativa de 3 actos.
    Retorna dict con: guion, titulo, filosofo (si aplica)
    """
    client = genai.Client(api_key=os.environ["GEMINI_API"])

    prompt = f"""Sos un creador de contenido filosófico viral en YouTube para audiencia argentina.

TEMA: {tema}

Generá un guion para un YouTube Short con esta estructura de 3 actos (máximo 50 palabras en total):

ACTO 1 — GANCHO (8-10 palabras): Una frase que genere shock inmediato o curiosidad insaciable.
ACTO 2 — DESARROLLO (25-30 palabras): La idea central explicada de forma simple y directa. Si tiene un filósofo o personaje, nómbralo.
ACTO 3 — CIERRE (8-10 palabras): Una frase reflexiva que invite a quedarse y suscribirse.

Usá el voseo argentino. Hablá directo al oyente. Nada de presentaciones como "Hola, hoy vamos a hablar de...".

Respondé SOLO con este formato JSON exacto, sin markdown ni backticks:
{{
  "guion": "texto completo del guion separando actos con | ",
  "titulo": "título para YouTube de máximo 60 caracteres con emoji",
  "filosofo": "nombre del filósofo si aplica, o null"
}}"""

    response = client.models.generate_content(
        model=MODELO,
        contents=prompt,
    )

    texto = response.text.strip()

    # Limpiar posibles backticks de markdown
    texto = re.sub(r"```json\s*", "", texto)
    texto = re.sub(r"```\s*", "", texto)
    texto = texto.strip()

    try:
        data = json.loads(texto)
        return data
    except json.JSONDecodeError:
        # Fallback si Gemini no respeta el formato
        print(f"⚠️  JSON inválido, usando fallback. Respuesta: {texto[:200]}")
        return {
            "guion": texto,
            "titulo": f"Dato filosófico del día 🧠 #shorts",
            "filosofo": None,
        }


# ── Paso 2: Audio + tiempos para subtítulos ───────────────────────────────────

async def generar_audio_con_tiempos(texto: str) -> list[dict]:
    """
    Genera audio y extrae los tiempos de cada palabra para subtítulos.
    Retorna lista de {word, start, end} en segundos.
    """
    voz = random.choice(VOCES)
    comunicador = edge_tts.Communicate(texto, voz, rate="+5%")

    palabras = []
    chunks = []

    async for chunk in comunicador.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            palabras.append({
                "word": chunk["text"],
                "start": chunk["offset"] / 1e7,          # 100ns → segundos
                "end": (chunk["offset"] + chunk["duration"]) / 1e7,
            })

    # Guardar audio
    with open("audio.mp3", "wb") as f:
        for c in chunks:
            f.write(c)

    print(f"🔊 Audio con voz: {voz} — {len(palabras)} palabras detectadas")
    return palabras


def generar_archivo_subtitulos(palabras: list[dict], archivo: str = "subs.srt") -> None:
    """
    Genera un archivo .srt agrupando palabras de a 4-5 para subtítulos legibles.
    """
    if not palabras:
        # Crear un .srt vacío para que FFmpeg no falle
        with open(archivo, "w") as f:
            f.write("")
        return

    grupos = []
    i = 0
    idx = 1
    while i < len(palabras):
        grupo = palabras[i:i+4]
        texto_grupo = " ".join(p["word"] for p in grupo)
        inicio = grupo[0]["start"]
        fin = grupo[-1]["end"]
        grupos.append((idx, inicio, fin, texto_grupo))
        idx += 1
        i += 4

    def fmt(segundos: float) -> str:
        h = int(segundos // 3600)
        m = int((segundos % 3600) // 60)
        s = int(segundos % 60)
        ms = int((segundos % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(archivo, "w", encoding="utf-8") as f:
        for idx, inicio, fin, texto in grupos:
            f.write(f"{idx}\n")
            f.write(f"{fmt(inicio)} --> {fmt(fin)}\n")
            f.write(f"{texto}\n\n")

    print(f"📝 Subtítulos generados: {len(grupos)} líneas")


# ── Paso 3: Video de fondo ─────────────────────────────────────────────────────

def descargar_video_fondo(archivo: str = "raw.mp4") -> None:
    query = random.choice(QUERIES_VIDEO)
    headers = {"Authorization": os.environ["PEXELS_API"]}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=10&orientation=portrait&size=medium"

    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    datos = r.json()

    if not datos.get("videos"):
        raise RuntimeError(f"Pexels sin resultados para: {query}")

    video = random.choice(datos["videos"])
    archivos = video["video_files"]
    hd = [f for f in archivos if f.get("quality") in ("hd", "sd")]
    link = (hd[0] if hd else archivos[0])["link"]

    with open(archivo, "wb") as f:
        f.write(requests.get(link, timeout=60).content)
    print(f"🎬 Video: {query}")


# ── Paso 4: FFmpeg con subtítulos quemados ────────────────────────────────────

def procesar_video(
    entrada: str = "raw.mp4",
    audio: str = "audio.mp3",
    subs: str = "subs.srt",
    salida: str = "final.mp4"
) -> None:
    """
    Ensambla video 1080x1920 con subtítulos quemados.
    Los subtítulos aparecen en el tercio inferior con fuente grande y legible.
    """
    # Filtro de video: escalar + pad + subtítulos quemados
    subs_abs = os.path.abspath(subs)

    # Verificar si hay subtítulos
    tiene_subs = os.path.exists(subs) and os.path.getsize(subs) > 0

    if tiene_subs:
        vf = (
            "scale=w=1080:h=1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
            "setsar=1,"
            f"subtitles={subs_abs}:force_style='FontName=Arial,FontSize=22,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BackColour=&H80000000,Bold=1,Alignment=2,"
            "MarginV=80,BorderStyle=4'"
        )
    else:
        vf = (
            "scale=w=1080:h=1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
            "setsar=1"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", entrada,
        "-i", audio,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        salida,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg stderr:", result.stderr[-2000:])
        raise RuntimeError("FFmpeg falló")

    if not os.path.exists(salida):
        raise RuntimeError("FFmpeg no generó final.mp4")
    print("✂️  Video procesado: 1080x1920 con subtítulos")


# ── Paso 5: Subir a YouTube ────────────────────────────────────────────────────

def subir_a_youtube(titulo: str, archivo: str = "final.mp4") -> None:
    info = json.loads(os.environ["YT_TOKEN"])
    creds = Credentials.from_authorized_user_info(info)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    yt = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": titulo[:100],
            "description": DESCRIPCION,
            "tags": [
                "shorts", "estoicismo", "filosofia", "psicologia",
                "mentalidad", "viral", "argentina", "datos", "motivacion",
                "marco aurelio", "seneca", "epicteto",
            ],
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
    print(f"🚀 Subido: '{titulo}'")


# ── Flujo principal ────────────────────────────────────────────────────────────

async def fabricar_video(tema: str):
    print(f"\n{'='*50}")
    print(f"🎯 Tema: {tema}")
    print(f"{'='*50}\n")

    # 1. Guion con estructura narrativa
    datos = generar_guion(tema)
    guion = datos.get("guion", tema)
    titulo = datos.get("titulo", "Dato del día 🧠 #shorts")
    filosofo = datos.get("filosofo")

    # Reemplazar placeholder en título si hay filósofo
    if filosofo and "{filosofo}" in titulo:
        titulo = titulo.replace("{filosofo}", filosofo)
    elif "{filosofo}" in titulo:
        titulo = titulo.replace("{filosofo}", "los sabios")

    print(f"📝 Guion: {guion}")
    print(f"🏷️  Título: {titulo}")

    # 2. Audio + tiempos para subtítulos
    palabras = await generar_audio_con_tiempos(guion)

    # 3. Subtítulos
    generar_archivo_subtitulos(palabras)

    # 4. Video de fondo
    descargar_video_fondo()

    # 5. FFmpeg
    procesar_video()

    # 6. Subir
    subir_a_youtube(titulo)

    print(f"\n✅ ¡Short publicado exitosamente!")


if __name__ == "__main__":
    # El tema puede venir como argumento desde GitHub Actions
    # Ejemplo: python main.py "Marco Aurelio y las emociones"
    if len(sys.argv) > 1:
        tema_elegido = " ".join(sys.argv[1:])
    else:
        # Fallback: tema aleatorio del banco
        tema_elegido = random.choice(NICHOS_DEFAULT)
        print(f"ℹ️  Sin argumento — usando tema aleatorio")

    asyncio.run(fabricar_video(tema_elegido))
