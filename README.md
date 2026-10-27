# Analizador Táctico — MVP de análisis post-partido

Sistema de análisis táctico para clubes de fútbol regional (Liga de San Francisco). Toma el video de un partido filmado con una cámara fija y produce:

- la posición de cada jugador en metros sobre la cancha;
- métricas de bloque;
- momentos para revisar;
- un dashboard para mirar el video y la cancha 2D sincronizados, taguear jugadas y calificar a los jugadores.

Funciona **100% sin internet**: en las canchas de la liga no hay conectividad confiable. La nube (Supabase) es opcional y se usa después, con un sync manual.

**Equipo (Lorenzatti – Tribolo – Pesce):** Santiago Lorenzatti (Product Manager & UX), Lucia Pesce (Lead AI & Computer Vision), Nicolas Tribolo (Full-Stack & Integración).

> La fuente de verdad sobre arquitectura y decisiones es `docs/context/` (en particular `arquitectura.md` y `decisiones.md`). Este README cubre instalar, usar y mantener el sistema.

---

## Qué hace

| Parte | Qué hace |
|---|---|
| **Detección y tracking** | Modelo propio RF-DETR Small, entrenado en Roboflow (jugador, arquero, árbitro y pelota), con seguimiento de ByteTrack (`src/detection/`) |
| **Homografía** | Calibración a mano por cámara, con control de calidad automático y verificación de que la cámara no se movió durante el video. Pasa los píxeles a metros, con las medidas reales de cada estadio (`src/homography/`) |
| **Análisis** | Equipo por color de camiseta, estadísticas por jugador, fases del bloque y "momentos para revisar". Los momentos son una señal experimental, no un diagnóstico (`src/analysis/`) |
| **Dashboard** | Mesa táctica (video y cancha 2D sincronizados, métricas, tagueo con un clic o con el teclado), Jugadores, Patrones y Semáforo de rendimiento (`app/`) |
| **Usuarios** | Login local con cuatro roles: administrador, analista, cuerpo técnico y solo lectura |
| **Datos** | SQLite local; respaldos automáticos y verificables; sync manual y opcional a Supabase |

---

## Requisitos

- **Python 3.12.** Las versiones de `requirements.txt` están probadas juntas con 3.12.
- **ffmpeg y ffprobe**, para generar el video anotado y cortar videos. En Mac: `brew install ffmpeg`.
- **Git.**
- **Disco:** ~3 GB para las dependencias (el detector trae PyTorch). Además, ~0,5 GB por partido procesado (video anotado y parquets).
- **Desarrollado y probado en macOS** con Apple Silicon: la inferencia usa CoreML (CPU + GPU). En otra plataforma, el dashboard funciona igual; la inferencia va a ser más lenta si no hay aceleración.
- **Solo para procesar videos nuevos:** una API key de Roboflow (`ROBOFLOW_API_KEY`). Para usar el dashboard sobre partidos ya procesados no hace falta.

---

## Instalación desde cero

```bash
# 1. Código
git clone <url-del-repo> Asistente_Tactico_FR
cd Asistente_Tactico_FR

# 2. Entorno y dependencias (fuera de iCloud Drive: ver "Problemas conocidos")
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Primer administrador (la contraseña se pide por teclado; mínimo 8 caracteres)
python3 scripts/usuarios.py crear <usuario> --nombre "Nombre Apellido" --rol admin

# 4. Levantar el dashboard
streamlit run app/main.py
#    → abre http://localhost:8501
```

La base de datos (`data/db/analizador.sqlite`) se crea sola. No hay scripts de migración: cada módulo de `src/db/` crea su tabla (`CREATE TABLE IF NOT EXISTS`) la primera vez que se usa.

### Probarlo sin un partido real

```bash
python3 scripts/make_sample_parquet.py   # crea data/outputs/demo_field.parquet (22 jugadores sintéticos)
python3 scripts/usuarios.py demo         # un usuario de prueba por rol, con contraseñas al azar
```

