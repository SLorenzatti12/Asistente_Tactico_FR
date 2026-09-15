# Definición del Stack Tecnológico 

Lorenzatti - Tribolo - Pesce 

## **Diagrama de Arquitectura (Modelo Lógico)** 

El sistema opera bajo una arquitectura de procesamiento en bloque (Batch Processing) ejecutada íntegramente en un entorno local (Localhost). Se divide en cuatro capas lógicas: 

###  **Capa de Entrada (Ingesta de Datos):** 

- Lectura de archivos locales .mp4 provenientes de las cámaras de fondo (Norte y Sur). 

- Carga de parámetros del partido (dimensiones del campo, nombres de equipos). 

###  **Capa de Procesamiento (El "Cerebro" IA):** 

- **Módulo de Visión:** YOLOv8n detecta las coordenadas de jugadores y balón frame a frame. 

- **Módulo de Tracking:** ByteTrack asocia un ID persistente a cada detección. 

- **Módulo Matemático:** OpenCV aplica la Matriz de Homografía dual para transformar los píxeles en coordenadas métricas (x,y) sobre un plano 2D centralizado. 

###  **Capa de Persistencia (Backend):** 

   - Motor de base de datos relacional (SQLite) que almacena la metadata del partido, los eventos etiquetados y las calificaciones del "Semáforo". 

   - Módulo de recorte de video (FFmpeg/MoviPy) que extrae clips de 10 segundos y los guarda en el sistema de archivos local. 

- **Capa de Presentación (Frontend):** 

   - Servidor local instanciado con Streamlit. 

   - Renderizado en navegador web del reproductor sincronizado, el mapa 2D interactivo y la botonera de etiquetado táctico. 

Definir el **Stack Tecnológico** para este MVP es un paso clave. Dado que el sistema debe procesar dos o más canales de video en tiempo real, de manera 100% offline y en una laptop de gama media, la elección de las herramientas debe estar orientada a la . **eficiencia, la ligereza y la velocidad de desarrollo** 

## **Especificación del Stack Tecnológico** 

Para cumplir con las restricciones operativas de las canchas regionales (ausencia de conectividad) y las necesidades de procesamiento dual, se ha seleccionado un ecosistema de desarrollo basado en tecnologías de código abierto de alto rendimiento. 

### **Lenguaje de Programación Principal** 

###  **Tecnología: Python 3.10+** 

- **Justificación:** Es el estándar de la industria para el desarrollo de inteligencia artificial y visión por computadora. Permite la integración nativa y fluida de modelos de aprendizaje profundo con interfaces gráficas rápidas, además de facilitar el manejo asincrónico de hilos de ejecución para procesar los dos feeds de vídeo simultáneamente. 

### **Núcleo de Inteligencia Artificial y Visión Artificial** 

- **Tecnología: Ultralytics YOLOv8 (Versión Nano - YOLOv8n)** 

- **Justificación:** YOLOv8 ofrece la mejor relación del mercado entre precisión y velocidad de inferencia (FPS). Se opta específicamente por la arquitectura _Nano_ debido a que el hardware local debe procesar dos imágenes concurrentes. Su bajo peso computacional garantiza que la laptop no sufra estrangulamiento térmico durante el partido. 

- **Librerías de Soporte:** 

   - **OpenCV (Open Source Computer Vision Library):** Utilizada para la captura de los flujos de video locales, la manipulación de frames y la aplicación matemática de la **Matriz de Homografía** (conversión de píxeles a metros). 

   - **ByteTrack:** Algoritmo de tracking encargado de mantener la persistencia de los identificadores (IDs) de los jugadores frame a frame. 

### **Interfaz de Usuario y Frontend** 

###  **Tecnología: Streamlit** 

- **Justificación:** En lugar de construir una arquitectura compleja con frameworks como React o Angular que ralentizarían el MVP, Streamlit permite desarrollar una aplicación web interactiva utilizando únicamente Python. Es ideal para renderizar el mapa táctico 2D en tiempo real, manejar la botonera de taggeo "One-Click" y actualizar los gráficos de compacidad sin agregar sobrecarga de procesamiento al sistema. 

### **Gestión de Datos y Persistencia** 

- **Tecnología: SQLite** 

- **Justificación:** Al ser una base de datos relacional basada en un archivo local sin necesidad de un servidor activo (serverless), se acopla perfectamente a la premisa _offline_ del proyecto. Almacenará de forma estructurada las tablas de partidos, jugadores, coordenadas y los registros del "Semáforo de Rendimiento" post-partido, garantizando portabilidad absoluta. 

### **Entorno Operativo, Conectividad e Infraestructura** 

- **Protocolo de Video: RTSP (Real-Time Streaming Protocol)** o lectura directa de archivos en disco (Modo Batch). 

- **Infraestructura Física:** Cámaras de fondo conectadas a través de switches con soporte **PoE Activo (Power over Ethernet)** y cableado estructurado UTP Categoría 6, blindando la comunicación contra cualquier interferencia del entorno. 

- **Entorno de Desarrollo y Control de Versiones: GitHub** para la gestión del código fuente de los tres integrantes y **Notion** para el seguimiento del tablero Kanban. 

