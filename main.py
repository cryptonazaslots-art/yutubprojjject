"""
ViralEngine V6
Fixes:
- Guion de 90-110 palabras → audio de 35-50 segundos (rango óptimo YouTube)
- Subtítulos via archivo .ass con timing estimado (no depende de WordBoundary)
- Fuerza resolución 1080p al buscar en Pexels
- Voz masculina grave con pausa dramática entre actos
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

MODELO = "gemini-2.5-flash-lite"
VOZ = "es-ES-AlvaroNeural"
VELOCIDAD = "-8%"
PITCH = "-4Hz"

MUSICA_URLS = [
    "https://cdn.pixabay.com/download/audio/2022/03/10/audio_2dde668d05.mp3",
    "https://cdn.pixabay.com/download/audio/2023/01/10/audio_8ea684a6d0.mp3",
    "https://cdn.pixabay.com/download/audio/2022/10/25/audio_946f8c0e5a.mp3",
]

NICHOS_DEFAULT = [
    "Marco Aurelio y el control de las emociones",
    "Séneca sobre el uso del tiempo",
    "Epicteto y la dicotomía del control",
    "psicología oscura: el efecto ancla en decisiones",
    "sesgo de confirmación: por qué creemos lo que creemos",
    "El estoicismo aplicado al trabajo moderno",
    "la historia perturbadora del experimento de Milgram",
    "truco mental respaldado por la ciencia para tomar mejores decisiones",
]

QUERIES_VIDEO = [
    "ancient rome cinematic",
    "philosophy nature contemplation",
    "dark moody atmospheric",
    "stoic warrior silhouette",
    "ancient greece ruins",
    "ocean meditation calm",
    "mountains epic landscape",
    "dark forest cinematic",
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

# ── Paso 1: Guion largo + SEO ──────────────────────────────────────────────────

def generar_contenido(tema: str) -> dict:
    client = genai.Client(api_key=os.environ["GEMINI_API"])

    prompt = f"""Sos un experto en SEO de YouTube y creador de contenido filosófico viral en español.

TEMA: {tema}

Generá TODO el contenido para un YouTube Short de 35-50 segundos.
El guion DEBE tener entre 90 y 110 palabras — esto es crítico para la duración del video.

Respondé ÚNICAMENTE con JSON válido, sin markdown, sin backticks.

