# Elección de la metodología de Trabajo y el Setup Organizacional 

Lorenzatti - Tribolo - Pesce 

Para un equipo de estudiantes de ingeniería con horarios cruzados y sin posibilidad de reuniones diarias fijas, **Kanban es la elección más inteligente y honesta** . 

Intentar hacer Scrum convencional cuando no podemos garantizar una _Daily_ de o cierres de _Sprint_ rígidos suele terminar en frustración y burocracia innecesaria. Kanban, en cambio, se adapta al **flujo de trabajo real** : las tareas se mueven a medida que hay disponibilidad. 

## Metodología: Kanban (Flujo Continuo) 

#### **Marco Organizacional y Metodología de Trabajo** 

Para la gestión y ejecución de este proyecto, se ha optado por la metodología Kanban. Esta elección se fundamenta en la necesidad de mantener un flujo de trabajo constante y flexible, adaptándose a la disponibilidad horaria variable de los integrantes del equipo y priorizando el avance asincrónico sobre las estructuras rígidas de tiempo. 

#### **Justificación de la Metodología** 

A diferencia de otros marcos ágiles que requieren reuniones de sincronización diarias (Daily Stand-ups) o cierres de ciclo estancos (Sprints), Kanban permite una gestión visual del trabajo que se ajusta a la realidad operativa del proyecto: 

- **Flexibilidad operativa:** El trabajo avanza según la capacidad real del equipo en cada momento, evitando la burocracia en periodos de baja disponibilidad. 

- **Foco en la finalización:** Mediante la aplicación de límites de trabajo en progreso (WIP Limits), el equipo se asegura de completar tareas críticas antes de iniciar nuevas, reduciendo el tiempo de entrega de funcionalidades clave. 

- **Gestión asincrónica:** El tablero de tareas actúa como la única fuente de verdad, permitiendo que cualquier integrante retome el trabajo en sus horarios disponibles sin perder el contexto del estado global del proyecto. 

#### **Estructura del Flujo de Trabajo (Workflow)** 

El proceso de desarrollo se visualiza a través de un tablero organizado en las siguientes etapas: 

1. **Idea:** Repositorio de requerimientos, ideas y funcionalidades técnicas pendientes de priorización. 

2. **Por Hacer:** Tareas definidas y priorizadas que están listas para ser tomadas por el equipo, pero que aún no han iniciado su ejecución. 

3. **En Progreso:** Desarrollo activo de módulos de software o tareas de investigación técnica. 

4. **Validación:** Fase de pruebas del código utilizando los registros de video recolectados en los clubes locales para asegurar la precisión del tracking y la homografía. 

5. **Realizado:** Funcionalidades completamente integradas, testeadas y documentadas. 

6. **Detenidas:** Tareas que se encuentren en pausa por falta de algún tipo de recurso 

## Estructura del Tablero 

Para que el Kanban funcione, las columnas deben reflejar nuestro proceso técnico: 

|**Columna**|**Descripción**|
|---|---|
|**Idea**|Ideas y requerimientos brutos|
|**Por Hacer**|Las tareas priorizadas listas para iniciar su ejecución|
|**En Progreso**|Lo que se está programando o investigando en este momento.|
|**Validación**|El código funciona pero falta probarlo con video real de la LRF.|
|**Realizado**|Funcionalidad terminada, testeada y documentada.|
|**Detenida**|Tareas pausadas por falta de algún tipo de recursos|



## Roles, Comunicación y Tareas 

#### **1. Product Manager & UX (El "Vínculo con la Cancha")** 

**Responsable:** .Este rol se encarga de que el software no sea solo un "ejercicio de código", sino una herramienta que el DT realmente pueda usar bajo presión. 

####  **Responsabilidades:** 

- **Validación Continua:** Traducir los "dolores" de los DTs en requerimientos técnicos (ej: "Maxi necesita que el taggeo sea automático"). 

- **Lógica de Negocio:** Definir los criterios del "Semáforo" de rendimiento y la estructura de los reportes post-partido. 

- **Diseño de Experiencia (UX):** Diseñar cómo se deben ver las alertas en Streamlit para que no saturen al Ayudante de Campo. 

- **QA Táctico:** Probar el sistema con ojos de "entrenador" y marcar si los datos que tira la IA tienen sentido futbolístico. 

#### **2. Lead AI & Computer Vision Engineer (El "Cerebro")** 

