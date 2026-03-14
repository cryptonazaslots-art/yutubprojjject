"""
ViralEngine V7
Fixes:
- Video: descarga 3 clips de Pexels y los concatena → nunca más bucle de 3s
- Subtítulos: WordBoundary real con stream dedicado → sincronización exacta
- Estilo: una palabra por vez, grande, amarillo en palabras clave (Hormozi)
- Gancho: texto en pantalla los primeros 2 segundos antes de la voz
"""

import os, sys, asyncio, json, re, requests, random, subprocess, tempfile
from google import genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import edge_tts

MODELO  = "gemini-2.5-flash-lite"
VOZ     = "es-ES-AlvaroNeural"
VELOCIDAD = "-8%"
PITCH     = "-4Hz"

MUSICA_URLS = [
    "https://cdn.pixabay.com/download/audio/2022/03/10/audio_2dde668d05.mp3",
    "https://cdn.pixabay.com/download/audio/2023/01/10/audio_8ea684a6d0.mp3",
    "https://cdn.pixabay.com/download/audio/2022/10/25/audio_946f8c0e5a.mp3",
]

NICHOS_DEFAULT = [
    "Marco Aurelio y el control de las emociones",
    "Séneca sobre el uso del tiempo",
    "Epicteto y la dicotomía del control",
    "el efecto ancla en decisiones cotidianas",
    "sesgo de confirmación: por qué creemos lo que creemos",
    "la historia perturbadora del experimento de Milgram",
    "el estoicismo aplicado al trabajo moderno",
    "por qué el cerebro humano sabotea tus propias metas",
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

# Palabras que van en amarillo en los subtítulos (alto impacto semántico)
PALABRAS_CLAVE = {
    "nunca","jamás","secreto","nadie","todo","nada","siempre","verdad",
    "mentira","miedo","poder","libre","muerte","vida","mente","control",
    "trampa","error","clave","único","real","falso","hoy","ya","basta",
    "stop","atención","cuidado","peligro","importante","crítico","urgente",
    "descubrí","probado","científico","demostrado","sorprendente","increíble",
}

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
    "shorts","estoicismo","filosofia estoica","psicologia","mentalidad",
    "marco aurelio","seneca","epicteto","sabiduria","motivacion","reflexion",
    "crecimiento personal","inteligencia emocional","datos curiosos",
    "curiosidades","filosofia","viral","argentina","mente","autoconocimiento",
]

# ─────────────────────────────────────────────────────────────────────────────
# 1. Contenido + SEO
# ─────────────────────────────────────────────────────────────────────────────

def generar_contenido(tema: str) -> dict:
    client = genai.Client(api_key=os.environ["GEMINI_API"])
    prompt = f"""Sos un experto en SEO de YouTube y creador de contenido filosófico viral en español.

TEMA: {tema}

Generá TODO el contenido para un YouTube Short de 35-50 segundos.
El guion DEBE tener entre 90 y 110 palabras — esto es CRÍTICO para la duración.

Respondé ÚNICAMENTE con JSON válido, sin markdown, sin backticks.

{{
  "guion": "guion 90-110 palabras. GANCHO: 15 palabras impactantes. DESARROLLO: 60 palabras con filósofo/científico y ejemplo concreto. CIERRE: 15 palabras reflexivas invitando a suscribirse. Voseo argentino. Sin separadores.",
  "gancho_pantalla": "frase de máximo 6 palabras para mostrar en pantalla los primeros 2 segundos. Debe generar shock o curiosidad extrema.",
  "titulo": "título YouTube SEO, máximo 60 caracteres, con 1 emoji al inicio",
  "hook_descripcion": "primera oración descripción generando curiosidad, máximo 120 caracteres",
  "descripcion_extendida": "2-3 oraciones SEO sobre el tema, máximo 250 caracteres",
  "filosofo": "nombre del filósofo si aplica, o null"
}}"""

    response = client.models.generate_content(model=MODELO, contents=prompt)
    texto = re.sub(r"```json\s*|```\s*", "", response.text.strip()).strip()

    try:
        data = json.loads(texto)
        palabras = len(data.get("guion","").split())
        print(f"📊 Guion: {palabras} palabras")
        if palabras < 70:
            print("⚠️  Guion muy corto, reintentando...")
            return generar_contenido(tema)
        return data
    except json.JSONDecodeError:
        print(f"⚠️  JSON inválido, usando fallback")
        return {
            "guion": texto[:500],
            "gancho_pantalla": "¿Lo sabías?",
            "titulo": "🏛️ Sabiduría estoica del día",
            "hook_descripcion": "Una idea que cambia tu perspectiva.",
            "descripcion_extendida": f"Reflexión sobre {tema}.",
            "filosofo": None,
        }