## **Ecosistema de Herramientas** 

Para garantizar un flujo de desarrollo estandarizado entre los tres integrantes, se define el siguiente ecosistema de trabajo: 

- **Entorno de Desarrollo Integrado (IDE):** Visual Studio Code (VS Code) con extensiones de linting (Pylint, Flake8) para estandarizar el formato del código Python. 

- **Gestión de Entornos Virtuales:** venv nativo de Python para aislar las dependencias y evitar conflictos de versiones entre las computadoras del equipo. 

- **Gestión de Tareas y Documentación:** Notion (Tablero Kanban con política estricta de WIP Limits y diccionario de datos centralizado). 

- **Control de Versiones:** Git y alojamiento remoto en GitHub. 

## **Estrategia de Repositorio** 

Se implementará un flujo de trabajo basado en el modelo **Feature Branch Workflow** (Flujo de Ramas por Funcionalidad), ideal para equipos pequeños que requieren integración asincrónica. 

###  **Ramas Principales:** 

      - main: Contiene el código estable y funcional, listo para ser ejecutado ante el tribunal o los usuarios finales. 

      - develop: Rama de integración donde convergen y se prueban todas las nuevas características antes de pasar a producción. 

- **Ramas de Trabajo:** Por cada tarjeta en la columna "En Progreso" del Kanban, el desarrollador creará una rama específica desde develop (Ej: 

   - feature/homografia-sur o fix/botonera-ui). Una vez finalizada, se integra mediante un _Pull Request_ . 

- **Política de .gitignore:** Queda estrictamente prohibido subir al repositorio remoto los archivos de video .mp4, la base de datos local datos.sqlite y los archivos de pesos neuronales .pt. El repositorio alojará exclusivamente código fuente e instrucciones de instalación. 

## **Matriz de Riesgos Técnicos** 

|**ID**|**Riesgo Técnico**|**Probabilidad**|**Impacto**|**Estrategia de Mitigación**|
|---|---|---|---|---|
|**RT1**|Estrangulamiento térmico de|Media|Alto|Uso estricto del modelo|



||la laptop por inferencia<br>pesada, causando caída<br>masiva de fotogramas.|||YOLOv8n (Nano) y ejecución<br>del procesamiento en<br>formato diferido (Batch) sin<br>exigencias de tiempo real.|
|---|---|---|---|---|
|**RT2**|Incompatibilidad de rutas de<br>archivos de video y base de<br>datos entre distintos<br>sistemas operativos de los<br>desarrolladores.|Alta|Medio|Implementación obligatoria<br>de la libreríaos.patho<br>pathliben Python para la<br>gestión dinámica y relativa<br>de todos los directorios.|
|**RT3**|Pérdida de integridad en<br>SQLite por bloqueos<br>concurrentes de escritura al<br>procesar y etiquetar<br>simultáneamente.|Baja|Alto|Restringir SQLite a lectura<br>asincrónica, asegurando que<br>las funciones de guardado<br>de recortes operen de<br>manera sincrónica y<br>secuencial.|
|**RT4**|Pérdida severa de IDs<br>(Tracking) en zonas de<br>oclusión masiva del área<br>durante el procesamiento<br>offline.|Alta|Medio|Ajuste del umbralmax_age<br>en ByteTrack para tolerar la<br>pérdida visual temporal, y<br>uso del "Centro de Masa" del<br>equipo para métricas de<br>bloque.|



## **J ustificación de Decisiones (Trade-offs Técnicos)** 

Este apartado documenta por qué se descartaron tecnologías alternativas en favor del stack actual, fundamentando las decisiones de ingeniería ante el tribunal. 

- **Streamlit vs. Arquitectura Híbrida (React/JSX + FastAPI):** Se descartó la creación de un frontend con React (JSX) debido al aumento exponencial de complejidad arquitectónica. Una arquitectura de API separada exige gestionar múltiples entornos de dependencias (pip y npm) y dificulta el empaquetado para la 

- ejecución 100% offline (sin internet) requerida en los clubes. Streamlit centraliza toda la lógica de presentación y procesamiento en un único ecosistema Python. 

-  **Procesamiento Batch (Post-partido) vs. Tiempo Real Vivo:** Se abandonó el procesamiento en vivo debido al elevado riesgo de latencia (FPS bajos) al correr dos instancias de YOLOv8 simultáneas en hardware comercial, sumado a las dificultades logísticas de montar redes LAN cableadas de extremo a extremo en estadios sin infraestructura. El procesamiento Batch asegura el 100% de precisión matemática en la homografía sin comprometer la estabilidad del sistema. 

- **SQLite vs. Motores Cliente-Servidor (PostgreSQL/MySQL):** El MVP requiere portabilidad extrema. Instalar un servidor de base de datos como MySQL en las computadoras de los analistas de video de los clubes añadía una barrera técnica innecesaria. SQLite opera sobre un archivo local directo, siendo suficiente para manejar los volúmenes de datos tácticos generados en la liga regional sin necesidad de configuración en red. 
