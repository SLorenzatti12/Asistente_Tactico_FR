# Informe — Secciones 5.1 (Despliegue) y 5.2 (Seguridad) — BORRADOR

Borrador del 27/10/2026, armado sobre el sistema real: código, base y pruebas de ese día.

- **[completar]:** lo que tiene que decidir el equipo.
- **[verificar]:** lo que no se comprobó.

Los casos de prueba que cita cada medida (`CP-xx`) están al final, para la sección 4.

---

## 5.1 Despliegue

### Nivel elegido: 1 — instalación local documentada

El sistema se despliega en la **laptop del club** (la del analista), con un instructivo para instalarlo desde cero en cualquier máquina. Ese instructivo es el `README.md` del repositorio.

**Por qué el nivel 1 y no una URL pública:**
- **Sin conectividad en la cancha.** Es un requisito validado en las entrevistas: el sistema tiene que funcionar 100% sin internet. Una URL pública no sirve donde se usa.
- **Datos reales de personas.** Los videos muestran a jugadores reales, y en inferiores pueden ser menores. La materia pide no publicar datos reales en un entorno de prueba.
- **Volumen.** Un partido son cientos de MB de video, y procesarlo requiere aceleración por hardware (~80 min por partido de 90 min en la laptop de desarrollo). Los planes gratuitos de publicación no lo soportan.

**Opcional para la defensa:** una instancia pública (nivel 2) solo con datos sintéticos (`scripts/make_sample_parquet.py`) y los usuarios de prueba. **[completar: decidir si se hace]**

### Entorno y servicios

| Parte | Dónde corre | Servicio |
|---|---|---|
| Código | Repositorio Git | GitHub (`main` estable, ramas por integrante) |
| Dashboard | Laptop del club, solo `localhost` | Streamlit 1.60, Python 3.12 |
| Base de datos | Laptop del club | SQLite (`data/db/analizador.sqlite`), sin servidor |
| Procesamiento de video | Laptop del club | Modelo RF-DETR propio (Roboflow `inference`), aceleración CoreML |
| Respaldos | Laptop (por defecto) u otro disco | Carpetas verificables (`scripts/respaldo.py`) |
| Nube (opcional, posterior) | Internet | Supabase: Postgres y Storage privado, sync manual de la laptop a la nube |

### Requisitos

- **Software:** Python 3.12, ffmpeg y Git.
- **Disco:** ~3 GB para las dependencias, más ~0,5 GB por partido.
- **Plataforma:** desarrollado y probado en macOS con Apple Silicon.
- **Para procesar videos nuevos:** una API key de Roboflow.
  - El modelo se descarga una vez y queda en `models/roboflow_cache/`.
  - **[verificar]** que después la inferencia corra sin internet.

### Pasos de instalación

Están numerados en `README.md` → "Instalación desde cero":
1. clonar el repositorio;
2. crear el entorno e instalar dependencias (`requirements.txt`, todas con versión fija);
3. crear el primer administrador por consola;
4. levantar el dashboard.

Para probar sin un partido real, el README trae los comandos de datos y usuarios de prueba.

**Base de datos:** no hay migraciones ni scripts aparte. Cada módulo de `src/db/` crea su tabla (`CREATE TABLE IF NOT EXISTS`) la primera vez que se usa. El esquema de la nube está en `db/schema_cloud.sql` y es idempotente.

**Verificado:** en un entorno de Python limpio, `pip install --dry-run -r requirements.txt` resuelve las 244 dependencias sin conflictos.
- **[completar]** Falta la instalación completa en otra máquina (la de Nico o la de Luci), siguiendo el README tal cual.

### Configuración (variables de entorno, sin valores)

| Variable | Para qué | Obligatoria |
|---|---|---|
| `ROBOFLOW_API_KEY` | Detección de jugadores (procesar videos nuevos) | Solo para procesar |
| `SUPABASE_URL`, `SUPABASE_KEY` | Sync a la nube (key pública, nunca `service_role`) | No |
| `ANALIZADOR_DIR_RESPALDOS` | Carpeta de respaldos (otro disco o pendrive) | No (recomendada) |

