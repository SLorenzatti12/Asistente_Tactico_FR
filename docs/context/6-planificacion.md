# Planificación del Proyecto 

Lorenzatti - Tribolo - Pesce 

## **Sprint 1: Cimientos del Sistema y Captura (Junio 2026)** 

**Foco:** Preparar la infraestructura de código y conseguir el "combustible" (datos). 

##  **Semana 1 (1 al 7 de junio): Setup Inicial** 

   - Full-Stack: Inicialización de repositorio en GitHub, configuración de ramas y .gitignore. 

   - Lead AI: Creación del entorno virtual (venv) e instalación de YOLOv8, PyTorch y OpenCV. 

   - PM (Vos): Redacción de requerimientos de video (calidad, posición, duración) para enviar a los clubes. 

- **Semana 2 (8 al 14 de junio): Recolección y Base de Datos** 

   - PM: Gestión presencial con clubes locales (ej. LRF o Liga San Francisco) para obtener los 2 partidos grabados a doble fondo. 

   - Full-Stack: Diseño del diagrama de Entidad-Relación y creación del archivo schema.sql (SQLite). 

   - Lead AI: Script básico de prueba (test_yolo.py) para verificar que el modelo carga correctamente en la laptop. 

- **Semana 3 (15 al 21 de junio): Inferencia Cruda** 

   - Lead AI: Ejecutar YOLOv8 sobre los primeros videos de fondo para analizar la pérdida de detección por distancia. 

   - Full-Stack: Desarrollo del script backend que auto-genera la estructura de carpetas locales (/videos, /clips, /db). 

- **Semana 4 (22 al 30 de junio): Revisión del Sprint** 

   - PM: Documentar en Notion las especificaciones finales del dataset conseguido. 

   - Equipo: Reunión de sincronización para evaluar los FPS obtenidos en la inferencia cruda y cerrar el Sprint. 

## **Sprint 2: El Reto Matemático (Julio 2026)** 

**Foco:** Calibración de las cámaras y unificación del plano. 

##  **Semana 1 (1 al 7 de julio): UI de Calibración e Insumos** 

   - PM: Conseguir las medidas métricas oficiales de las canchas filmadas y diseñar el fondo del mapa 2D. 

   - Full-Stack: Crear el esqueleto en Streamlit (app.py) con la barra lateral para subir el video. 

- **Semana 2 (8 al 14 de julio): Desarrollo del Calibrador** 

   - Lead AI: Script en OpenCV que permita hacer clic en las 4 esquinas del fotograma para obtener coordenadas (x,y). 

   - Full-Stack: Integrar la ventana de OpenCV dentro o en paralelo a la app de Streamlit. 

- **Semana 3 (15 al 21 de julio): Lógica de Homografía** 

   - Lead AI: Implementar la matemática para generar las dos matrices de transformación, fijando el (0,0) en el centro de la cancha. 

- **Semana 4 (22 al 31 de julio): Guardado de Matrices** 

- Full-Stack: Programar la exportación de la calibración a un archivo JSON local. 

- Equipo: Test de extremo a extremo: subir foto, calibrar, guardar matriz. 

## **Sprint 3: Tracking e Integración 2D (Agosto 2026)** 

**Foco:** Seguir a los jugadores y dibujarlos en el mapa en diferido. 

##  **Semana 1 (1 al 7 de agosto): Integración de ByteTrack** 

   - Lead AI: Acoplar ByteTrack a YOLOv8 para asegurar que los IDs de los jugadores sean persistentes a lo largo de los frames. 

   - PM: Definir la paleta de colores de los puntos tácticos y el tamaño de renderizado en el mapa. 

- **Semana 2 (8 al 14 de agosto): Pipeline de Exportación** 

   - Lead AI: Programar el bucle que procesa el video, aplica la matriz de homografía a los pies detectados y exporta un archivo coordenadas.parquet. 

- **Semana 3 (15 al 21 de agosto): Renderizado del Mapa** 

   - Full-Stack: Leer el archivo exportado y utilizar Plotly/Bokeh en Streamlit para dibujar los puntos sobre la cancha cenital. 