# ─────────────────────────────────────────────────────────────────────────────
# 2. Audio + WordBoundary preciso
# ─────────────────────────────────────────────────────────────────────────────

async def generar_audio_y_tiempos(texto: str) -> tuple[float, list[dict]]:
    """
    Hace DOS pasadas:
    - Pasada 1: stream completo para capturar WordBoundary con tiempos exactos
    - Pasada 2: save() para guardar el archivo de audio
    Esto evita el problema de que stream() y save() interfieran entre sí.
    """
    # Pasada 1: capturar tiempos
    palabras = []
    com1 = edge_tts.Communicate(texto, VOZ, rate=VELOCIDAD, pitch=PITCH)
    async for chunk in com1.stream():
        if chunk["type"] == "WordBoundary":
            palabras.append({
                "word":  chunk["text"],
                "start": chunk["offset"] / 1e7,
                "end":   (chunk["offset"] + chunk["duration"]) / 1e7,
            })

    # Pasada 2: guardar audio
    com2 = edge_tts.Communicate(texto, VOZ, rate=VELOCIDAD, pitch=PITCH)
    await com2.save("audio.mp3")

    # Duración real con ffprobe
    r = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1","audio.mp3"],
        capture_output=True, text=True
    )
    duracion = float(r.stdout.strip()) if r.stdout.strip() else 40.0

    print(f"🔊 Audio: {duracion:.1f}s — {len(palabras)} palabras detectadas")

    # Fallback si WordBoundary no funcionó
    if not palabras:
        print("⚠️  WordBoundary sin datos, usando timing estimado")
        lista = texto.split()
        seg = duracion / max(len(lista), 1)
        t = 0.2
        for w in lista:
            palabras.append({"word": w, "start": t, "end": t + seg * 0.9})
            t += seg

    return duracion, palabras

# ─────────────────────────────────────────────────────────────────────────────
# 3. Subtítulos .ASS estilo Hormozi (una palabra por vez)
# ─────────────────────────────────────────────────────────────────────────────

def generar_subtitulos_hormozi(palabras: list[dict], gancho: str, duracion_total: float) -> None:
    """
    - Una palabra por línea, centrada, grande (80px)
    - Palabras clave → amarillo brillante
    - Resto → blanco con borde negro grueso
    - Gancho en pantalla los primeros 1.8s (antes de que empiece la voz)
    """

    def fmt(s: float) -> str:
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sc = s % 60
        cs = int((sc % 1) * 100)
        return f"{h}:{m:02d}:{int(sc):02d}.{cs:02d}"

    header = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Normal,Arial Black,80,&H00FFFFFF,&H000000FF,&H00000000,&HAA000000,-1,0,0,0,100,100,2,0,1,4,0,2,60,60,200,1
Style: Key,Arial Black,80,&H0000FFFF,&H000000FF,&H00000000,&HAA000000,-1,0,0,0,100,100,2,0,1,4,0,2,60,60,200,1
Style: Gancho,Arial Black,72,&H00FFFFFF,&H000000FF,&H00000000,&HAA000000,-1,0,0,0,100,100,2,0,1,5,0,5,60,60,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Ajustar tiempos si la primera palabra empieza antes de 2s
    # (dejamos espacio para el gancho visual)
    offset = 0.0
    if palabras and palabras[0]["start"] < 2.0:
        offset = 2.0 - palabras[0]["start"]

    with open("subs.ass", "w", encoding="utf-8") as f:
        f.write(header)

        # Línea del gancho (primeros 1.8 segundos)
        if gancho:
            f.write(f"Dialogue: 0,{fmt(0.1)},{fmt(1.8)},Gancho,,0,0,0,,{gancho}\n")

        # Una palabra por línea con estilo según si es clave o no
        for p in palabras:
            inicio = p["start"] + offset
            fin    = p["end"]   + offset
            # Clamp para no pasarse de la duración total
            fin = min(fin, duracion_total - 0.05)
            if inicio >= duracion_total:
                break

            word_lower = p["word"].lower().strip("¿?¡!.,;:")
            estilo = "Key" if word_lower in PALABRAS_CLAVE else "Normal"
            # Limpiar caracteres especiales de ASS
            word_clean = p["word"].replace("{","").replace("}","")
            f.write(f"Dialogue: 0,{fmt(inicio)},{fmt(fin)},{estilo},,0,0,0,,{word_clean}\n")

    print(f"📝 Subtítulos Hormozi: {len(palabras)} palabras")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Música