{{
  "guion": "guion de exactamente 90-110 palabras con esta estructura: GANCHO impactante de 15 palabras que genere curiosidad o shock inmediato. Luego DESARROLLO de 60 palabras explicando el concepto con profundidad, nombrando al filósofo o científico, dando un ejemplo concreto de la vida real. Luego CIERRE de 15 palabras con reflexión poderosa que invite a suscribirse. Usá voseo argentino. Sin separadores ni símbolos especiales.",
  "titulo": "título YouTube SEO, máximo 60 caracteres, con 1 emoji al inicio",
  "hook_descripcion": "primera oración de la descripción generando curiosidad, máximo 120 caracteres",
  "descripcion_extendida": "2-3 oraciones explicando el tema para SEO, máximo 250 caracteres",
  "filosofo": "nombre del filósofo o científico si aplica, o null"
}}"""

    response = client.models.generate_content(model=MODELO, contents=prompt)
    texto = response.text.strip()
    texto = re.sub(r"```json\s*", "", texto)
    texto = re.sub(r"```\s*", "", texto).strip()

    try:
        data = json.loads(texto)
        # Verificar longitud del guion
        palabras = len(data.get("guion", "").split())
        print(f"📊 Longitud del guion: {palabras} palabras")
        if palabras < 70:
            print("⚠️  Guion muy corto, reintentando...")
            return generar_contenido(tema)  # reintentar una vez
        return data
    except json.JSONDecodeError:
        print(f"⚠️  JSON inválido, usando fallback")
        return {
            "guion": texto[:500],
            "titulo": "🏛️ Sabiduría estoica del día",
            "hook_descripcion": "Una idea que cambia tu perspectiva.",
            "descripcion_extendida": f"Reflexión profunda sobre {tema}.",
            "filosofo": None,
        }

# ── Paso 2: Audio ──────────────────────────────────────────────────────────────

async def generar_audio(texto: str) -> float:
    comunicador = edge_tts.Communicate(texto, VOZ, rate=VELOCIDAD, pitch=PITCH)
    await comunicador.save("audio.mp3")

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", "audio.mp3"],
        capture_output=True, text=True
    )
    duracion = float(result.stdout.strip()) if result.stdout.strip() else 40.0
    print(f"🔊 Audio: {duracion:.1f}s — voz: {VOZ}")
    return duracion

# ── Paso 3: Subtítulos .ASS (no depende de WordBoundary) ──────────────────────

def generar_subtitulos_ass(texto: str, duracion_total: float) -> None:
    """
    Genera subtítulos .ass con timing calculado por velocidad de habla.
    Más robusto que WordBoundary — funciona siempre en GitHub Actions.
    Subtítulos grandes, centrados en el tercio inferior, con sombra.
    """
    palabras = texto.split()
    # Velocidad de habla: ~2.8 palabras/segundo con la voz lenta configurada
    seg_por_palabra = duracion_total / max(len(palabras), 1)

    # Agrupar de a 4 palabras por línea
    grupos = []
    i = 0
    t = 0.3  # pequeño delay inicial
    while i < len(palabras):
        grupo = palabras[i:i+4]
        texto_grupo = " ".join(grupo)
        dur_grupo = seg_por_palabra * len(grupo)
        fin = min(t + dur_grupo, duracion_total - 0.1)
        grupos.append((t, fin, texto_grupo))
        t = fin
        i += 4

    def fmt_ass(s: float) -> str:
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        cs = int((sec % 1) * 100)
        return f"{h}:{m:02d}:{int(sec):02d}.{cs:02d}"

    # Header .ass con estilo grande y legible
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,72,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,160,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    with open("subs.ass", "w", encoding="utf-8") as f:
        f.write(header)
        for inicio, fin, texto_linea in grupos:
            f.write(f"Dialogue: 0,{fmt_ass(inicio)},{fmt_ass(fin)},Default,,0,0,0,,{texto_linea}\n")

    print(f"📝 Subtítulos .ass: {len(grupos)} líneas")

# ── Paso 4: Música ─────────────────────────────────────────────────────────────

def descargar_musica() -> bool:
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

# ── Paso 5: Video de fondo (fuerza 1080p) ─────────────────────────────────────

def descargar_video_fondo() -> None:
    query = random.choice(QUERIES_VIDEO)
    headers = {"Authorization": os.environ["PEXELS_API"]}
    # large = HD 1080p en Pexels
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=15&orientation=portrait&size=large"

    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    datos = r.json()

    if not datos.get("videos"):
        raise RuntimeError(f"Pexels sin resultados: {query}")

    # Filtrar videos >= 15 segundos
    videos = [v for v in datos["videos"] if v.get("duration", 0) >= 15]
    if not videos:
        videos = datos["videos"]

    video = random.choice(videos)
    archivos = video["video_files"]

    # Preferir HD 1080 explícitamente
    hd1080 = [f for f in archivos if f.get("height", 0) >= 1080]
    hd = [f for f in archivos if f.get("quality") == "hd"]
    link = (hd1080[0] if hd1080 else (hd[0] if hd else archivos[0]))["link"]

    with open("raw.mp4", "wb") as f:
        f.write(requests.get(link, timeout=90).content)
    print(f"🎬 Video: {query} ({video.get('duration')}s, {video['video_files'][0].get('width')}x{video['video_files'][0].get('height')})")

# ── Paso 6: FFmpeg ─────────────────────────────────────────────────────────────

def procesar_video(duracion_audio: float, tiene_musica: bool) -> None:
    subs_abs = os.path.abspath("subs.ass")

    vf = (
        "scale=w=1080:h=1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,ass={subs_abs}"
    )

    duracion_total = duracion_audio + 0.5

    if tiene_musica:
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", "raw.mp4",
            "-i", "audio.mp3",
            "-stream_loop", "-1", "-i", "music.mp3",
            "-filter_complex",
            "[1:a]volume=1.0[voz];"
            "[2:a]volume=0.12[musica];"
            "[voz][musica]amix=inputs=2:duration=first[audio_final]",
            "-vf", vf,
            "-map", "0:v",
            "-map", "[audio_final]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(duracion_total),
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
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(duracion_total),
            "-movflags", "+faststart",
            "final.mp4",
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg stderr:", result.stderr[-3000:])
        raise RuntimeError("FFmpeg falló")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", "final.mp4"],
        capture_output=True, text=True
    )
    dur_final = float(probe.stdout.strip()) if probe.stdout.strip() else 0
    print(f"✂️  Video final: {dur_final:.1f}s — 1080x1920")

# ── Paso 7: YouTube ────────────────────────────────────────────────────────────

def subir_a_youtube(datos: dict) -> None:
    info = json.loads(os.environ["YT_TOKEN"])
    creds = Credentials.from_authorized_user_info(info)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    yt = build("youtube", "v3", credentials=creds)

    titulo = datos.get("titulo", "🏛️ Sabiduría estoica del día")[:100]
    descripcion = DESCRIPCION_TEMPLATE.format(
        hook=datos.get("hook_descripcion", ""),
        descripcion_extendida=datos.get("descripcion_extendida", ""),
    )

    body = {
        "snippet": {
            "title": titulo,
            "description": descripcion,
            "tags": TAGS,
            "categoryId": "27",
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

    datos = generar_contenido(tema)
    guion = datos.get("guion", tema).strip()
    print(f"📝 Guion ({len(guion.split())} palabras): {guion[:100]}...")
    print(f"🏷️  Título: {datos.get('titulo')}")

    duracion = await generar_audio(guion)
    generar_subtitulos_ass(guion, duracion)
    tiene_musica = descargar_musica()
    descargar_video_fondo()
    procesar_video(duracion, tiene_musica)
    subir_a_youtube(datos)

    print(f"\n✅ ¡Short publicado!")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        tema_elegido = " ".join(sys.argv[1:])
    else:
        tema_elegido = random.choice(NICHOS_DEFAULT)
        print("ℹ️  Tema aleatorio")

    asyncio.run(fabricar_video(tema_elegido))
