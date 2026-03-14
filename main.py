"""
ViralEngine V5
- Video en loop hasta cubrir el audio completo
- Subtítulos robustos (método directo sin WordBoundary)
- Voz masculina profunda: es-ES-AlvaroNeural (más grave disponible)
- Música ambient sin copyright desde Pixabay
- SEO optimizado
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
MODELO = "gemini-2.5-flash-lite"

# ── Voz ────────────────────────────────────────────────────────────────────────
# Masculina grave española — la más profunda disponible en edge-tts español
VOZ = "es-ES-AlvaroNeural"
VELOCIDAD = "-10%"   # Más lento = más solemne y estoico
PITCH = "-5Hz"       # Más grave

# ── Música de fondo (Pixabay — libre de copyright) ────────────────────────────
MUSICA_URLS = [
    "https://cdn.pixabay.com/download/audio/2022/03/10/audio_2dde668d05.mp3",  # Epic ambient
    "https://cdn.pixabay.com/download/audio/2023/01/10/audio_8ea684a6d0.mp3",  # Dark cinematic
    "https://cdn.pixabay.com/download/audio/2022/10/25/audio_946f8c0e5a.mp3",  # Meditation
]

# ── Banco de nichos ────────────────────────────────────────────────────────────
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

QUERIES_VIDEO = [
    "ancient rome cinematic",
    "philosophy nature contemplation",
    "dark moody atmospheric",
    "stoic warrior silhouette",
    "ancient greece ruins",
    "ocean meditation calm",
    "dark forest cinematic",
    "mountains epic landscape",
]

DESCRIPCION_TEMPLATE = """{hook}

🏛️ Canal de filosofía estoica y psicología aplicada.
📌 Un dato que cambia tu perspectiva — cada día.

✅ Suscribite para no perderte ninguno.

━━━━━━━━━━━━━━━━━━━━━━
🔎 SOBRE ESTE VIDEO
━━━━━━━━━━━━━━━━━━━━━━
{descripcion_extendida}

━━━━━━━━━━━━━━━━━━━━━━
📚 TAGS
━━━━━━━━━━━━━━━━━━━━━━
#shorts #estoicismo #filosofia #psicologia #mentalidad #viral
#marcaurelio #seneca #epicteto #sabiduria #motivacion #reflexion
#crecimientopersonal #inteligenciaemocional #datos #curiosidades
"""

TAGS = [
    "shorts", "estoicismo", "filosofia estoica", "psicologia",
    "mentalidad", "marco aurelio", "seneca", "epicteto",
    "sabiduria", "motivacion", "reflexion", "crecimiento personal",
    "inteligencia emocional", "datos curiosos", "curiosidades",
    "filosofia", "viral", "argentina", "mente", "autoconocimiento",
]

# ── Paso 1: Guion + SEO con Gemini ────────────────────────────────────────────

def generar_contenido(tema: str) -> dict:
    client = genai.Client(api_key=os.environ["GEMINI_API"])

    prompt = f"""Sos un experto en SEO de YouTube y creador de contenido filosófico viral en español.

TEMA: {tema}

Generá TODO el contenido necesario para un YouTube Short. Respondé ÚNICAMENTE con JSON válido, sin markdown.

