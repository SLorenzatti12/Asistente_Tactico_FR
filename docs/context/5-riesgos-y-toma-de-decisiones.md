# Cálculo de Riesgos y Toma de Decisiones 

Lorenzatti - Tribolo - Pesce 

Un buen software no solo debe funcionar bien, sino ser viable en su entorno y anticiparse a las fallas lógicas, operativas y contextuales. 

## **1. Herramientas de Diagnóstico Contextual** 

## **PESTEL (Análisis Macroentorno)** 

- **Político/Legal:** Cumplimiento de normativas de derecho de imagen de los jugadores (Ligas Regionales) al capturar material audiovisual en estadios semi-públicos. 

- **Económico:** Presupuesto limitado de los clubes locales de la LRF y Liga de San Francisco para adquirir infraestructura física permanente (cámaras IP de alta fidelidad, cableado estructurado UTP). 

- **Social:** Resistencia inicial al cambio por parte de cuerpos técnicos tradicionales que confían más en la intuición que en la métrica algorítmica. 

- **Tecnológico:** Disponibilidad de hardware local apto (laptops de gama media/alta) para procesamiento neuronal (YOLOv8) fuera de laboratorios universitarios. 

- **Ecológico:** Nivel de impacto nulo, enfocado en el uso eficiente y optimizado del consumo energético del hardware de procesamiento. 

## **Las 5 Fuerzas de Porter (Análisis de la Industria)** 

- **Rivalidad entre competidores:** Alta en el fútbol de élite (Hudl, InStat), pero **nula** o inexistente en el nicho del fútbol regional amateur/semiprofesional por barreras económicas. 

- **Amenaza de nuevos competidores:** Media. La democratización de los modelos _open-source_ de visión artificial facilita que otros desarrolladores emulen soluciones similares. 

- **Poder de negociación de los proveedores:** Bajo. Se utilizan frameworks libres (Ultralytics, OpenCV, Streamlit). El único proveedor crítico es el fabricante de hardware/cámaras. 

- **Poder de negociación de los clientes:** Alto. Los clubes locales tienen presupuestos acotados; el software debe demostrar un valor de retorno inmediato para justificar su adopción. 

- **Amenaza de productos sustitutos:** Alta (edición y taggeo manual tradicional mediante software gratuito como Kinovea). 

## **Análisis FODA (Foco Principal del Proyecto)** 

## ** Fortalezas (Internas)** 

- El equipo domina las tres áreas clave (PM, IA, Full-Stack). 

- Modelo dual/triple que aporta una perspectiva táctica única (profundidad de bloque). 

- Arquitectura 100% offline; el sistema no depende de internet. 

- Validación previa y directa con 5 usuarios reales de la región. 

## ** Oportunidades (Externas)** 

- Nicho de mercado desatendido (Fútbol regional: LRF y Liga Regional). 

- Creciente interés de los cuerpos técnicos locales por la 

   - profesionalización tecnológica. 

- Escalabilidad del software a otros deportes de campo (hockey, rugby, basket). 

## ** Debilidades (Internas)** 

- El equipo cuenta con disponibilidad horaria cruzada y variable. 

- Redundancia del procesamiento de inferencia (dos o más hilos de video simultáneos). 

- Dependencia estricta de una calibración inicial manual de homografía precisa. 

## ** Amenazas (Externas)** 

- Infraestructura precaria de los estadios regionales (cortes de luz, falta de postes de altura). 

- Pérdida de resolución de imagen o detección por factores climáticos (niebla, lluvia, partidos nocturnos con iluminación deficiente). 

- Desactualización o cambios bruscos en las licencias de las librerías _open-source_ . 

## **2. Detección de 8 Riesgos Reales** 

- **R1 (Técnico):** Caída drástica de los FPS (procesamiento lento) al ejecutar dos o más instancias en paralelo de YOLOv8 en hardware comercial de gama media. 

-  **R2 (Operativo):** Desalineación o errores de medición métrica en el mapa 2D si la cámara se mueve milimétricamente por el viento o vibraciones después de realizar la calibración de la homografía. 

- **R3 (Entorno):** Imposibilidad de conectar físicamente las dos cámaras de fondo a la computadora del analista debido a la longitud de la cancha (más de 100 metros) y falta de cableado idóneo. 

- **R4 (Gestión):** Pérdida de ritmo de desarrollo o cuellos de botella severos por la falta de sincronización presencial periódica del equipo de tres personas. 

- **R5 (Técnico):** Pérdida constante del ID de tracking (ByteTrack) cuando los jugadores se agrupan masivamente en pelotas paradas dentro del área (oclusión severa). 

- **R6 (Operativo):** Rechazo de la interfaz de Streamlit por parte del ayudante de campo si la visualización en vivo o alertas saturan su monitor durante el partido. 

