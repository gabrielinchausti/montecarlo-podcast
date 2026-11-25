# Montecarlo Podcast — Contexto del proyecto

## Qué es esto
Programa que graba 10 minutos del stream en vivo de **Radio Montecarlo (CX20,
930 AM, Uruguay)** de lunes a viernes a las 6:29 y a las 16:59 (hora
Montevideo) y lo publica como un podcast personal, para escucharlo en Apple
Podcasts.

Es el proyecto hermano de **podcast_eym** (mismo dueño, Gabriel Inchausti).

**Desde el 25/11/2026 todo corre en Google Cloud.** GitHub guarda solo el
código: no ejecuta nada ni almacena audio.

## Arquitectura

```
Cloud Scheduler  →  Cloud Run (job "grabar")  →  Cloud Storage  →  Apple Podcasts
 (el horario)         (graba y publica)           (MP3 + feed)
```

Proyecto de Google Cloud: `montecarlo-podcast`. Región: `us-central1`.
Facturación: "Mi cuenta de facturación 1" (paga), con alerta de presupuesto de
USD 5 por mes.

1. **Cloud Scheduler**: trabajos `montecarlo-manana` (`29 6 * * 1-5`) y
   `montecarlo-tarde` (`59 16 * * 1-5`), zona `America/Montevideo`, 3
   reintentos. Hacen `POST` a la API de Cloud Run para ejecutar el job.
2. **Cloud Run job `grabar`**: contenedor armado desde `nube/`. Tiempo máximo
   45 min, `--max-retries 1`. Variables: `BUCKET` (obligatoria),
   `DURACION_SEGUNDOS` (600) y `DIAS_A_GUARDAR` (3).
3. **Cloud Storage**: un depósito con `audio/`, `feed.xml` y `cover.jpg`. Es de
   descarga pública (`allUsers` con `roles/storage.legacyObjectReader`, que no
   permite listar). **El nombre del depósito NO se escribe en este repo**
   (es público y ese nombre es lo difícil de adivinar). Está en Cloud Shell en
   `~/bucket.txt`; también sale de `gcloud storage buckets list`.
4. **Identidad**: la cuenta de servicio
   `grabador@montecarlo-podcast.iam.gserviceaccount.com` ejecuta el job
   (`storage.objectAdmin` sobre el depósito) y es la que usa el Scheduler para
   dispararlo (`run.invoker` sobre el job).

No hay claves ni tokens que puedan vencer.

## Archivos
- `nube/grabar.py` — graba, sube el MP3, regenera el feed y borra lo viejo.
  Solo librería estándar de Python más `ffmpeg`.
- `nube/Dockerfile` — Alpine + `ffmpeg` + Python.
- `cover.jpg` — portada (1400×1400). La copia que se sirve está en el depósito.

## Cómo funciona `grabar.py`
- Si la grabación llega al menos a la mitad de la duración pedida, la publica.
  Si no, reintenta (hasta 6 intentos, 20 s entre medio); si ninguno llega,
  publica el más largo siempre que tenga al menos 1 minuto.
- Sube primero el MP3, después el feed y recién entonces borra los episodios
  de más de 3 días.
- El feed lleva tamaño y duración reales e `itunes:block` (no listado).

## Publicar un cambio
Commit y push desde la Mac, y después en **Cloud Shell**:

```bash
cd ~/montecarlo-podcast && git fetch --depth 1 origin main && git reset --hard origin/main
```

```bash
gcloud run jobs deploy grabar --source ~/montecarlo-podcast/nube --region us-central1
```

El push **no** actualiza Cloud Run por sí solo. El job debería conservar su
configuración al republicar; confirmarlo con
`gcloud run jobs describe grabar --region us-central1`.

## Operación y diagnóstico (en Cloud Shell)

```bash
gcloud config set project montecarlo-podcast
```

Grabar a mano:

```bash
gcloud run jobs execute grabar --region us-central1 --wait
```

Ver las últimas corridas:

```bash
gcloud run jobs executions list --job grabar --region us-central1 --limit 5
```

Ver los mensajes (del más nuevo al más viejo):

```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="grabar"' --limit 20 --format 'value(textPayload)'
```

Ver cuándo disparó un horario:

```bash
gcloud scheduler jobs describe montecarlo-manana --location us-central1 --format="yaml(state,schedule,scheduleTime,lastAttemptTime,status)"
```