Van en un `.env` que está en `.gitignore`. En el repositorio solo está `.env.example`, con los nombres y sin valores.

### Accesos de prueba

`python3 scripts/usuarios.py demo` crea un usuario por rol (`admin_demo`, `analista_demo`, `cuerpo_demo`, `lector_demo`), con contraseñas al azar que se muestran una sola vez. No se entregan contraseñas fijas en el informe ni en el repositorio.

### Prueba de punta a punta después de instalar

1. Ingresar con cada rol y ver que las vistas y botones coinciden con la matriz de 5.2.
2. Abrir un partido y reproducir el video: la cancha 2D lo sigue.
3. Taguear con un botón y con el teclado (1–9). El evento aparece en el historial.
4. Abrir Jugadores y Patrones; "Ver en la Mesa táctica" lleva al momento.
5. `python3 scripts/respaldo.py crear` y `verificar`.

### Actualizar y volver atrás

- **Actualizar:** respaldo, `git pull`, `pip install -r requirements.txt` y la prueba de punta a punta.
- **Versiones:** cada versión mostrada lleva una etiqueta de git (hoy: `demo-avance-2026-10-20`).
- **Volver atrás:**
  - **Código:** `git checkout <etiqueta>`.
  - **Datos:** `python3 scripts/respaldo.py restaurar <respaldo>`. Antes de restaurar se respalda el estado actual, así que se puede deshacer.
- **Responsable del despliegue:** **[completar]**

### Qué falta para el 16/11

| Tarea | Responsable |
|---|---|
| Instalación completa desde cero en una segunda máquina, siguiendo el README | **[completar]** |
| Etiqueta de la versión de entrega (p.ej. `entrega-final-2026-11-16`) | **[completar]** |
| Regenerar en H.264 los videos anotados viejos (`partido_clip`, `partido_clip2`) | Santi |
| Aplicar la seguridad de la nube en el proyecto real (`8-base-de-datos-hibrida.md` → "Seguridad de la nube") y correr `scripts/verificar_rls.py` | Nico (tiene el acceso al proyecto) |
| (Opcional) instancia pública con datos sintéticos | **[completar]** |

---

## 5.2 Seguridad de la información

### Inventario de datos

| Dato | Dónde vive | Sensibilidad | Quién debe verlo | Riesgo si se filtra |
|---|---|---|---|---|
| Video del partido | `data/videos/` (laptop); Storage privado de Supabase si se sincroniza | **Alta**: imagen de personas, posiblemente menores | Cuerpo técnico y analista del club | Exposición de la imagen de los jugadores sin consentimiento; incumplimiento de la Ley 25.326 |
| Semáforo: minutos jugados y valoración del DT, el ayudante y el coordinador, por jugador y partido | SQLite (por ahora no se sube a la nube) | **Alta**: valoración de personas | Cuerpo técnico (y administrador) | Conflicto con jugadores o con otros clubes; uso fuera de su finalidad |
| Plantel (apellido, nombre, dorsal) | SQLite; copia en Supabase | Personal | Cuerpo técnico, analista | Datos personales fuera del club |
| Posiciones, métricas, eventos tagueados | Parquets y SQLite | Media: información táctica del club | Usuarios del club | Ventaja competitiva para un rival |
| Credenciales de usuarios | SQLite, solo hash scrypt con sal | **Crítica** | Nadie (ni el administrador ve la contraseña) | Acceso al sistema con la identidad de otro |
| Registro de accesos | SQLite (tabla `registro`) | Media: usuarios y horarios | Administrador | Conocer hábitos de uso; si se altera, se pierde trazabilidad |
| Claves de servicios (Supabase, Roboflow) | `.env` local, fuera del repositorio | **Crítica** | Solo quien despliega | Lectura y escritura de la base en la nube; uso de la cuenta de Roboflow |