-  **R7 (Entorno):** Falla en la detección de la pelota o jugadores lejanos debido a la baja resolución de las cámaras adquiridas o iluminación deficiente en partidos nocturnos. 

- **R8 (Gestión):** Desviación del alcance del MVP por intentar incorporar peticiones de última hora de los entrenadores (Scope Creep). 

## **3. Matriz de Prioridad** 

Para mapear los riesgos de forma matemática, asignamos una escala del 1 al 5 tanto para la Probabilidad como para el Impacto 

|**Riesgo**|**Probabilidad**<br>**(1-5)**|**Impacto (1-**<br>**5)**|**Criticidad (PxI)**|**Zona de**<br>**Impacto**|
|---|---|---|---|---|
|**R1 (Bajo FPS Dual)**|4|5|20|Crítica|
|**R3 (Conectividad de distancia)**|4|4|16|Crítica|
|**R2 (Error de homografía por**<br>**clima)**|3|4|12|Alta|
|**R5(Oclusión en área)**|5|2|10|Media|
|**R4 (Desconexión del equipo)**|2|4|8|Media|
|**R7 (Baja Luz/Resolución)**|3|2|6|Baja|
|**R6 (Saturación de la interfaz**<br>**UX)**|2|3|6|Baja|
|**R8 (Scope Creep)**|2|2|4|Baja|



## **4. Mitigación de riesgos** 

## **R1 - Caída de FPS por procesamiento dual de video** 

- **Estrategia:** Mitigación técnica mediante optimización de software. 

- **Acción Preventiva (Antes):** El **Lead AI Engineer** implementará la inferencia utilizando el modelo **YOLOv8n (versión Nano)** , que es el más ligero de la familia. Además, se exportarán los pesos del modelo a formato **ONNX** o **TensorRT** para acelerar el procesamiento por hardware en arquitecturas tanto de CPU como de GPU locales. 

- **Acción Correctiva (Durante/Después):** Si los FPS caen por debajo de 10, el sistema activará un módulo de _Frame Skipping_ asincrónico (procesar un frame de cada tres en hilos de ejecución separados por OpenCV), manteniendo la fluidez de la interfaz táctica en Streamlit sin colgar el procesador. 

## **R3 - Imposibilidad de conectar las cámaras por la distancia del campo** 

- **Estrategia:** Mitigación mediante infraestructura física cableada y contingencia de almacenamiento local. 

- **Acción Preventiva (Antes):** El **Full-Stack Architect** diseñará un despliegue de red puramente cableado e independiente. Se utilizarán cables UTP Categoría 6 para exteriores junto con inyectores y extensores de señal **PoE (Power over Ethernet) activos** , o bien bobinas de cable de red blindado (STP) aptas para cubrir tramos de hasta 120 metros. Esto permitirá conectar las cámaras de forma física y directa a un switch Ethernet conectado a la laptop del analista, garantizando la transmisión de datos sin pérdida de paquetes y sin depender de señales Wi-Fi inexistentes en el predio. 

- **Acción Correctiva (Durante/Después):** Si las limitaciones físicas del estadio impiden el tendido seguro de los cables (por ejemplo, cruce de tribunas o sectores sin acceso perimetral), el sistema mutará de forma inmediata a **Modo Post-Partido (Batch Processing)** . Las cámaras de fondo grabarán el encuentro localmente en sus tarjetas SD internas de alta velocidad. Al finalizar cada tiempo o el partido, el analista extraerá físicamente las tarjetas para procesar los archivos de video en bloque en la laptop, ejecutando el tagueo y las métricas en pocos minutos de forma totalmente offline. 

## **R2 - Descalibración de la matriz de homografía por factores externos** 

- **Estrategia:** Mitigación operativa e interfaz de usuario. 

- **Acción Preventiva (Antes):** Diseñar un sistema de montaje rígido y seguro para las cámaras de fondo (mordazas mecánicas de alta presión o trípodes con contrapeso). El **Full-Stack** programará una función en Notion/Streamlit para almacenar los 4 puntos de referencia iniciales como un _preset_ fijo de la cancha. 

- **Acción Correctiva (Durante/Después):** Si durante el partido se detecta un desfase visual en el mapa 2D, la interfaz de Streamlit contará con un botón de **"Recalibración Rápida"** . Al presionarlo, el sistema pausará la inferencia táctica por 10 segundos para permitirle al **Product Manager** reajustar los 4 puntos esquineros sobre el fotograma actual sin reiniciar el software ni perder los datos taggeados previamente. 

## **R5 - Pérdida constante del ID de tracking por oclusiones severas en el área (pelotas paradas)** 

- **Estrategia:** Mitigación algorítmica y tolerancia al fallo posicional. 