**Responsable:** Se encarga del procesamiento pesado de imágenes. Es el rol más técnico en cuanto a algoritmos de visión artificial. 

####  **Responsabilidades:** 

- **Implementación de YOLOv8:** Configurar y tunear el modelo para que detecte jugadores, árbitros y pelota en condiciones de luz de liga regional. 

- **Tracking & ID:** Lograr que el sistema no "pierda" a un jugador cuando se cruza con otro (Sort/DeepSort). 

- **Matriz de Homografía:** Desarrollar el script que convierte los píxeles del video en metros reales en un plano 2D (la vista de pájaro). 

- **Optimización de Inferencia:** Asegurarse de que el modelo corra a una velocidad decente en una laptop común sin necesidad de una supercomputadora. 

#### **3. Full-Stack Architect & Integrator (El "Constructor")** 

**Responsable:** Es el encargado de que todas las piezas sueltas (el script de IA, la base de datos y la interfaz) funcionen como un solo producto robusto. 

####  **Responsabilidades:** 

- **Desarrollo en Streamlit:** Crear la interfaz interactiva, la botonera de tagueo y los dashboards de visualización de datos. 

- **Gestión de Datos (Backend):** Diseñar y mantener la base de datos (SQLite) donde se guardará la historia clínica táctica del club. 

- **Arquitectura Offline:** Configurar el sistema para que funcione localmente, gestionando la entrada de video (vía OpenCV) y el almacenamiento de clips tagueados. 

- **Pipeline de Integración:** Unir el output del "Cerebro" (coordenadas de IA) con la interfaz para que el usuario vea los dibujos tácticos sobre el video. 

## Gestión y Sincronización 

Para garantizar la continuidad del desarrollo y la transparencia entre los integrantes, se han establecido mecanismos específicos de comunicación y control de flujo que permiten el avance asincrónico sin perder la alineación de los objetivos. 

### **Mecanismos de Sincronización** 

Dada la naturaleza académica y la variabilidad de horarios de los integrantes, la sincronización se articulará principalmente mediante encuentros periódicos y un soporte de comunicación bajo demanda: 

- **Reuniones de coordinación:** Se establece un hito de sincronización cada 7 o 10 días con el objetivo de coordinar la realización de tareas operativas y actualizar el estado de avance de cada miembro del equipo de forma directa. 

- **Canal de actualización complementario:** El envío de informes de progreso detallados (tareas finalizadas, bloqueos encontrados y objetivos del ciclo) a través del canal grupal (WhatsApp) pasará a un segundo plano, reservándose únicamente para los casos en que sea solicitado explícitamente por el equipo. 

- **Propósito:** Este enfoque dinámico prioriza los encuentros frecuentes de alineación para resolver dependencias rápidamente, garantizando una visión clara del avance global y facilitando la toma de decisiones inmediata sobre el Backlog. 

#### **Plataforma de Gestión: Notion** 

La gestión integral de las tareas, la documentación técnica y los activos del proyecto se centralizará en **Notion** . Esta herramienta ha sido seleccionada por las siguientes ventajas competitivas: 

- **Flexibilidad de visualización:** Permite utilizar plantillas de tableros Kanban optimizadas por la comunidad, adaptándolas específicamente a un flujo de ingeniería de software. 

- **Centralización de la información:** Notion actúa como un repositorio único donde conviven las Historias de Usuario, el Diccionario de Datos y el seguimiento de las tareas en tiempo real. 

- **Accesibilidad:** Facilita el trabajo asincrónico al permitir comentarios, menciones y adjuntos directamente en las tarjetas de trabajo. 

#### **Control de Flujo y Límites de Trabajo (WIP)** 

Para evitar la dispersión de esfuerzos y asegurar una alta tasa de finalización de funcionalidades, se ha implementado una política estricta de **Límite de Trabajo en Progreso (WIP Limit)** : 

- **Capacidad por integrante:** Se permite un máximo de **2 tareas en simultáneo por persona** en la columna "In Progress". 

- **Justificación:** Esta restricción es fundamental para identificar cuellos de botella de forma temprana. Si un integrante alcanza su límite, el protocolo dicta que debe colaborar en la finalización de tareas de sus compañeros o resolver bloqueos antes de iniciar una nueva actividad del _To Do_ . 

- **Impacto en el MVP:** Esta medida asegura que los módulos críticos (como la Homografía o la Interfaz de Tagueo) reciban atención plena hasta su validación técnica definitiva. 