{{
  "guion": "guion de 3 actos separados por | — máximo 55 palabras total. ACTO1: gancho impactante (10 palabras). ACTO2: desarrollo con el filósofo o concepto (30 palabras). ACTO3: cierre reflexivo que invite a suscribirse (15 palabras). Usá voseo argentino.",
  "titulo": "título YouTube optimizado SEO, máximo 60 caracteres, con 1 emoji al inicio, sin hashtags en el título",
  "hook_descripcion": "primera oración de la descripción — debe generar curiosidad, máximo 120 caracteres",
  "descripcion_extendida": "2-3 oraciones explicando el tema del video para SEO, máximo 200 caracteres",
  "filosofo": "nombre del filósofo si aplica, o null"
}}"""

    response = client.models.generate_content(model=MODELO, contents=prompt)
    texto = response.text.strip()
    texto = re.sub(r"```json\s*", "", texto)
    texto = re.sub(r"```\s*", "", texto).strip()

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        print(f"⚠️  JSON inválido, usando fallback")
        return {
            "guion": texto[:200],
            "titulo": f"🏛️ Sabiduría estoica del día",
            "hook_descripcion": "Una idea que cambia tu perspectiva.",
            "descripcion_extendida": f"Reflexión sobre {tema}.",
            "filosofo": None,
        }

# ── Paso 2: Audio ──────────────────────────────────────────────────────────────

async def generar_audio(texto: str) -> float:
    """Genera audio y retorna la duración en segundos."""
    comunicador = edge_tts.Communicate(texto, VOZ, rate=VELOCIDAD, pitch=PITCH)
    await comunicador.save("audio.mp3")

    # Obtener duración con ffprobe
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", "audio.mp3"],
        capture_output=True, text=True
    )
    duracion = float(result.stdout.strip()) if result.stdout.strip() else 30.0
    print(f"🔊 Audio generado — duración: {duracion:.1f}s")
    return duracion

# ── Paso 3: Subtítulos (método directo) ───────────────────────────────────────

async def generar_subtitulos(texto: str) -> None:
    """
    Genera subtítulos usando WordBoundary de edge-tts.
    Si falla, genera un .srt con timing estimado por palabras.
    """
    comunicador = edge_tts.Communicate(texto, VOZ, rate=VELOCIDAD, pitch=PITCH)
    palabras = []

    try:
        async for chunk in comunicador.stream():
            if chunk["type"] == "WordBoundary":
                palabras.append({
                    "word": chunk["text"],
                    "start": chunk["offset"] / 1e7,
                    "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                })
    except Exception as e:
        print(f"⚠️  WordBoundary falló: {e} — usando timing estimado")

    # Fallback: estimar timing por palabras (140 palabras/min habla lenta)
    if not palabras:
        lista = texto.split()
        seg_por_palabra = 60 / 120  # 120 palabras/min
        t = 0.5
        for w in lista:
            dur = len(w) * 0.07 + 0.15
            palabras.append({"word": w, "start": t, "end": t + dur})
            t += dur + 0.05

    # Agrupar de a 4 palabras
    def fmt(s: float) -> str:
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        ms = int((sec % 1) * 1000)
        return f"{int(h):02d}:{int(m):02d}:{int(sec):02d},{ms:03d}"

    with open("subs.srt", "w", encoding="utf-8") as f:
        i = 0
        idx = 1
        while i < len(palabras):
            grupo = palabras[i:i+4]
            texto_grupo = " ".join(p["word"] for p in grupo)
            inicio = grupo[0]["start"]
            fin = grupo[-1]["end"]
            f.write(f"{idx}\n{fmt(inicio)} --> {fmt(fin)}\n{texto_grupo}\n\n")
            idx += 1
            i += 4

    print(f"📝 Subtítulos: {idx-1} líneas")

# ── Paso 4: Música de fondo ────────────────────────────────────────────────────

def descargar_musica() -> bool:
    """Descarga una pista ambient. Retorna True si tuvo éxito."""
    url = random.choice(MUSICA_URLS)
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open("music.mp3", "wb") as f:
            f.write(r.content)
        print("🎵 Música descargada")
        return True
    except Exception as e:
        print(f"⚠️  Sin música: {e}")
        return False

# ── Paso 5: Video de fondo ─────────────────────────────────────────────────────

def descargar_video_fondo() -> None:
    query = random.choice(QUERIES_VIDEO)
    headers = {"Authorization": os.environ["PEXELS_API"]}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=15&orientation=portrait&size=medium"

    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    datos = r.json()

    if not datos.get("videos"):
        raise RuntimeError(f"Pexels sin resultados: {query}")

    # Filtrar videos de al menos 10 segundos
    videos = [v for v in datos["videos"] if v.get("duration", 0) >= 10]
    if not videos:
        videos = datos["videos"]  # fallback sin filtro

    video = random.choice(videos)
    archivos = video["video_files"]
    hd = [f for f in archivos if f.get("quality") in ("hd", "sd")]
    link = (hd[0] if hd else archivos[0])["link"]

    with open("raw.mp4", "wb") as f:
        f.write(requests.get(link, timeout=60).content)
    print(f"🎬 Video: {query} ({video.get('duration', '?')}s)")

# ── Paso 6: FFmpeg — ensamblar todo ───────────────────────────────────────────

def procesar_video(duracion_audio: float, tiene_musica: bool) -> None:
    """
    - Loop del video hasta cubrir el audio completo
    - Subtítulos quemados
    - Mezcla de voz + música ambient (música al 15% del volumen)
    """
    subs_abs = os.path.abspath("subs.srt")

    # Filtro de subtítulos
    sub_filter = (
        f"subtitles={subs_abs}:force_style='"
        "FontName=Arial Black,FontSize=20,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BackColour=&H80000000,"
        "Bold=1,Alignment=2,MarginV=100,"
        "BorderStyle=3,Outline=2'"
    )

    vf = (
        "scale=w=1080:h=1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,{sub_filter}"
    )

    if tiene_musica:
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", "raw.mp4",   # loop infinito del video
            "-i", "audio.mp3",
            "-stream_loop", "-1", "-i", "music.mp3", # loop de música
            "-filter_complex",
            # Mezcla: voz al 100%, música al 15%
            "[1:a]volume=1.0[voz];"
            "[2:a]volume=0.15[musica];"
            "[voz][musica]amix=inputs=2:duration=first[audio_final]",
            "-vf", vf,
            "-map", "0:v",
            "-map", "[audio_final]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(duracion_audio + 0.5),  # duración exacta del audio
            "-movflags", "+faststart",
            "final.mp4",
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", "raw.mp4",
            "-i", "audio.mp3",
            "-vf", vf,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(duracion_audio + 0.5),
            "-movflags", "+faststart",
            "final.mp4",
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg stderr:", result.stderr[-3000:])
        raise RuntimeError("FFmpeg falló")

    if not os.path.exists("final.mp4"):
        raise RuntimeError("FFmpeg no generó final.mp4")

    # Verificar duración del video final
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", "final.mp4"],
        capture_output=True, text=True
    )
    dur_final = float(probe.stdout.strip()) if probe.stdout.strip() else 0
    print(f"✂️  Video final: {dur_final:.1f}s — 1080x1920 con subtítulos")

# ── Paso 7: Subir a YouTube con SEO completo ──────────────────────────────────

def subir_a_youtube(datos: dict) -> None:
    info = json.loads(os.environ["YT_TOKEN"])
    creds = Credentials.from_authorized_user_info(info)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    yt = build("youtube", "v3", credentials=creds)

    titulo = datos.get("titulo", "🏛️ Sabiduría del día #shorts")[:100]
    descripcion = DESCRIPCION_TEMPLATE.format(
        hook=datos.get("hook_descripcion", ""),
        descripcion_extendida=datos.get("descripcion_extendida", ""),
    )

    body = {
        "snippet": {
            "title": titulo,
            "description": descripcion,
            "tags": TAGS,
            "categoryId": "27",        # Educación — mejor para este nicho
            "defaultLanguage": "es",
            "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "madeForKids": False,
        },
    }

    media = MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    response = yt.videos().insert(
        part="snippet,status", body=body, media_body=media
    ).execute()

    video_id = response.get("id", "")
    print(f"🚀 Subido: '{titulo}'")
    print(f"🔗 https://youtube.com/shorts/{video_id}")

# ── Flujo principal ────────────────────────────────────────────────────────────

async def fabricar_video(tema: str):
    print(f"\n{'='*55}")
    print(f"🎯 Tema: {tema}")
    print(f"{'='*55}\n")

    # 1. Contenido + SEO
    datos = generar_contenido(tema)
    guion_raw = datos.get("guion", tema)
    # Limpiar separadores de actos para el audio
    guion = guion_raw.replace("|", ". ").strip()
    print(f"📝 Guion: {guion}")
    print(f"🏷️  Título: {datos.get('titulo')}")

    # 2. Audio
    duracion = await generar_audio(guion)

    # 3. Subtítulos
    await generar_subtitulos(guion)

    # 4. Música
    tiene_musica = descargar_musica()

    # 5. Video de fondo
    descargar_video_fondo()

    # 6. FFmpeg
    procesar_video(duracion, tiene_musica)

    # 7. YouTube
    subir_a_youtube(datos)

    print(f"\n✅ ¡Short publicado!")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        tema_elegido = " ".join(sys.argv[1:])
    else:
        tema_elegido = random.choice(NICHOS_DEFAULT)
        print(f"ℹ️  Tema aleatorio seleccionado")

    asyncio.run(fabricar_video(tema_elegido))