- **Acción Preventiva (Antes):** El **Lead AI Engineer** calibrará el algoritmo de tracking ( **ByteTrack / Sort** ) ajustando los umbrales de persistencia temporal (parámetro max_age). Esto le permite al sistema "esperar" un número determinado de fotogramas antes de borrar el ID de un jugador que quedó tapado, dándole tiempo a que el tumulto se desarme y el jugador vuelva a ser visible en el área. 

- **Acción Correctiva (Durante/Después):** Si durante un córner o tiro libre los IDs de tracking se mezclan inevitablemente, el sistema priorizará la métrica del **Centro de Masa del Bloque** sobre las identidades individuales. Para el mapa 2D, el MVP computará el agrupamiento como un "bloque defensivo/ofensivo único", evitando que los errores de ID afecten los cálculos de distancia vertical generales. 

## **R4 - Pérdida de ritmo de desarrollo por falta de sincronización presencial del equipo** 

- **Estrategia:** Mitigación organizativa y disciplina de flujo (Kanban). 

- **Acción Preventiva (Antes):** Se implementará de forma estricta el **Setup Organizacional** en Notion. Vos, como **Product Manager** , asegurarás que las Historias de Usuario estén desglosadas en tareas atómicas y claras en el tablero. Se respetará el hito de sincronización cada 5 o 7 días para coordinar operativamente el avance. 

- **Acción Correctiva (Durante/Después):** Si se detecta un estancamiento de tareas por más de un ciclo, el protocolo dicta congelar el _Backlog_ y activar la regla de **WIP Limit (Máximo 2 tareas en progreso)** . Ningún integrante podrá asumir nuevos desafíos; el equipo completo concentrará sus horas disponibles en destrabar el cuello de botella técnico del compañero afectado. 

## **R7 - Falla en la detección por baja resolución de cámaras o iluminación deficiente en partidos nocturnos** 

- **Estrategia:** Mitigación mediante pre-procesamiento de imagen y optimización de confianza. 

- **Acción Preventiva (Antes):** El **Lead AI Engineer** entrenará o ajustará las capas de entrada del modelo YOLOv8 aplicando técnicas de aumentación de datos ( _data augmentation_ ) que simulan ruido digital, baja luminosidad y desenfoque. Se configurarán las cámaras con un seteo de exposición manual fijo para evitar que los focos de la cancha encandilen el lente. 

- **Acción Correctiva (Durante/Después):** Si las condiciones climáticas o la luz del estadio son extremadamente deficientes durante el partido, la interfaz de Streamlit permitirá al usuario reducir manualmente el **Umbral de Confianza (Confidence Threshold)** del modelo de 0.5 a 0.35. Esto aumentará la sensibilidad de detección de la IA, complementandose con un filtro de suavizado de movimiento (filtro de Kalman) para evitar falsos positivos. 

## **R6 - Saturación visual de la interfaz (UX) del Ayudante de Campo durante el partido** 

- **Estrategia:** Diseño de interfaz minimalista y jerarquía de alertas. 

- **Acción Preventiva (Antes):** Diseñar un layout limpio en **Streamlit** enfocado en la usabilidad "bajo presión". El video principal ocupará el centro, el mapa 2D estará en un panel lateral limpio y la botonera de taggeo tendrá botones grandes y espaciados. Las alertas tácticas no emitirán ventanas emergentes ( _pop-ups_ ); se mostrarán como un discreto indicador de color (estilo semáforo). 

- **Acción Correctiva (Durante/Después):** El **Full-Stack Architect** programará un switch de "Modo Compacto / Modo Extendido" en la barra lateral. Si el Ayudante de Campo se siente abrumado por los gráficos en tiempo real, podrá alternar a la vista compacta, la cual oculta las métricas secundarias en vivo y deja únicamente activos el monitor de video y los botones de recorte rápido. 

## **R8 - Desviación del alcance del MVP por peticiones externas de los entrenadores (Scope Creep)** 

- **Estrategia:** Gestión estricta de requerimientos y blindaje del proyecto. 

- **Acción Preventiva (Antes):** Vos ( **Facundo** ) actuarás como la única interfaz con los cuerpos técnicos (Pirulo, Maxi, etc.). Toda sugerencia o requerimiento nuevo que surja durante las pruebas de campo se registrará exclusivamente en la sección **"Idea / Backlog a Futuro"** de Notion, dejando asentado por escrito que no forma parte del alcance académico inicial. 

- **Acción Correctiva (Durante/Después):** Ante la insistencia de un usuario por una función compleja (como el reconocimiento de dorsales automático), se le exhibirá el documento formal de "Límites del MVP" validado por la facultad. Se le explicará que dicha funcionalidad requiere una etapa de investigación independiente (Sprint posterior) y que la prioridad actual del equipo es garantizar la infalibilidad del taggeo manual y la homografía de fondo. 
