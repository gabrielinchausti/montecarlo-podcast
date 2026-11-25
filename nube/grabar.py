#!/usr/bin/env python3
"""
Graba la radio, publica el episodio en Cloud Storage y regenera el feed.
Corre como un job de Cloud Run. Usa solo la librería estándar y ffmpeg.

Variables de entorno:
  BUCKET             (obligatoria) nombre del depósito de Cloud Storage
  DURACION_SEGUNDOS  duración de la grabación (por defecto 600)
  DIAS_A_GUARDAR     antigüedad máxima de los episodios (por defecto 3)
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.utils import format_datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

BUCKET = os.environ.get("BUCKET", "")
DURACION = int(os.environ.get("DURACION_SEGUNDOS", "600"))
DIAS_A_GUARDAR = int(os.environ.get("DIAS_A_GUARDAR", "3"))

STREAM_URL = "https://streamingcasazorrilla.innovanexo.com:8000/montecarlo.mp3"
ZONA = ZoneInfo("America/Montevideo")
KBPS = 128
INTENTOS = 6
ESPERA_ENTRE_INTENTOS = 20  # segundos

FEED_TITLE = "Radio Montecarlo – Noticias"
FEED_DESC = "Grabaciones de Radio Montecarlo CX20 930 AM, Uruguay."
FEED_LINK = "https://www.radiomontecarlo.com.uy"
FEED_LANG = "es-uy"
AUTOR = "Radio Montecarlo CX20 930 AM"

PATRON = re.compile(r"episodio-(\d{4}-\d{2}-\d{2}-\d{4})\.mp3$")
API = "https://storage.googleapis.com"
URL_TOKEN = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)


def log(mensaje):
    print(mensaje, flush=True)


# ---------------------------------------------------------------- grabación

def segundos_de(ruta):
    """Duración estimada de un MP3 de bitrate constante, a partir de su tamaño."""
    if not os.path.exists(ruta):
        return 0
    return os.path.getsize(ruta) * 8 / (KBPS * 1000)


def grabar(destino):
    comando = [
        "ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-loglevel", "warning",
        "-rw_timeout", "30000000",  # 30 s sin datos = error (en microsegundos)
        "-i", STREAM_URL,
        "-t", str(DURACION),
        "-acodec", "libmp3lame", "-b:a", f"{KBPS}k",
        "-y", destino,
    ]
    try:
        resultado = subprocess.run(comando, timeout=DURACION + 120)
        log(f"ffmpeg terminó con código {resultado.returncode}")
    except subprocess.TimeoutExpired:
        log("ffmpeg tardó demasiado y se interrumpió")
    return segundos_de(destino)


def grabar_con_reintentos(carpeta):
    """
    Se queda con la primera grabación que llegue a la mitad de la duración
    pedida. Si ninguna llega, usa la más larga (siempre que sirva de algo).
    """
    mejor = (0, None, None)  # segundos, ruta, nombre
    for intento in range(1, INTENTOS + 1):
        momento = datetime.now(ZONA)
        nombre = f"episodio-{momento:%Y-%m-%d-%H%M}.mp3"
        ruta = os.path.join(carpeta, f"intento-{intento}.mp3")
        log(f"Intento {intento} de {INTENTOS}: grabando {nombre}")
        segundos = grabar(ruta)
        log(f"Intento {intento}: se grabaron {segundos:.0f} de {DURACION} segundos")
        if segundos > mejor[0]:
            mejor = (segundos, ruta, nombre)
        if segundos >= DURACION / 2:
            break
        if intento < INTENTOS:
            time.sleep(ESPERA_ENTRE_INTENTOS)

    segundos, ruta, nombre = mejor
    if segundos < min(60, DURACION * 0.9):
        raise RuntimeError("No se pudo grabar el stream en ningún intento")
    return ruta, nombre


# ------------------------------------------------------------ Cloud Storage

def pedir(metodo, url, cabeceras, datos=None):
    """Pedido HTTP que reintenta ante errores pasajeros."""
    for intento in range(1, 5):
        pedido = urllib.request.Request(url, data=datos, headers=cabeceras, method=metodo)
        try:
            with urllib.request.urlopen(pedido, timeout=60) as respuesta:
                return respuesta.read()
        except urllib.error.HTTPError as error:
            if error.code < 500 and error.code != 429:
                raise
            fallo = error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            fallo = error
        if intento < 4:
            log(f"Error pasajero ({fallo}); reintento")
            time.sleep(2 ** intento)
    raise fallo


def obtener_autorizacion():
    """Credencial temporal que Google le entrega al job; no se guarda en ningún lado."""
    cuerpo = pedir("GET", URL_TOKEN, {"Metadata-Flavor": "Google"})
    return {"Authorization": f"Bearer {json.loads(cuerpo)['access_token']}"}


def subir(auth, nombre, datos, tipo, cache):
    url = f"{API}/{BUCKET}/{urllib.parse.quote(nombre)}"
    cabeceras = {**auth, "Content-Type": tipo, "Cache-Control": cache}
    pedir("PUT", url, cabeceras, datos)


def listar_episodios(auth):
    objetos, pagina = [], None
    while True:
        parametros = {"prefix": "audio/"}
        if pagina:
            parametros["pageToken"] = pagina
        url = f"{API}/storage/v1/b/{BUCKET}/o?{urllib.parse.urlencode(parametros)}"
        respuesta = json.loads(pedir("GET", url, auth))
        objetos += respuesta.get("items", [])
        pagina = respuesta.get("nextPageToken")
        if not pagina:
            return [o for o in objetos if PATRON.search(o["name"])]


def borrar(auth, nombre):
    url = f"{API}/storage/v1/b/{BUCKET}/o/{urllib.parse.quote(nombre, safe='')}"
    try:
        pedir("DELETE", url, auth)
    except urllib.error.HTTPError as error:
        if error.code != 404:  # 404 = ya no estaba
            raise


# --------------------------------------------------------------------- feed

def fecha_de(nombre):
    sello = PATRON.search(nombre).group(1)
    return datetime.strptime(sello, "%Y-%m-%d-%H%M").replace(tzinfo=ZONA)


def item_de(objeto):
    momento = fecha_de(objeto["name"])
    url = f"{API}/{BUCKET}/{objeto['name']}"
    bytes_ = int(objeto["size"])
    minutos, segundos = divmod(round(bytes_ * 8 / (KBPS * 1000)), 60)
    titulo = f"Montecarlo {momento:%H:%M} – {momento:%Y-%m-%d}"
    return f"""
    <item>
      <title>{escape(titulo)}</title>
      <description>Grabación del {momento:%Y-%m-%d} a las {momento:%H:%M} (hora Uruguay).</description>
      <pubDate>{format_datetime(momento)}</pubDate>
      <enclosure url="{escape(url)}" length="{bytes_}" type="audio/mpeg"/>
      <guid isPermaLink="true">{escape(url)}</guid>
      <itunes:duration>{minutos}:{segundos:02d}</itunes:duration>
      <itunes:explicit>no</itunes:explicit>
    </item>"""


def armar_feed(episodios):
    imagen = f"{API}/{BUCKET}/cover.jpg"
    ordenados = sorted(episodios, key=lambda o: o["name"], reverse=True)
    items = "".join(item_de(o) for o in ordenados)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{escape(FEED_TITLE)}</title>
    <description>{escape(FEED_DESC)}</description>
    <link>{FEED_LINK}</link>
    <language>{FEED_LANG}</language>
    <itunes:author>{escape(AUTOR)}</itunes:author>
    <itunes:category text="News"/>
    <itunes:explicit>no</itunes:explicit>
    <itunes:block>Yes</itunes:block>
    <itunes:image href="{imagen}"/>
    <image>
      <url>{imagen}</url>
      <title>{escape(FEED_TITLE)}</title>
      <link>{FEED_LINK}</link>
    </image>{items}
  </channel>
</rss>
"""


