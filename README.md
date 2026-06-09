# Analizador Táctico IA - MVP (Procesamiento Post-Partido)

Este repositorio contiene el Producto Mínimo Viable (MVP) del sistema de análisis táctico automatizado diseñado para clubes de fútbol regional. Utiliza Inteligencia Artificial y Visión por Computadora para procesar videos en diferido de las cámaras de fondo (Norte y Sur), transformando la perspectiva diagonal en un plano métrico 2D único para calcular la compacidad del bloque y permitir el etiquetado táctico ágil.

**Desarrolladores (Equipo Lorenzatti - Tribolo - Pesce):**
* Santiago Lorenzatti (Product Manager & UX)
* Lucia Pesce (Lead AI & Computer Vision Engineer)
* Nicolas Tribolo (Full-Stack Architect & Integrator)

---

## 🚀 Características Clave

* **Procesamiento Offline Completo:** Diseñado para funcionar al 100% sin conexión a internet, adaptándose a la realidad de los estadios regionales.
* **Doble Homografía Unificada:** Convierte la perspectiva de los dos fondos de la cancha en un único plano métrico 2D interactivo con origen $(0,0)$ en el centro del campo.
* **Tracking de Jugadores:** Identificación y seguimiento persistente de los futbolistas frame a frame mediante YOLOv8 y ByteTrack.
* **Tagueo "One-Click":** Botonera integrada para exportar clips automáticos de 10 segundos de eventos clave (Salidas, Presión, Pelota Parada).
* **Semáforo de Rendimiento:** Módulo cuantitativo y cualitativo conectado a base de datos local para guardar el histórico de análisis.

---

## 🛠️ Stack Tecnológico

* **Lenguaje:** Python 3.10+
* **Modelado de IA:** Ultralytics YOLOv8 (Versión Nano - `yolov8n`)
* **Tracking:** ByteTrack
* **Visión & Geometría:** OpenCV
* **Interfaz Gráfica:** Streamlit
* **Base de Datos:** SQLite (Serverless)
* **Procesamiento de Video:** FFmpeg / MoviePy

---

## 📁 Estructura del Proyecto

El sistema auto-genera e implementa la siguiente arquitectura de directorios locales:

```text
├── .gitignore
├── README.md
├── requirements.txt
├── app.py                      # Archivo principal de ejecución de Streamlit
├── db/
│   ├── schema.sql              # Estructura de tablas SQLite
│   └── datos.sqlite            # Base de datos local (Ignorada en Git)
├── src/
│   ├── calibrador.py           # Script OpenCV para Matriz de Homografía
│   ├── pipeline_ia.py          # Script de inferencia Batch (YOLOv8 + ByteTrack)
│   └── utils.py                # Funciones auxiliares de corte de video y lógica
├── data/
│   ├── assets/                 # Imagen cenital de la cancha (.png)
│   ├── calibracion/            # Archivos JSON con matrices guardadas
│   └── videos/                 # Videos crudos .mp4 de los partidos (Ignorados en Git)
└── output/
    └── clips/                  # Recortes de video generados por el tagueo (Ignorados en Git)