# ─────────────────────────────────────────────────────────────────────────────

def descargar_musica() -> bool:
    try:
        url = random.choice(MUSICA_URLS)
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open("music.mp3","wb") as f: f.write(r.content)
        print("🎵 Música descargada")
        return True
    except Exception as e:
        print(f"⚠️  Sin música: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# 5. Video de fondo — descarga 3 clips y los concatena
# ─────────────────────────────────────────────────────────────────────────────

def descargar_y_concatenar_videos(duracion_necesaria: float) -> None:
    """
    Descarga hasta 3 clips de Pexels con distintas queries.
    Los concatena con FFmpeg hasta cubrir la duración necesaria.
    Nunca más bucle de 3 segundos.
    """
    headers  = {"Authorization": os.environ["PEXELS_API"]}
    queries  = random.sample(QUERIES_VIDEO, 3)
    archivos = []

    for i, query in enumerate(queries):
        url = (f"https://api.pexels.com/videos/search"
               f"?query={query}&per_page=10&orientation=portrait&size=large")
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            datos = r.json()
            videos = datos.get("videos", [])
            if not videos:
                continue

            # Preferir clips de al menos 8 segundos
            largos = [v for v in videos if v.get("duration", 0) >= 8]
            video  = random.choice(largos if largos else videos)
            files  = video["video_files"]

            # Mejor calidad disponible
            hd = [f for f in files if f.get("height", 0) >= 1080]
            sd = [f for f in files if f.get("quality") == "hd"]
            link = (hd[0] if hd else (sd[0] if sd else files[0]))["link"]

            fname = f"clip_{i}.mp4"
            content = requests.get(link, timeout=60).content
            with open(fname, "wb") as f: f.write(content)

            # Verificar duración real del clip
            probe = subprocess.run(
                ["ffprobe","-v","error","-show_entries","format=duration",
                 "-of","default=noprint_wrappers=1:nokey=1", fname],
                capture_output=True, text=True
            )
            dur_clip = float(probe.stdout.strip()) if probe.stdout.strip() else 0
            print(f"🎬 Clip {i+1}: {query} — {dur_clip:.1f}s")
            archivos.append(fname)

        except Exception as e:
            print(f"⚠️  Clip {i+1} falló: {e}")

    if not archivos:
        raise RuntimeError("No se pudo descargar ningún clip de Pexels")

    if len(archivos) == 1:
        # Solo un clip: usar stream_loop como fallback
        os.rename(archivos[0], "raw.mp4")
        print("ℹ️  Un solo clip — se usará loop si es necesario")
        return

    # Normalizar todos los clips al mismo formato antes de concatenar
    clips_norm = []
    for i, clip in enumerate(archivos):
        norm = f"norm_{i}.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", clip,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-an",  # sin audio en los clips de fondo
            norm
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            clips_norm.append(norm)

    # Crear lista de concatenación
    with open("concat.txt", "w") as f:
        for c in clips_norm:
            f.write(f"file '{os.path.abspath(c)}'\n")

    # Concatenar
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", "concat.txt",
        "-c", "copy", "raw.mp4"
    ]
    result = subprocess.run(cmd_concat, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback: usar solo el primer clip con loop
        os.rename(clips_norm[0], "raw.mp4")
        print("⚠️  Concatenación falló, usando primer clip con loop")
    else:
        # Verificar duración total
        probe = subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1","raw.mp4"],
            capture_output=True, text=True
        )
        dur_total = float(probe.stdout.strip()) if probe.stdout.strip() else 0
        print(f"✅ Video concatenado: {dur_total:.1f}s totales")