Al abrir el dashboard aparece el partido `demo_field`, sin video: solo la cancha y las métricas. Los usuarios `*_demo` son para una instalación de prueba o la defensa, **no para la laptop del club**. Se desactivan desde la vista Usuarios.

**Accesos de prueba por rol** (los crea `usuarios.py demo`):

| Usuario | Rol | Qué ve y qué puede hacer |
|---|---|---|
| `admin_demo` | Administrador | Todo, incluida la administración de usuarios y el registro de accesos |
| `analista_demo` | Analista | Mesa táctica, Jugadores y Patrones; taguea y gestiona el partido |
| `cuerpo_demo` | Cuerpo técnico | Las vistas anteriores y el Semáforo (califica); no taguea |
| `lector_demo` | Solo lectura | Mesa táctica, Jugadores y Patrones; no carga ni modifica nada |

---

## Procesar un partido

Las etapas se corren por consola, una vez por video. Un partido de dos tiempos son dos videos, y cada tiempo se procesa por separado. Los comandos completos, con todas sus opciones, están en `CLAUDE.md` ("Setup y comandos").

```bash
export ROBOFLOW_API_KEY="..."                                           # solo esta etapa la necesita
python3 src/detection/run_inference.py data/videos/<clip>.mp4           # detección + tracking (~80 min por 90 min de video)
python3 scripts/estadios.py alta "<estadio>" --largo <m> --ancho <m>    # una vez por estadio
python3 src/homography/calibrate.py data/videos/<clip>.mp4 --estadio "<estadio>"
python3 src/homography/calibrate.py data/videos/<clip>.mp4 --apply data/outputs/<clip>_coords.parquet
```

Regla de la calibración: se usa solo con el control en **OK** y después de mirar la imagen de superposición (ver `decisiones.md`).

---

## Configuración

Lo que cambia entre instalaciones va en variables de entorno o en un `.env` (copiar `.env.example`). El `.env` **no se sube al repo**: está en `.gitignore`.

| Variable | Para qué | ¿Obligatoria? |
|---|---|---|
| `ROBOFLOW_API_KEY` | Detección en `run_inference.py` | Solo para procesar videos nuevos |
| `SUPABASE_URL`, `SUPABASE_KEY` | Sync a la nube (`scripts/sync_to_cloud.py`); la key pública, nunca la `service_role` | No |
| `ANALIZADOR_DIR_RESPALDOS` | Dónde guardar los respaldos (por defecto `data/respaldos/`) | No; recomendado: otro disco |
| `STREAMLIT_CLIENT_SHOW_ERROR_DETAILS` | `full` para ver el traceback en el navegador mientras se desarrolla | No |

Configuración fija en `.streamlit/config.toml`:
- el dashboard escucha solo en `localhost` (para usarlo desde una tablet en la red local: `--server.address 0.0.0.0`);
- los errores se muestran genéricos en el navegador;
- tema oscuro.

---

## Datos, respaldos y seguridad

**Qué se guarda y dónde (todo local, en `data/`, fuera del repo):**

| Dato | Dónde |
|---|---|
| Usuarios, registro de accesos, eventos tagueados, semáforo, plantel, equipos, estadios | `data/db/analizador.sqlite` |
| Posiciones de los jugadores | `data/outputs/*.parquet` |
| Calibraciones | `data/outputs/*.json`, `data/calibracion/` |
| Videos | `data/videos/`, `data/outputs/*_tracked.mp4` |

**Contraseñas:**
- se guardan solo como hash scrypt con sal, nunca en claro;
- mínimo 8 caracteres;
- 5 intentos fallidos seguidos bloquean ese usuario 15 minutos;
- la sesión se cierra sola a los 30 minutos sin uso.

**Registro de accesos:** ingresos (también los fallidos), salidas y cambios de usuarios y respaldos, con quién y cuándo. Lo ve el admin en la vista Usuarios, o por consola:

```bash
python3 scripts/usuarios.py registro
```