**Minimización:**
- no se guardan datos de los jugadores que no hagan falta (ni DNI, ni contacto, ni fecha de nacimiento);
- el tracking no identifica personas: los jugadores son números de track, sin nombre;
- los videos no se suben al repositorio ni se publican.

### Roles y permisos

Autenticación local (usuario y contraseña, sin internet). La autorización se verifica en el servidor en cada corrida: lo que el rol no permite no se dibuja, y en Streamlit lo que no se dibujó no se puede ejecutar.

| Acción | Administrador | Analista | Cuerpo técnico | Solo lectura |
|---|---|---|---|---|
| Ver Mesa táctica, Jugadores, Patrones | Sí | Sí | Sí | Sí |
| Taguear eventos (botones y teclado) | Sí | Sí | No | No |
| Configurar el partido (equipo, video) | Sí | Sí | No | No |
| Ver los eventos tagueados (gráficos, historial, ir al momento) | Sí | Sí | Sí | Sí |
| Editar o borrar eventos; configurar tipos de evento | Sí | Sí | No | No |
| Ver el plantel | Sí | Sí | Sí | Sí |
| Gestionar el plantel (alta y baja) | Sí | Sí | No | No |
| Ver el Semáforo (última calificación, quién y cuándo) | Sí | Sí | Sí | Sí |
| Cargar minutos jugados | Sí | No | Sí | No |
| Valorar en el Semáforo | Solo la columna de su función (DT, ayudante o coordinador), si tiene una | No | Solo la columna de su función | No |
| Administrar usuarios y ver el registro de accesos | Sí | No | No | No |
| Acceso a la base en la nube | Solo el sync, con la clave secreta, desde la máquina que sincroniza | | | |

Quien no tiene un permiso ve la pantalla en solo lectura: los controles no se dibujan, y por lo tanto no se pueden ejecutar.

### Matriz de riesgos de seguridad

| ID | Riesgo | Prob. | Impacto | Medida | Estado |
|---|---|---|---|---|---|
| R1 | **Pérdida o corrupción de la base** (está en una sola laptop; ya hubo archivos corruptos por iCloud) | Media | Alto | Respaldo automático diario, verificable (SHA-256 y `integrity_check`), con restauración probada; repo fuera de iCloud | **Hecha** la parte técnica · falta definir el disco externo (`ANALIZADOR_DIR_RESPALDOS`) |
| R2 | **Lectura o escritura de la base en la nube** con la clave pública (RLS desactivada) | Media | Alto | RLS en todas las tablas sin acceso para la clave pública (`db/rls_cloud.sql`); sync con la clave secreta, solo en la máquina que sincroniza; verificación con `scripts/verificar_rls.py` | **En curso**: probado contra un Postgres local que imita a Supabase · falta aplicarlo en el proyecto real (Nico) |
| R3 | **Laptop desatendida** con la sesión abierta, o alguien en la misma red | Media | Medio | Login con roles; cierre a los 30 min sin uso; el dashboard escucha solo en `localhost` | **Hecha** |
| R4 | **Contraseñas adivinables** o fuerza bruta | Media | Medio | Hash scrypt con sal; mínimo 8 caracteres; bloqueo tras 5 fallidos durante 15 min; mensajes genéricos | **Hecha** |
| R5 | **Claves en el repositorio** | Baja | Alto | `.env` y `secrets.toml` en `.gitignore`; `.env.example` sin valores; historial revisado sin claves | **Hecha** |
| R6 | **Exposición de la imagen de jugadores menores** sin consentimiento | Media | Alto | Videos fuera del repo; bucket privado; consentimiento firmado de padres o tutores antes de filmar inferiores | **Pendiente**: modelo de consentimiento **[completar]** |
| R7 | **Acceso directo a los archivos** de la laptop (base, parquets y videos no están cifrados) | Media | Alto | Cifrado de disco del sistema operativo (FileVault o BitLocker) y usuario del sistema propio para el analista | **Pendiente**: procedimiento operativo |
| R8 | **Dependencias vulnerables**, o que una actualización rompa el sistema | Media | Medio | Versiones fijadas y probadas juntas; reemplazar `sv.ByteTrack` (deprecado) antes de actualizar supervision | **En curso** |