## Cómo se armó (para rehacerlo desde cero)
APIs: `run`, `cloudbuild`, `artifactregistry`, `cloudscheduler`. La cuenta de
servicio por defecto de Compute necesita `roles/run.builder`. Depósito en
`us-central1` con `--uniform-bucket-level-access --no-public-access-prevention`.
Primer despliegue:

```bash
gcloud run jobs deploy grabar --source ~/montecarlo-podcast/nube --region us-central1 --service-account grabador@montecarlo-podcast.iam.gserviceaccount.com --set-env-vars BUCKET=$(cat ~/bucket.txt) --task-timeout 45m --max-retries 1
```

Cada horario:

```bash
gcloud scheduler jobs create http montecarlo-manana --location us-central1 --schedule="29 6 * * 1-5" --time-zone="America/Montevideo" --uri="https://run.googleapis.com/v2/projects/montecarlo-podcast/locations/us-central1/jobs/grabar:run" --http-method POST --oauth-service-account-email grabador@montecarlo-podcast.iam.gserviceaccount.com --max-retry-attempts 3
```

## Costos
Pensado para entrar en la capa gratuita, que se calcula por cuenta de
facturación (la comparten todos los proyectos): 5 GB de Storage (solo regiones
de EE. UU. elegibles), 240.000 vCPU-segundos de Cloud Run, 3 trabajos de
Scheduler (acá se usan 2) y 0,5 GB de Artifact Registry. Cada despliegue
agrega una imagen al repositorio `cloud-run-source-deploy`, así que conviene
revisar cada tanto que no pase de 0,5 GB. **Falta confirmar en Facturación,
tras unos días, que el costo real sea cero.**

## Pendientes
- Confirmar que el disparo **automático** funcione a su hora (la primera es la
  del 25/11/2026 a las 16:59).
- **Aviso por correo cuando falle una grabación** (Google no avisa por
  defecto).
- Borrar el job de prueba `prueba-radio`, su imagen y la carpeta `~/prueba` de
  Cloud Shell.
- Borrar el respaldo `~/respaldo-montecarlo-podcast.git` de la Mac cuando ya
  no haga falta.
- Decidir qué hacer con las ramas viejas `con-openai` y `stream-directo`.

## Problemas conocidos
- **Stream inestable**: `streamingcasazorrilla.innovanexo.com:8000` redirige a
  un backend rotativo y a veces `ffmpeg` falla con `[tls] An unexpected TLS
  packet was received` (9/9 y 29/9/2026, en GitHub Actions). Los reintentos de
  `grabar.py` apuntan a esto.
- **Scheduler recién habilitado**: el 25/11/2026 los primeros disparos manuales
  tardaron unos minutos en ejecutarse (estado `code: -1`) y después funcionó.
  La causa no se confirmó.
- **Apple Podcasts puede tardar** en mostrar episodios nuevos: el programa está
  agregado por URL y la app consulta el feed en su propio horario.

## Historial (para no repetir indagación)
1. Bajaba grabaciones de **radiocut.fm**; se cambió por `ffmpeg` contra el
   stream.
2. Una versión grababa **1 hora** y usaba OpenAI para ubicar el informativo; se
   cambió por "10 minutos a hora fija".
3. **GitHub Actions** (julio a noviembre de 2026): disparo desde cron-job.org
   con un token, MP3 commiteado al repo y feed servido por GitHub Pages. Se
   retiró el 25/11/2026 por el riesgo de que GitHub suspenda la cuenta por usar
   Actions para tareas ajenas al código. Ese día también se borraron las
   releases viejas con audio y se aplastó el historial de `main`. Hay un
   respaldo espejo del historial anterior al 1/11/2026 en
   `~/respaldo-montecarlo-podcast.git`.

## Cómo trabajar con Gabriel
- Hablarle en español (rioplatense). Explicar cada paso ANTES de ejecutarlo
  — le gusta entender qué se va a hacer y por qué, no que se corran cosas de
  sopetón.
- Pedir confirmación explícita antes de cualquier `commit`/`push` al repo.
- Ir de a partes chicas, verificando entendimiento compartido antes de avanzar.
- Preferencia clara: nada depende de la máquina local. El código vive en GitHub
  y el audio y el feed en Google Cloud Storage; no proponer guardado local.
- Conoce Git de proyectos anteriores (commits, branches, rebase vs merge)
  pero agradece que se le expliquen comandos nuevos.