- **Semana 4 (22 al 31 de agosto): Sincronización Video-Mapa** 

   - Full-Stack: Unir el componente reproductor de video de Streamlit con el mapa 2D, para que al avanzar el video se actualicen los puntos. 

   - Equipo: Revisión de fluidez visual. 

## **Sprint 4: Tagueo Automatizado "One-Click" (Septiembre 2026)** 

**Foco:** Los botones mágicos que cortan el video de forma automática. 

- **Semana 1 (1 al 7 de septiembre): Diseño de Botonera** 

   - PM: Validar el listado de los 4 eventos clave con los directores técnicos. 

   - Full-Stack: Maquetar la botonera en la vista principal de Streamlit debajo del video. 

- **Semana 2 (8 al 14 de septiembre): Motor de Recorte (FFmpeg)** 

   - `Full-Stack: Lógica de backend. Al presionar botón, tomar timestamp actual −10 segundos y ejecutar comando nativo para cortar video.` 

- **Semana 3 (15 al 21 de septiembre): Persistencia de Clips** 

   - Full-Stack: Conectar la acción del botón con un INSERT en SQLite (guardar timestamp, ruta del .mp4 generado y tipo de evento). 

- **Semana 4 (22 al 30 de septiembre): Optimización de Metadata** 

   - Lead AI: Vincular el evento tagueado con su porción de datos del mapa 2D, para que el clip tenga contexto táctico guardado. 

   - Equipo: Prueba de estrés cortando 20 clips seguidos para medir estabilidad local. 

## **Sprint 5: Métricas de Bloque y Semáforo (Octubre 2026)** 

**Foco:** Darle valor analítico e histórico al sistema. 

- **Semana 1 (1 al 7 de octubre): Algoritmo de Compacidad** 

   - PM: Redactar la lógica de cálculo (qué considera el cuerpo técnico como línea defensiva y ofensiva). 

   - Lead AI: Programar la función que mida la distancia Eje Y entre extremos del equipo. 

- **Semana 2 (8 al 14 de octubre): Gráfico Evolutivo** 

   - Full-Stack: Integrar un gráfico de líneas temporal en Streamlit que muestre cómo varió el bloque táctico durante el partido. 

- **Semana 3 (15 al 21 de octubre): Formulario Semáforo** 

   - PM: Diseñar los campos cualitativos/cuantitativos del formulario. 

   - Full-Stack: Programar la vista del formulario en Streamlit y su impacto en la base de datos. 

- **Semana 4 (22 al 31 de octubre): Dashboard Final** 

   - Full-Stack: Consolidar todas las vistas (Video, Mapa, Gráficos, Semáforo) en el layout definitivo. 

   - Equipo: Cierre funcional del software ("Code Freeze"). 

## **Sprint 6: QA, Pruebas de Campo y Ajustes (Noviembre 2026)** 

**Foco:** Que el sistema no falle frente al tribunal ni frente al DT. 

##  **Semana 1 (1 al 7 de noviembre): Testeo con Usuarios Reales** 

   - PM: Simular una charla técnica en un club utilizando los videos procesados, evaluando la botonera y el mapa con entrenadores reales. 

- **Semana 2 (8 al 14 de noviembre): Ajustes de IA y Falsos Positivos** 

   - Lead AI: Revisar los logs del testeo. Ajustar umbrales (conf) y parámetros del tracker (max_age) si hubo pérdida de IDs críticos. 

- **Semana 3 (15 al 21 de noviembre): Resolución de Bugs UI/UX** 

   - Full-Stack: Corregir cuelgues reportados en Streamlit, mejorar manejo de errores (ej. clics dobles en la botonera). 

- **Semana 4 (22 al 30 de noviembre): Empaquetado** 

   - Full-Stack & Lead AI: Crear un archivo de inicialización rápido (run.bat o start.sh) para que los evaluadores puedan levantar la app con un solo comando. 

   - PM: Iniciar redacción final del manual de usuario. 