La **inyección SQL** se revisó y queda cubierta (ver medidas). No figura como riesgo abierto.

### Medidas implementadas

| Medida | Protege | Dónde | Caso de prueba |
|---|---|---|---|
| Contraseñas con hash scrypt y sal por usuario; nunca en claro | Confidencialidad | `src/db/usuarios_repo.py` | CP-01 |
| Mínimo 8 caracteres | Confidencialidad | ídem | CP-02 |
| Bloqueo tras 5 fallidos, por nombre escrito (no revela si el usuario existe) | Confidencialidad | ídem y `registro_repo.py` | CP-03, CP-04 |
| Mensaje genérico de error de ingreso | Confidencialidad | `app/components/sesion.py` | CP-05 |
| Roles y permisos verificados en el servidor | Confidencialidad, integridad | `usuarios_repo.PERMISOS`, `main.py` | CP-06 |
| Cierre de sesión por inactividad (30 min) | Confidencialidad | `sesion.py` | CP-07 |
| Dashboard solo en `localhost` | Confidencialidad | `.streamlit/config.toml` | CP-08 |
| Errores genéricos en el navegador (detalle solo en la terminal) | Confidencialidad | ídem | CP-09 |
| Consultas parametrizadas (`?`); los nombres de tabla o columna salen de listas fijas del código | Confidencialidad, integridad | `src/db/`, `tagging.py` | CP-10 |
| Secretos fuera del repositorio | Confidencialidad | `.gitignore`, `.env.example` | CP-11 |
| Respaldo verificable y restauración | Disponibilidad, integridad | `src/db/respaldo.py`, `scripts/respaldo.py` | CP-12, CP-13, CP-14 |
| Registro de accesos y acciones críticas, sin contraseñas | Integridad (trazabilidad) | `src/db/registro_repo.py` | CP-15, CP-20 |
| Modos de solo lectura por rol (eventos, Semáforo, plantel) | Integridad, confidencialidad | `tagging.py`, `roster_view.py`, `main.py` | CP-18 |
| Autor de cada evento y calificación (`created_by`) | Integridad (trazabilidad) | `tagging.py` | CP-19 |
| RLS en la nube; la clave pública sin acceso; sync con la clave secreta | Confidencialidad, integridad | `db/rls_cloud.sql`, `supabase_client.py` | CP-21, CP-22 |
| Siempre queda un administrador activo; un admin no puede desactivarse a sí mismo | Disponibilidad | `usuarios_repo.py`, `usuarios_view.py` | CP-16 |
| Dependencias con versión fija | Integridad, disponibilidad | `requirements.txt` | CP-17 |

### Respaldos y registro de acciones

**Respaldos:**
- **Qué incluyen:** la base (usuarios, registro, eventos, semáforo, plantel, equipos, estadios, partidos), las calibraciones (JSON) y los parquets de posiciones. Los videos quedan afuera: los tiene el club.
- **Frecuencia:** automática al ingresar, si el último tiene más de 24 h. También manual, cuando se quiera (`scripts/respaldo.py crear`).
- **Dónde:** `data/respaldos/` en la misma laptop, o en otro disco con `--destino` o `ANALIZADOR_DIR_RESPALDOS`. Se conservan los últimos 14.
- **Cómo se restaura:** `python3 scripts/respaldo.py restaurar <respaldo>`, con el dashboard cerrado.
  - Primero verifica el SHA-256 de cada archivo, la integridad de la base y las filas por tabla.
  - Después respalda el estado actual (para poder deshacer) y recién entonces restaura.
- **Restauración probada** el 27/10/2026, ver CP-13.