# ------------------------------------------------------------------- flujo

def publicar(ruta, nombre):
    auth = obtener_autorizacion()

    with open(ruta, "rb") as archivo:
        subir(auth, f"audio/{nombre}", archivo.read(), "audio/mpeg", "public, max-age=86400")
    log(f"Subido audio/{nombre}")

    limite = datetime.now(ZONA).date() - timedelta(days=DIAS_A_GUARDAR)
    episodios = listar_episodios(auth)
    vigentes = [o for o in episodios if fecha_de(o["name"]).date() >= limite]
    viejos = [o for o in episodios if fecha_de(o["name"]).date() < limite]

    # Primero el feed y después el borrado: así nunca apunta a un archivo que ya no está.
    subir(auth, "feed.xml", armar_feed(vigentes).encode("utf-8"),
          "application/rss+xml; charset=utf-8", "no-cache")
    log(f"Feed actualizado con {len(vigentes)} episodios")

    for objeto in viejos:
        borrar(auth, objeto["name"])
        log(f"Borrado {objeto['name']}")


def main():
    if not BUCKET:
        sys.exit("Falta la variable de entorno BUCKET")
    with tempfile.TemporaryDirectory() as carpeta:
        ruta, nombre = grabar_con_reintentos(carpeta)
        publicar(ruta, nombre)
    log("Listo")


if __name__ == "__main__":
    main()
