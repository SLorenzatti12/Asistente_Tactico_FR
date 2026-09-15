# Definición del MVP 

# Definición del Producto Mínimo Viable (MVP) 

Lorenzatti - Tribolo - Pesce 

Definir los límites del **MVP (Producto Mínimo Viable)** es el paso más crítico para evitar el "scope creep" (alcance desmedido) y asegurar que el equipo de tres personas pueda entregar una herramienta funcional y de alta calidad para el fútbol regional. 

Basándonos en la evidencia recolectada (el calvario del taggeo manual, la necesidad de apoyo visual rápido y la brecha de ritmo), aquí están los límites propuestos para el MVP del **Asistente Táctico** 

### **1. Lo que el MVP S hará (Alcance Funcional)** 

El foco está en la captura dual sincronizada para obtener una visión total del campo en tiempo real: 

- **Procesamiento Dual en Tiempo Real:** El sistema capturará y procesará simultáneamente dos señales de video provenientes de cámaras ubicadas en los fondos del campo. El procesamiento será local (offline) para garantizar estabilidad. 

- **Detección y Tracking Unificado:** Uso de YOLOv8 para detectar jugadores y pelota en ambos feeds. Los datos se integrarán en un único **Mapa Táctico 2D** (vista cenital) que mostrará la posición de los 22 jugadores en una sola interfaz. 

- **Doble Matriz de Homografía:** El sistema permitirá calibrar cada cámara de forma independiente para transformar las perspectivas de fondo en coordenadas métricas reales, unificándolas en el plano central de la cancha. 

- **Botonera de Taggeo en Vivo:** Interfaz en Streamlit con botones de eventos críticos ( _Presión, Salida, Transición_ ). Al presionar, el sistema extraerá y guardará automáticamente el clip de los últimos 10 segundos de la cámara que tenga la acción principal. 

- **Métrica de "Bloque y Profundidad":** Cálculo en tiempo real de la distancia vertical entre la línea defensiva y la de ataque, aprovechando la perspectiva de fondo que es ideal para medir el escalonamiento táctico. 

- **Registro del "Semáforo" Histórico:** Formulario post-partido para almacenar la evaluación subjetiva del cuerpo técnico en una base de datos SQLite local. 

### **2. Lo que el MVP NO hará (Límites Claros)** 

Para garantizar la entrega con un equipo de 3 personas, quedan fuera: 

- **Sincronización de Identidad (ID Transfer):** Al cruzar la mitad de cancha, un jugador podría cambiar su número de identificación (ID) en el sistema. El MVP prioriza la posición en el mapa sobre la persistencia de la identidad única entre cámaras. 

- **Reconocimiento de Dorsales (OCR):** No se identificarán números de camiseta automáticamente debido a la distancia de las cámaras de fondo. La asignación de nombres será manual o por posición. 

- **Streaming hacia la Nube:** El sistema es estrictamente local. No habrá retransmisión por internet ni acceso remoto durante el partido. 

- **Métricas de Carga Física:** No se medirán aceleraciones ni esfuerzos metabólicos; el alcance es puramente táctico y posicional. 

### **3. Restricciones Técnicas (El "Setup")** 

- **Conectividad:** La captura se realizará mediante cámaras IP conectadas por cable UTP o red local dedicada (RTSP), evitando el uso de Wi-Fi público de los estadios. 

- **Rendimiento (Performance):** El sistema deberá mantener una tasa de procesamiento de **10-15 FPS por cámara** (procesamiento balanceado) en una laptop de gama media con soporte de aceleración por hardware (Cuda/TensorRT). 

- **Desarrollo:** Interfaz íntegramente en **Streamlit** y lógica de visión en **Python/OpenCV** , optimizada para procesamiento asincrónico de dos hilos de video. 

## Historias de Usuario 

Para facilitar la planificación y priorización dentro de los límites definidos del MVP, las Historias de Usuario se organizarán en **Bloques.** 

### **Bloque 1: Operación en Tiempo Real (Durante el partido)** 

1. **Como Ayudante de Campo** , quiero registrar una "Presión" o "Salida" con un solo clic en la interfaz, **para** tener el clip de video cortado automáticamente y mostrarlo al DT en el entretiempo sin perder tiempo editando. 

2. **Como Director Técnico** , quiero visualizar la posición de los 22 jugadores en un mapa 2D unificado, **para** detectar desajustes tácticos y espacios libres que no alcanzo a ver desde el nivel del suelo por el ángulo de visión. 

3. **Como Ayudante de Campo** , quiero que el sistema me muestre una alerta visual cuando la distancia entre la línea defensiva y la de ataque supere los metros establecidos, **para** corregir la compacidad (bloque) del equipo de inmediato. 

4. **Como Director Técnico** , quiero revisar una jugada de pelota parada desde la cámara de fondo 10 segundos después de ocurrida, **para** dar una indicación precisa sobre una marca perdida antes de que se reanude el juego o en el próximo parate. 