**Registro de acciones (tabla `registro`):**
- **Qué guarda:** ingresos, ingresos fallidos y bloqueados, salidas, sesiones vencidas, altas, cambios de rol, activaciones, cambios de contraseña, respaldos creados y restaurados, ediciones y borrados de eventos (antes y después), altas y bajas del plantel.
- **Cada fila:** fecha y hora, quién (usuario, `consola` o `sistema`), acción, sobre qué y un detalle.
- **No guarda** contraseñas ni hashes.
- **Quién lo ve:** el administrador, en la vista Usuarios ("Registro de accesos y cambios"), o con `scripts/usuarios.py registro`.

**Autoría en los datos:** cada evento tagueado y cada calificación del Semáforo guardan quién los hizo (`created_by`). Las calificaciones no se pisan: cada una es una fila nueva, así que queda el historial completo.

### Marco normativo aplicable

**[verificar]** Los artículos citados se cotejan con el texto vigente en la fuente oficial (InfoLEG) antes de entregar.

- **Ley 25.326 (Protección de los Datos Personales).**
  - **Qué datos personales trata el sistema:** la imagen de los jugadores en el video, el plantel (nombre y dorsal) y las valoraciones del Semáforo.
  - **Obligaciones que implica:**
    - **Finalidad:** usar los datos solo para el análisis deportivo del club.
    - **Consentimiento:** informado. Para menores, de sus padres o tutores, antes de filmar inferiores.
    - **Deber de seguridad:** medidas técnicas y organizativas (las de esta sección).
    - **Derechos de acceso, rectificación y supresión:** el plantel admite corrección, y la baja de un jugador borra el registro (`DELETE` físico).
    - **Datos en la nube:** si se sincronizan, el proveedor (Supabase) y la ubicación de los datos son una decisión a documentar.
- **Ley 26.388 (Delitos informáticos).**
  - **Tipifica:** el acceso ilegítimo a un sistema o dato informático y el daño informático.
  - **Por qué importa acá:** el registro de accesos y los respaldos verificables (con su SHA-256) son la evidencia que se pediría en un peritaje (ver Clases 17–18 y el informe pericial del track 1078).
- **ISO/IEC 27001 (referencia, sin certificar).** Controles del Anexo A que el sistema cubre:
  - control de acceso y autenticación segura (5.15, 5.17, 8.5);
  - respaldo de la información (8.13);
  - registro de eventos (8.15);
  - uso de criptografía (8.24).

---

## Casos de prueba de seguridad (para la sección 4)

Ejecutados el 27/10/2026 sobre una copia de la base, salvo que se indique otra cosa.

**Cómo se ejecutaron:**
- **Repositorio:** script de pruebas, 24 de 24 OK.
- **Interfaz:** `streamlit.testing.v1.AppTest` sobre el `app/main.py` real.
- **Navegador:** Chromium, contra el dashboard levantado en la laptop de desarrollo.