# ─────────────────────────────────────────────────────────────────────────────
# 6. FFmpeg final
# ─────────────────────────────────────────────────────────────────────────────

def procesar_video(duracion_audio: float, tiene_musica: bool) -> None:
    subs_abs = os.path.abspath("subs.ass")
    duracion_total = duracion_audio + 2.5  # +2.5s para el gancho inicial

    vf = (
        "scale=w=1080:h=1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,ass={subs_abs}"
    )

    # El audio empieza 2 segundos después para dar tiempo al gancho visual
    audio_filter = "[1:a]adelay=2000|2000[voz_delayed];"

    if tiene_musica:
        af = (
            audio_filter +
            "[2:a]volume=0.12[musica];"
            "[voz_delayed][musica]amix=inputs=2:duration=first[audio_final]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", "raw.mp4",
            "-i", "audio.mp3",
            "-stream_loop", "-1", "-i", "music.mp3",
            "-filter_complex", af,
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
        af = audio_filter + "[voz_delayed]aformat=sample_fmts=fltp[audio_final]"
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", "raw.mp4",
            "-i", "audio.mp3",
            "-filter_complex", af,
            "-vf", vf,
            "-map", "0:v",
            "-map", "[audio_final]",
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
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1","final.mp4"],
        capture_output=True, text=True
    )
    dur = float(probe.stdout.strip()) if probe.stdout.strip() else 0
    print(f"✂️  Video final: {dur:.1f}s — 1080x1920 con subtítulos Hormozi")

# ─────────────────────────────────────────────────────────────────────────────
# 7. YouTube
# ─────────────────────────────────────────────────────────────────────────────

def subir_a_youtube(datos: dict) -> None:
    info  = json.loads(os.environ["YT_TOKEN"])
    creds = Credentials.from_authorized_user_info(info)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    yt = build("youtube","v3",credentials=creds)

    titulo = datos.get("titulo","🏛️ Sabiduría estoica del día")[:100]
    descripcion = DESCRIPCION_TEMPLATE.format(
        hook=datos.get("hook_descripcion",""),
        descripcion_extendida=datos.get("descripcion_extendida",""),
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
    media    = MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    response = yt.videos().insert(
        part="snippet,status", body=body, media_body=media
    ).execute()
    vid = response.get("id","")
    print(f"🚀 Subido: '{titulo}'")
    print(f"🔗 https://youtube.com/shorts/{vid}")

# ─────────────────────────────────────────────────────────────────────────────
# Flujo principal
# ─────────────────────────────────────────────────────────────────────────────

async def fabricar_video(tema: str):
    print(f"\n{'='*55}\n🎯 Tema: {tema}\n{'='*55}\n")

    # 1. Contenido
    datos  = generar_contenido(tema)
    guion  = datos.get("guion", tema).strip()
    gancho = datos.get("gancho_pantalla", "¿Lo sabías?")
    titulo = datos.get("titulo","🏛️ Sabiduría del día")
    print(f"📝 Guion ({len(guion.split())} palabras): {guion[:80]}...")
    print(f"⚡ Gancho: {gancho}")
    print(f"🏷️  Título: {titulo}")

    # 2. Audio + tiempos precisos
    duracion, palabras = await generar_audio_y_tiempos(guion)

    # 3. Subtítulos Hormozi sincronizados
    generar_subtitulos_hormozi(palabras, gancho, duracion + 2.5)

    # 4. Música
    tiene_musica = descargar_musica()

    # 5. Video (3 clips concatenados)
    descargar_y_concatenar_videos(duracion + 3)

    # 6. FFmpeg
    procesar_video(duracion, tiene_musica)

    # 7. YouTube
    subir_a_youtube(datos)

    print("\n✅ ¡Short publicado!")


if __name__ == "__main__":
    tema = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else random.choice(NICHOS_DEFAULT)
    if len(sys.argv) == 1:
        print("ℹ️  Tema aleatorio")
    asyncio.run(fabricar_video(tema))
