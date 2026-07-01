#!/usr/bin/env python3
"""
Genera el feed RSS del podcast a partir de los releases de GitHub.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime

# ─── Configuración ────────────────────────────────────────────────────────────
REPO        = os.environ.get("REPO", "TU_USUARIO/montecarlo-podcast")
TOKEN       = os.environ.get("GITHUB_TOKEN", "")
OWNER, NAME = REPO.split("/")
BASE_URL    = f"https://github.com/{REPO}/releases/download"
FEED_TITLE  = "Radio Montecarlo – Noticias"
FEED_DESC   = "Grabaciones de Radio Montecarlo CX20 930 AM, Uruguay."
FEED_LINK   = "https://www.radiomontecarlo.com.uy"
FEED_LANG   = "es-uy"
FEED_IMG    = "https://www.radiomontecarlo.com.uy/artworks/artworks_radiomontecarlocomuy/logos/logo_social.jpg"
MAX_EPS     = 30   # 3 episodios por día × 30 días
# ──────────────────────────────────────────────────────────────────────────────


def fetch_releases():
    url = f"https://api.github.com/repos/{REPO}/releases?per_page={MAX_EPS}"
    headers = {"User-Agent": "montecarlo-podcast-rss/1.0"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def release_to_item(release):
    tag = release["tag_name"]   # ep-2026-06-29-0628

    # Separar fecha y hora del tag
    partes = tag.replace("ep-", "").split("-")
    # partes = ['2026', '06', '29', '0628']
    fecha = "-".join(partes[:3])   # 2026-06-29
    hora  = partes[3] if len(partes) > 3 else "0000"  # 0628

    # Formatear hora para mostrar: 0628 → 06:28
    hora_display = f"{hora[:2]}:{hora[2:]}"

    # URL directa al MP3
    nombre  = f"episodio-{fecha}-{hora}"
    mp3_url = f"{BASE_URL}/{tag}/{nombre}.mp3"

    # Fecha en formato RFC 2822 para RSS
    try:
        dt       = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H%M")
        pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S -0300")
    except ValueError:
        pub_date = release.get("published_at", "")[:10]

    return f"""
    <item>
      <title>Montecarlo {hora_display} – {fecha}</title>
      <description>Grabación de Radio Montecarlo CX20 930 AM del {fecha} a las {hora_display}</description>
      <pubDate>{pub_date}</pubDate>
      <enclosure url="{mp3_url}" type="audio/mpeg" length="0"/>
      <guid isPermaLink="false">{mp3_url}</guid>
      <itunes:duration>5:00</itunes:duration>
      <itunes:explicit>no</itunes:explicit>
    </item>"""


def build_feed(items_xml: str) -> str:
    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{FEED_TITLE}</title>
    <link>{FEED_LINK}</link>
    <description>{FEED_DESC}</description>
    <language>{FEED_LANG}</language>
    <lastBuildDate>{now}</lastBuildDate>
    <itunes:author>Radio Montecarlo CX20 930 AM</itunes:author>
    <itunes:category text="News"/>
    <itunes:image href="{FEED_IMG}"/>
    <itunes:explicit>no</itunes:explicit>
    {items_xml}
  </channel>
</rss>
"""


def main():
    print("Obteniendo releases de GitHub...")
    try:
        releases = fetch_releases()
    except urllib.error.HTTPError as e:
        print(f"Error al consultar la API de GitHub: {e}")
        raise

    print(f"  → {len(releases)} releases encontrados")

    items_xml = "".join(release_to_item(r) for r in releases)
    feed      = build_feed(items_xml)

    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(feed)

    print("feed.xml generado correctamente.")


if __name__ == "__main__":
    main()