| ID | Caso (uso o abuso) | Resultado esperado | Resultado obtenido |
|---|---|---|---|
| CP-01 | Se busca la contraseña en la base y en el registro | Solo existe el hash `scrypt$…`; la contraseña no aparece en ningún lado | OK |
| CP-02 | Alta con contraseña de 7 caracteres | Rechazada con mensaje | OK ("La contraseña tiene que tener al menos 8 caracteres") |
| CP-03 | 5 ingresos fallidos y después la contraseña correcta | El 6° intento se rechaza con "Demasiados intentos… 15 min", sin mirar la contraseña | OK (repositorio y pantalla de ingreso) |
| CP-04 | 5 fallidos con un usuario que **no existe** | Se bloquea igual (no revela si existe); se desbloquea pasados 15 min o con una contraseña nueva puesta por el admin | OK |
| CP-05 | Usuario existente con contraseña mala, y usuario inexistente | Mismo mensaje: "Usuario o contraseña incorrectos…" | OK |
| CP-06 | Ingresar con cada rol | Vistas, tagueo y configuración del partido según la matriz | OK (AppTest, los 4 roles); un usuario desactivado con la sesión abierta queda afuera en la próxima interacción |
| CP-07 | Sesión sin uso durante 31 min, y durante 29 min | A los 31 vuelve al ingreso con aviso y queda registrado; a los 29 sigue adentro | OK (AppTest); con el video reproduciéndose, el vigilante no lo corta (navegador: 76,9 s de video en 76,9 s) |
| CP-08 | Abrir el dashboard desde otra máquina de la red (IP de la laptop) | Conexión rechazada; desde `localhost` responde | OK (servidor escuchando solo en 127.0.0.1) |
| CP-09 | Provocar un error con una ruta interna en el mensaje | El navegador muestra un mensaje genérico, sin traceback ni ruta; el detalle va a la terminal | OK (navegador: "the original error message is redacted"; la terminal tiene el traceback) |
| CP-10 | Revisión de código: SQL armado concatenando texto | Ningún dato del usuario se concatena en una consulta | OK (revisión del 27/10) |
| CP-11 | Buscar `.env`, `secrets.toml` y claves en todo el historial de git | No aparecen | OK |
| CP-12 | Crear un respaldo y verificarlo | Verifica: 26 archivos, ~17 MB, filas por tabla iguales a la base | OK |
| CP-13 | Borrar usuarios y eventos, pisar una calibración y restaurar | Vuelven los usuarios, los eventos y la calibración; queda un respaldo del estado roto para deshacer; se registra la restauración | OK |
| CP-14 | Restaurar un respaldo alterado (bytes cambiados) | Se rechaza por SHA-256 distinto; la base no se toca | OK |
| CP-15 | Ingreso, fallo, cambio de rol y desactivación | Cada acción queda con fecha, quién, sobre quién y detalle (p.ej. "rol: analyst → coach") | OK |
| CP-16 | El único admin intenta quitarse el rol o desactivarse | No se permite | OK ("Tiene que quedar al menos un administrador activo"); en la app, sus propios controles están deshabilitados |
| CP-17 | Instalación de las dependencias en un entorno limpio | Se resuelven sin conflictos | OK con `--dry-run` (244 paquetes) · **[completar]**: instalación completa en otra máquina |
| CP-18 | Ingresar con cada rol a la Mesa táctica y al Semáforo | Admin y analista taguean y editan; cuerpo técnico y lector ven los eventos sin botonera, ⚙️, editar ni borrar. El Semáforo lo ven todos, y solo admin y cuerpo técnico tienen los botones. El plantel solo lo editan admin y analista | OK (AppTest, los 4 roles, sobre una copia aislada) |
| CP-19 | Taguear como analista y calificar como cuerpo técnico | `created_by` = el usuario; el lector ve "🟢 destacado · por t_cuerpo · fecha" | OK (AppTest) |
| CP-20 | Editar y borrar un evento; agregar y sacar un jugador del plantel | Queda en el registro, con quién, el antes y el después del evento y quién lo había tagueado | OK (edición y borrado en el navegador; plantel con AppTest) |
| CP-21 | Con la clave pública: leer, insertar, modificar y borrar en las tablas, y subir o listar videos | Todo rechazado; con la clave secreta (sync) todo funciona; correr el SQL dos veces da lo mismo | OK en un Postgres local que imita a Supabase · **[completar]**: `scripts/verificar_rls.py` contra el proyecto real |
| CP-22 | Cargar la clave pública donde va la secreta, y al revés | El sync no arranca y explica el error | OK |
| CP-23 | Entrar al Semáforo con DT, ayudante, coordinador, cuerpo técnico sin función, admin, analista y lector | Cada uno edita solo la columna de su función; los minutos solo quien califica; las columnas ajenas se ven como etiquetas y no como controles | OK (AppTest, 7 usuarios) |
| CP-24 | Cargar minutos y valoraciones, cambiarlas y abrir el otro tiempo del partido | Vale la última; el historial guarda todas las cargas con quién y cuándo; los dos tiempos muestran la misma planilla | OK |
| CP-25 | Editar el plantel (alta, corrección, baja), importar un CSV, filas inválidas | Cada cambio queda en el registro; sin apellido o con dorsal fuera de 0–99, error y no se guarda; el CSV no duplica jugadores | OK (lógica y navegador) |