**Respaldos:** el dashboard hace uno al ingresar, si el último tiene más de 24 h, y conserva los últimos 14. Incluyen la base, las calibraciones y los parquets, cada archivo con su SHA-256. Los videos no van.

```bash
python3 scripts/respaldo.py crear --destino /Volumes/PENDRIVE/respaldos   # copia en otro disco
python3 scripts/respaldo.py listar
python3 scripts/respaldo.py verificar data/respaldos/respaldo_<fecha>
python3 scripts/respaldo.py restaurar data/respaldos/respaldo_<fecha>     # con el dashboard cerrado
```

`restaurar` verifica el respaldo y antes guarda otro del estado actual, así que se puede deshacer. Por defecto restaura solo la base; con `--con-archivos`, también las calibraciones y los parquets.

**Si alguien se olvidó la contraseña:** el admin le pone una nueva desde la vista Usuarios. Si es el único admin:

```bash
python3 scripts/usuarios.py contrasena <usuario>
```

---

## Actualizar y volver atrás

```bash
python3 scripts/respaldo.py crear          # 1. respaldo antes de actualizar
git pull                                   # 2. código nuevo
pip install -r requirements.txt            # 3. dependencias (por si cambiaron)
streamlit run app/main.py                  # 4. probar de punta a punta: ingresar, abrir un partido, taguear
```

Las versiones que se mostraron llevan una etiqueta de git (`git tag -n1` las lista; p.ej. `demo-avance-2026-10-20`).

**Para volver atrás:**
- **Código:** `git checkout <etiqueta>` y `pip install -r requirements.txt`.
- **Datos:** `python3 scripts/respaldo.py restaurar <respaldo>`.

---

## Estructura

```text
app/
  main.py                 # Dashboard (entry point): encabezado, vistas, login, orquestación
  components/             # Video sincronizado, mapa 2D, tagueo, jugadores, patrones, sesión, usuarios…
  static/                 # Generada al correr (hardlink al video abierto). No tocar; está en .gitignore
src/
  detection/              # run_inference.py (RF-DETR + ByteTrack), video_anotado.py
  homography/             # calibrate.py (calibración, control de calidad, tramos), medidas de cancha
  analysis/               # equipos, estadísticas, patrones, lados
  db/                     # Repositorios SQLite (uno por tabla), registro, respaldo, sync a Supabase
scripts/                  # CLIs: usuarios, respaldo, estadios, partidos, cortar video, sync, datos de prueba…
db/schema_cloud.sql       # Esquema de la nube (Supabase), idempotente
docs/context/             # Contexto del proyecto, arquitectura y decisiones (fuente de verdad)
mockup/                   # Mockup visual de referencia
data/                     # Videos, salidas, base y respaldos (fuera del repo)
```

---

## Problemas conocidos

- **iCloud Drive:** el repo sincronizado con iCloud corrompió archivos (0 bytes) en el pasado. Conviene clonarlo fuera de iCloud, y no arrastrar archivos con Finder.
- **Dos OpenCV:** el detector instala además `opencv-python-headless`. En el equipo de desarrollo se importa la 4.12 (`opencv-python`); si algo de video se comporta raro, revisar `python3 -c "import cv2; print(cv2.__version__)"`.
- **Videos anotados viejos:** los procesados antes del 18/10/2026 (`partido_clip`, `partido_clip2`) están en el códec `mpeg4`, que los navegadores no reproducen. Para regenerarlos en H.264, sin volver a correr el detector:

  ```bash
  python3 scripts/regenerar_video_anotado.py <video> <coords.parquet>
  ```
- **Velocidad máxima de jugadores lejos de la cámara:** es orientativa. Con cámara baja, el temblor de la caja en la banda lejana parece un pique.
- **Tracking fragmentado:** un mismo jugador puede quedar en varios tracks (oclusiones, salidas de cuadro). La vista Jugadores los agrupa como "posiblemente el mismo jugador", sin fusionarlos.
