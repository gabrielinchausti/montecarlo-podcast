# Montecarlo Podcast — Contexto del proyecto

## Qué es esto
Pipeline que graba automáticamente 10 minutos del stream en vivo de **Radio
Montecarlo (CX20, 930 AM, Uruguay)** todos los días a las 6:29 (hora Montevideo)
y lo publica como episodio de un podcast personal, para escucharlo en Apple
Podcasts.

Es el proyecto hermano de **podcast_eym** (mismo dueño, Gabriel Inchausti,
misma arquitectura de distribución: GitHub Actions + repo + RSS servido por
GitHub Pages). A diferencia de `podcast_eym`, acá **todo el pipeline corre en
GitHub Actions** — no hace falta correr nada en la máquina local, porque
grabar un stream de audio no choca con bloqueos de IP como sí le pasa a
`podcast_eym` con El País.

## Arquitectura actual
1. **Disparo**: un servicio externo (cron-job.org) pega todos los días a las
   09:29 UTC (06:29 Montevideo) contra la API de GitHub para lanzar un evento
   `repository_dispatch` de tipo `grabar`. El workflow también admite
   `workflow_dispatch` para correrlo a mano.
2. **`.github/workflows/grabar.yml`** (`runs-on: ubuntu-latest`):
   - Instala `ffmpeg`.
   - Graba 10 minutos del stream (`https://streamingcasazorrilla.innovanexo.com:8000/montecarlo.mp3`)
     con `ffmpeg -t 600`, y nombra el archivo `episodio-<FECHA>-<HORA>.mp3`
     (fecha/hora en `TZ=America/Montevideo`).
   - Mueve el mp3 a `audio/` y lo commitea/pushea a `main`.
   - Espera 60s (para dar tiempo a que GitHub procese el push).
   - Corre `generar_rss.py`, que regenera `feed.xml` a partir de lo que haya
     en `audio/`, y lo commitea/pushea.
   - Borra los episodios de `audio/` con más de 7 días y commitea/pushea la
     limpieza.
3. **`generar_rss.py`**: script standalone (solo librería estándar de Python,
   sin dependencias). Lee `audio/episodio-*.mp3`, arma un `feed.xml` con
   metadata fija del programa (título, descripción, imagen de portada) y un
   `<item>` por episodio.
4. **Distribución**: `feed.xml` y `cover.jpg` se sirven directo desde GitHub
   Pages (rama `main`, raíz del repo — no hay carpeta `docs/`). No se usan
   GitHub Releases (a diferencia de `podcast_eym`): el audio se commitea
   directo al repo dentro de `audio/`.

## Archivos
- `.github/workflows/grabar.yml` — el workflow completo.
- `generar_rss.py` — genera/regenera `feed.xml` a partir de `audio/`.
- `feed.xml` — feed RSS servido por GitHub Pages.
- `cover.jpg` — imagen de portada del podcast (1400×1400, logo de Radio
  Montecarlo recortado a cuadrado con margen). Reemplazó a una URL externa
  del sitio de radiomontecarlo.com.uy.
- `.gitignore` — ignora `.DS_Store`.

## Historial de iteraciones (para no repetir indagación)
El proyecto pasó por varias versiones antes de llegar a la actual:
- Primero bajaba grabaciones de **radiocut.fm**; se abandonó por `ffmpeg`
  directo contra el stream.
- Hubo una versión que grababa **1 hora completa** y usaba OpenAI para
  detectar el tramo exacto del informativo dentro de esa hora; se abandonó
  por la versión simple de "grabar 10 minutos a una hora fija".
- El trigger pasó de `schedule` (cron nativo de GitHub Actions, poco preciso
  con el horario) a `repository_dispatch` disparado por cron-job.org.
- Hasta el 7 de julio, el mp3 se subía como **GitHub Release** (con
  `softprops/action-gh-release`) y `generar_rss.py` consultaba la API de
  Releases para armar el feed. El commit `f4ad0fb` ("cambio por grabar mp3 y
  pages para ganar estabilidad") lo reemplazó por el esquema actual: commit
  directo a `audio/` + servido por Pages.

## Bugs encontrados y corregidos (14 de julio de 2026)
1. **La limpieza de "más de 7 días" no borraba nada**: usaba
   `find audio/ -name "*.mp3" -mtime +7 -delete`, pero `actions/checkout`
   resetea el mtime de **todos** los archivos al momento del checkout en cada
   corrida — así que ningún archivo aparecía nunca como "viejo". Se corrigió
   parseando la fecha directamente del nombre del archivo
   (`episodio-YYYY-MM-DD-HHMM.mp3`) y comparándola contra la fecha actual.
2. **El mp3 quedaba duplicado**: el paso "Guardar MP3 en el repo" hacía `cp`
   del archivo grabado hacia `audio/`, pero nunca borraba el original de la
   raíz del workspace. El `git add -A` del paso de limpieza terminaba
   commiteando también esa copia suelta, duplicando el tamaño del repo cada
   día (~19 MB/día en vez de ~9,4 MB/día). Se corrigió usando `mv` en vez de
   `cp`. Se limpiaron los 4 duplicados que ya habían quedado commiteados
   (`episodio-2026-07-08/09/10/13-*.mp3` sueltos en la raíz).

## Riesgos conocidos / pendientes de revisar
- **9 de julio**: hubo una demora de ~3h34min entre el disparo del workflow
  (09:29 UTC) y el arranque real del job (13:03 UTC) — grabó a las 10:05 en
  vez de las 6:29. Parece haber sido congestión de runners de GitHub ese día,
  no un problema del repo.
- El workflow **no tiene `concurrency` configurado**. Si el disparo externo
  llegara a reintentar y dos corridas se solaparan, los `git push`
  secuenciales de cada paso podrían pisarse entre sí (no hay retry si un push
  falla por no ser fast-forward).
- `generar_rss.py` no pone límite a la cantidad de items del feed — depende
  por completo de que la limpieza de 7 días funcione (ya corregida arriba).
- Detalles menores sin corregir: `<enclosure length="0">` (no calcula bytes
  reales del mp3), `<itunes:duration>10:00</itunes:duration>` fijo (no mide
  la duración real si el stream corta antes de los 10 minutos).
- **Apple Podcasts puede tardar en mostrar episodios nuevos**: el show está
  agregado por URL directa (no por el directorio oficial de Apple), así que
  la app de Apple sondea el feed en su propio horario y no hay forma de
  forzarle un refresh inmediato desde acá. Un swipe de pull-to-refresh en la
  lista de episodios suele andar mejor que navegar para adelante y atrás.

## Credenciales
A diferencia de `podcast_eym`, este proyecto no usa OpenAI ni cookies de
sesión. Solo necesita el `GITHUB_TOKEN` automático de Actions (el workflow
declara `permissions: contents: write`) — no hay secrets adicionales
configurados.

## Cómo trabajar con Gabriel
- Hablarle en español (rioplatense). Explicar cada paso ANTES de ejecutarlo
  — le gusta entender qué se va a hacer y por qué, no que se corran cosas de
  sopetón.
- Pedir confirmación explícita antes de cualquier `commit`/`push` al repo.
- Ir de a partes chicas, verificando entendimiento compartido antes de avanzar.
- Preferencia clara: todo el almacenamiento (audio, feed, imagen) vive en
  GitHub, no en la máquina local — no proponer alternativas de guardado local.
- Conoce Git de proyectos anteriores (commits, branches, rebase vs merge)
  pero agradece que se le expliquen comandos nuevos.