5. **Como Ayudante de Campo** , quiero operar el sistema de manera 100% local (offline), **para** asegurar que el procesamiento de video y el taggeo no se interrumpan por la falta de conectividad Wi-Fi en el estadio. 

### **Bloque 2: Análisis Post-Partido e Inteligencia** 

6. **Como Director Técnico** , quiero acceder el lunes por la mañana a una lista de clips de "Transiciones" ya procesados por la IA, **para** ahorrar las 2 horas de edición manual que actualmente dedico al videoanálisis semanal. 

7. **Como Integrante del Cuerpo Técnico** , quiero completar el formulario del "Semáforo de Rendimiento" al finalizar el encuentro, **para** que la evaluación de cada jugador quede registrada de forma objetiva y no dependa únicamente de la memoria subjetiva del lunes. 

8. **Como Coordinador del Club** , quiero consultar el historial de calificaciones y minutos jugados de los refuerzos, **para** tomar decisiones fundamentadas sobre la continuidad de los jugadores al finalizar la temporada. 

9. **Como Director Técnico** , quiero alternar entre la vista de la Cámara Norte y la Cámara Sur en la pantalla principal, **para** analizar con detalle las acciones que ocurren en las áreas críticas de fondo bajo una perspectiva de profundidad. 

### **Bloque 3: Validación y Entrenamiento** 

10. **Como Jugador** , quiero observar mi error posicional en un clip de 10 segundos durante la charla técnica, **para** comprender visualmente la corrección táctica que me pide el DT y evitar discusiones por recuerdos diferentes de la jugada. 

11. **Como Analista (Lead AI)** , quiero calibrar las dos cámaras de fondo mediante una matriz de homografía al inicio del partido, **para** garantizar que los puntos proyectados en el mapa 2D representen distancias métricas reales sobre el campo. 

## Priorización de Historias de Usuario 

Para priorizar las historias de usuario de forma profesional en un proyecto de ingeniería, utilizaremos el método **MoSCoW** (Must have, Should have, Could have, Won't have). 

#### **1. Prioridad Alta: "Must Have" (Lo que el sistema DEBE tener)** 

Estas historias son el núcleo técnico. Sin ellas, el software no cumple su propósito básico o no es viable en la cancha. 

- **Historia 11 (Calibración/Homografía):** Es el cimiento técnico. Si el **Lead AI** no logra convertir los píxeles a metros, no hay mapa 2D ni métricas reales. 

- **Historia 5 (Operación Offline):** Es una restricción técnica crítica validada en las entrevistas. Si el sistema depende de internet, fallará en los estadios de la liga. 

-  **Historia 2 (Mapa 2D Unificado):** Es el valor visual principal. Permite al DT ver el campo completo desde una perspectiva cenital, unificando las dos cámaras de fondo. 

- **Historia 9 (Alternar Vistas de Cámara):** Al tener dos cámaras de fondo, el **FullStack** debe permitir que el usuario elija qué arco mirar. Es esencial para la navegación básica. 

- **Historia 1 (Taggeo One-Click):** Ataca el "dolor" más grande detectado: las 2 horas de edición manual. Es quizá la funcionalidad que más espera el usuario. 

#### **2. Prioridad Media: "Should Have" (Lo que DEBERA tener)** 

Son funcionalidades de alto valor táctico que diferencian tu proyecto de una simple grabación de video, pero que podrían entregarse unos días después del núcleo básico. 

- **Historia 3 (Alertas de Bloque/Compacidad):** Es la métrica "estrella". Aprovecha las cámaras de fondo para medir la profundidad. Le da el nivel de "fútbol profesional" al proyecto. 

- **Historia 4 (Revisión de Pelota Parada):** Es vital para el entretiempo. Permite corregir errores específicos de marca que el ojo humano pierde por la velocidad de la jugada. 

- **Historia 6 (Acceso a clips el lunes):** Es la extensión del taggeo automático. Garantiza que el trabajo del domingo se traduzca en ahorro de tiempo real para la charla del martes. 

#### **3. Prioridad Baja: "Could Have" (Lo que PODRA tener)** 

Son mejoras administrativas o de uso secundario. Si el tiempo aprieta, estas tareas pueden pasar al "Backlog" de la siguiente etapa. 

- **Historia 7 (Semáforo de Rendimiento):** Es un gran aporte institucional, pero el análisis táctico puede vivir sin esto en una primera demo técnica. 

- **Historia 10 (Clips para el jugador):** Es un caso de uso externo. Aunque aporta valor, el foco del MVP es la toma de decisiones del cuerpo técnico. 

- **Historia 8 (Historial para el Coordinador):** Es una funcionalidad de análisis a largo plazo (meses). No es crítica para validar el funcionamiento del sistema en los primeros partidos. 
