#  Proyecto Analizador Táctico 

## _<u>Proyecto Analizador Táctico</u>_ 

_Todo lo que se pueda medir, se puede mejorar_ 

### 1. Definición del Problema 

1. El Efecto Burbuja: En la Liga Regional de San Francisco, los clubes dominantes suelen ganar por "peso propio" (mejores jugadores o presupuesto). Esto oculta deficiencias tácticas que solo quedan expuestas cuando salen a competir a nivel federal o provincial. La falta de datos objetivos impide que estos clubes vean sus techos reales antes de que sea tarde. 

2. La Inviabilidad del Ascenso (LRF): El caso de la Liga Rafaelina es un ejemplo clásico de falta de transición táctica. Un equipo de Primera B asciende con una estructura amateur y se encuentra con un ritmo de Primera A para el cual no tiene herramientas de análisis. El sistema permitiría que un equipo con menos recursos pueda compensar esa diferencia mediante una preparación táctica basada en datos, optimizando cada movimiento para maximizar sus chances de permanencia. 

3. Sesgo Cognitivo en Tiempo Real: Durante un partido, el entrenador está bajo estrés y puede perder de vista patrones tácticos (como un carrilero que no retrocede o un hueco constante en el mediocampo). El sistema actuaría como un "segundo par de ojos" objetivo. 

4. Inoperancia del Análisis Post-Partido: En ligas como la de San Francisco o la Rafaelina, el análisis posterior suele ser inexistente o puramente basado en recuerdos, perdiendo la oportunidad de corregir movimientos tácticos específicos con evidencia visual. 

Resumen del problema: "El proyecto busca mitigar la brecha competitiva en las ligas regionales, permitiendo que los clubes con menores presupuestos profesionalicen su análisis táctico y que los clubes grandes rompan su burbuja de rendimiento local mediante estándares de medición objetivos." 

### 2. Perfeccionamiento del Apartado Técnico 

Dado que el corazón del proyecto es el reconocimiento de patrones mediante cámara, usaremos un stack que soporte Computer Vision (CV) y Machine Learning (ML) de manera eficiente. 

#### **Detección y Procesamiento (El Core)** 

- Modelo de Detección: YOLOv8 (You Only Look Once). Es el estándar actual para detectar objetos (jugadores, pelota, árbitros) en tiempo real con alta precisión y baja latencia. 

- Seguimiento (Tracking): ByteTrack o DeepSORT. Son bibliotecas que permiten que la IA "entienda" que el Jugador A sigue siendo el Jugador A aunque se cruce con otro en la imagen. 

- Lógica Táctica: utilizaremos Heurísticas Tácticas programadas (distintas librerías o herramientas como: MPL Soccer, OpenCv, SciKit-Learn) en Python que analicen la distancia entre líneas o la densidad de jugadores en ciertas zonas del campo. 

#### **Stack de Desarrollo** 

- Lenguaje: Python. Es indispensable por la integración con bibliotecas de IA. 

- Framework de Backend: FastAPI. Ideal para recibir el streaming de video y procesarlo rápidamente. 

- Edge Computing: Para que la app sea útil en canchas de San Francisco donde quizás el 4G es inestable, lo ideal es que el procesamiento de IA ocurra on-device (usando TensorFlow Lite o CoreML) en lugar de enviarlo a la nube. 

- Tratamiento (Python/R): Transformás las coordenadas de los píxeles en coordenadas reales de campo (homografía). 

- Análisis de Niveles: Usar algoritmos de clustering (K-means) para identificar patrones de movimiento y compararlos con patrones de equipos de mayor nivel. 

### 3. Validación Legal y tica 

Tu avance en este punto es muy sólido. Es clave destacar que: 

- Cumplimiento Normativo: Te ajustás a la Regla 4 de la FIFA, permitiendo el uso táctico siempre que no interfiera con el arbitraje. 

- Contexto Local: Haber verificado que ni la Liga Rafaelina ni la de San Francisco tienen restricciones específicas nos da "vía libre" para pruebas piloto reales. 

- Privacidad: El enfoque en el consentimiento para menores es mandatorio para que el proyecto sea viable en clubes de divisiones inferiores. 

### 4. Comparación contra el software existente 

|Característica|Ecosistema de Élite (Hudl,<br>Catapult, Opta)|Proyecto (Asistente Táctico<br>Amateur)|
|---|---|---|
|Enfoque|Especializado: Necesitás un|Integrador: Una sola herramienta|



||software para video, otro<br>para GPS y otro para Big<br>Data.|que extrae datos de video y genera<br>táctica.|
|---|---|---|
|Captura de Datos|Híbrida: Sensores físicos<br>(GPS) + Cámaras fjas de alta<br>gama.|Visual: Exclusivamente mediante la<br>cámara del smartphone/tablet<br>(Computer Vision).|
|Costo|Muy Alto: Miles de dólares en<br>licencias y hardware anual.|Accesible: Modelo SaaS o App<br>única, sin hardware adicional.|
|Requerimientos<br>de Personal|Staf completo: Analistas de<br>video, científcos de datos y<br>preparados físicos.|Autogestionado: Diseñado para que<br>el propio DT o un ayudante lo<br>operen.|
|Análisis Táctico|Manual/Semiautomático:<br>Alguien debe "cortar" y<br>etiquetar las jugadas.|Automatizado: La IA (YOLOv8)<br>reconoce patrones y sugiere<br>ajustes sin intervención humana<br>constante.|



Para entender dónde se sitúa el proyecto respecto a los gigantes de la industria, es útil visualizarlo no como un competidor directo de una herramienta específica, sino como un integrador de funciones diseñado para un mercado que hoy está desatendido por ser "caro y complejo". 

#### **La ventaja competitiva: El "All-in-One" mediante Visión Artificial** 

Lo que hace que nuestra propuesta sea potente es que utiliza la Visión Artificial para suplir la falta de otras tecnologías. En la élite, si querés saber la distancia entre líneas, usás datos de GPS. En tu proyecto, como el club amateur no tiene GPS, usás la cámara para estimar esa distancia. 

¿Cómo se traduce esto en funciones integradas? 

1. Sustitución del GPS (Tracking Óptico): Al detectar a los 22 jugadores con YOLO, podés calcular distancias, velocidades estimadas y mapas de calor sin que los jugadores usen chalecos. 

2. Automatización del "Tagging" (Video Análisis): En lugar de que un analista presione un botón cada vez que hay un córner, tu IA puede detectar la acumulación de jugadores en el área y marcar el evento automáticamente. 

3. Consultoría Táctica en Tiempo Real: Mientras que Sportscode solo te muestra el video, tu idea propone un Modo Observador que procesa la información y sugiere cambios (ej. _"El lateral derecho está quedando muy expuesto"_ ), actuando como un asistente virtual. 

#### **El impacto en las ligas de interés** 

Respecto a la problemática de la Liga de San Francisco y la Rafaelina que se mencionaron anteriormente, esta solución ataca el núcleo del problema: 

- Clubes "Grandes" de la zona: Podrán medir su rendimiento con métricas reales antes de cruzarse con equipos de otras ligas, rompiendo esa burbuja de superioridad local que a veces es engañosa. 

- Clubes que ascienden (Efecto Ascensor): Tendrán una herramienta de "inteligencia competitiva" para estudiar el ritmo de la categoría superior y adaptar su sistema táctico rápidamente sin necesidad de un presupuesto de Primera División. 

### 5. Aclaraciones sobre el hardware del sistema 

#### Ventaja Estratégica del Procesamiento en Laptop 

El uso de hardware dedicado (laptop/PC) permite abordar la problemática de las ligas regionales (como la de San Francisco o la Rafaelina) con herramientas de nivel profesional: 

- Mayor Profundidad de Análisis: Una laptop puede procesar video en 4K o múltiples flujos de cámara simultáneamente. Esto permite una visión panorámica completa de la cancha, eliminando los puntos ciegos que tendría un teléfono. 

- Análisis Multitarea: Mientras el backend (Python) procesa el tracking con YOLOv8, el frontend puede mostrar tableros de control en tiempo real, mapas de calor y alertas tácticas sin degradar el rendimiento. 

- Almacenamiento Local: Los clubes a menudo tienen problemas de conectividad en sus estadios. Una aplicación de escritorio permite trabajar de forma 100% offline, guardando los datos en una base de datos local y sincronizando con la nube solo cuando haya una conexión estable. 

#### **Apartado Técnico: Stack para Escritorio / Web App** 

Al optar por este enfoque, el stack tecnológico se vuelve más robusto y modular: 

##### **Opción A: Aplicación de Escritorio (High Performance)** 

- Lenguaje: Python. 

- Interfaz (GUI): PyQt6 o PySide6. Permiten crear interfaces profesionales con integración nativa para mostrar el stream de video procesado. 

- Motor de IA: OpenVINO (si la laptop tiene procesador Intel) o TensorRT (si tiene placa NVIDIA). Estas herramientas optimizan YOLOv8 para que corra a máximos FPS en hardware de escritorio. 

- Base de Datos: SQLite para persistencia local sencilla o PostgreSQL si se planea escalar a una red de computadoras en el club. 

##### **Opción B: Web App con Procesamiento Local (Moderno)** 

- Backend: FastAPI corriendo en la laptop como un servidor local. 

- Frontend: React o Next.js. El navegador se conecta al "localhost" de la laptop. Esto permitiría que el técnico use la laptop para procesar, pero pueda ver los resultados en una tablet conectada a la misma red Wi-Fi (cumpliendo la idea de la app móvil como "espejo" o agregado). 

- Streaming: WebRTC para transmitir el video procesado desde el backend al navegador con latencia mínima. 

 **Streamlit o Dash (Plotly)** Son frameworks de Python que permiten convertir tus scripts de análisis en aplicaciones web de forma inmediata. 

- **Ventaja:** Permiten crear sliders, gráficos que se actualizan cada segundo y tablas de posiciones en tiempo real sin salir del ecosistema Python. 

- **Uso:** El backend procesa con YOLOv8 y envía las coordenadas a un dashboard de Streamlit que el asistente técnico ve en la misma laptop o en una tablet conectada a la red local. 

#### **Captura y Hardware** 

- Cámaras IP / RTSP: Se pueden usar cámaras de seguridad de alta resolución instaladas en las torres de iluminación o la zona de prensa. La laptop se conecta a ellas por red. 

- Cámaras de Acción (GoPro/Similares): Conectadas por HDMI a una capturadora de video en la laptop para máxima calidad de imagen. 

### 6. Estructura del Proyecto 

Para perfilar la estructura de un proyecto de esta envergadura, que integra visión artificial, procesamiento de datos en tiempo real y una interfaz de usuario, es fundamental adoptar un enfoque modular. Esto permite separar la lógica de la inteligencia artificial de la visualización y el manejo de datos, facilitando el mantenimiento y la escalabilidad. 

#### **1. Estructura de Directorios (Organización Modular)** 

asistente-tactico/ |. - app.py  src/ | [;& core/ | |~ analysis/ |  utils/ | lL database/ | data/ 

| models/ a notebooks/ L_ requirements. txt 

# Punto de entrada principal (Streamlit) # Logica central del sistema 

# Procesamiento de video y YOLOv8 

# Calculo de métricas (distancias, Voronoi, etc.) # Calibracion de camara y homografia # Gestidén de persistencia local (SQLite) 

# Almacenamiento de videos y logs 

# Pesos del modelo YOLO (.pt) y configuraciones # Experimentos y pruebas de algoritmos # Dependencias del proyecto 

#### **4. Estrategia de Datos y Persistencia** 

Para abordar la problemática de la brecha competitiva y permitir el análisis posterior, es necesario un sistema de almacenamiento eficiente: 

- **Registro de Eventos** : Cada detección y métrica calculada debe guardarse con una marca de tiempo en una base de datos local (como SQLite). Esto permitirá reconstruir el partido más tarde sin necesidad de volver a procesar el video. 

- **Exportación de Reportes** : Al finalizar el encuentro, el sistema debe ser capaz de generar un resumen estadístico que pueda ser consumido por otras herramientas o visualizado directamente en la aplicación como un informe postpartido. 

### 7. Aclaraciones sobre los datos que mostrará el software 

Para extraer una ventaja competitiva real, especialmente en ligas donde la brecha de nivel es marcada, los datos deben transformarse en información visual que sea accionable. En el fútbol profesional, el análisis se divide en tres dimensiones: espacial (dónde ocurre), temporal (cuándo ocurre) y relacional (cómo interactúan los jugadores). 

A continuación, los gráficos y estadísticas más efectivos para un sistema de análisis táctico basado en visión artificial: 

#### **1. Visualizaciones espaciales y mapas de calor** 

Estas herramientas permiten ver patrones que el ojo humano ignora durante el frenesí del partido. 

- Mapas de Calor de Posicionamiento: Indican las zonas de mayor permanencia de los jugadores. Son vitales para detectar si un extremo está muy "pegado" a la banda o si los volantes centrales están dejando desprotegido el eje medio. 

- Mapas de Presión (Defensive Actions): Registran dónde se producen las recuperaciones de pelota o las faltas. Para un equipo que busca ascender, ver que su presión solo es efectiva en campo propio es un indicador de que el ritmo de la categoría superior lo está superando. 

- Diagramas de Voronoi: Dividen el campo en polígonos donde cada punto dentro de un polígono es el más cercano a un jugador específico. Es la mejor forma de visualizar el control del espacio. Si los polígonos del rival son más grandes en zonas críticas, el equipo está perdiendo la batalla táctica. 

#### **2. Estadística de estructura y compactación** 

Aquí es donde el procesamiento en laptop con YOLOv8 brilla, ya que permite calcular distancias exactas de forma constante. 

- Convex Hull (Polígono de Equipo): Se dibuja un polígono que encierra a todos los jugadores de campo. El área de este polígono mide la compactación. Un equipo que se "estira" (área muy grande) es vulnerable a pases filtrados. 

- Altura de la Línea Defensiva: Un gráfico de líneas temporales que muestra a cuántos metros del arco propio está el último defensor. Esto revela si el equipo retrocede por miedo ante la jerarquía del rival o si mantiene una postura valiente. 

-  Distancia entre Líneas: Gráficos que miden la separación entre la defensa y el mediocampo. En la Liga Rafaelina o de San Francisco, la pérdida de esta métrica suele ser la causa principal de las derrotas de equipos recién ascendidos. 

#### **3. Gráficos comparativos (Benchmarking de nivel)** 

Para romper la "burbuja de nivel", el software debe comparar el rendimiento actual contra un estándar deseado. 

- Gráficos de Radar (Spider Charts): Permiten comparar múltiples variables a la vez (ej. efectividad de pases, recuperaciones, tiros al arco, centros). Podés superponer el radar de tu equipo contra el radar promedio de los 3 mejores equipos de la categoría superior. 

- Gráficos de Barras de Transición: Miden cuánto tiempo tarda el equipo en pasar de fase defensiva a ataque (y viceversa). La diferencia de nivel entre categorías suele estar en la velocidad de estas transiciones, no solo en la técnica individual. 

#### **4. Análisis de redes de pases (Pass Networks)** 

Aunque la visión artificial tiene dificultades para detectar quién da el pase sin cámaras de altísima resolución, con YOLOv8 se puede estimar la estructura de soporte. 

- Nodos de Interacción: Círculos que representan a los jugadores; el tamaño del círculo es la cantidad de veces que participan, y las líneas entre ellos indican la frecuencia de asociación. Esto permite identificar al "motor" del equipo rival para anularlo o detectar si tu propio equipo está siendo demasiado dependiente de un solo jugador. 

#### **5. Estadísticas de flujo en tiempo real para Streamlit** 

Para la pantalla de "Modo Observador", lo ideal son indicadores de tendencia: 

- Índice de Dominio Territorial: Un medidor (tipo velocímetro) que indica qué porcentaje del campo rival está bajo control en los últimos 5 minutos. 

- Expected Threat (xT) simplificado: Basado en la posición de la pelota, el sistema puede asignar una probabilidad de peligro. Si la pelota entra en el "pasillo interior", el sistema lanza una alerta visual de alto riesgo. 

### Presentación Formal del Problema 

**<u>Problema 1:</u>** El Efecto Burbuja: En la Liga Regional de San Francisco, los clubes dominantes suelen ganar por "peso propio" (mejores jugadores o presupuesto). Esto oculta deficiencias tácticas que solo quedan expuestas cuando salen a competir a nivel federal o provincial. La falta de datos objetivos impide que estos clubes vean sus techos reales antes de que sea tarde. 

##### 1. Usuario: ¿A quién le pasa? 

- Clubes Dominantes: Instituciones de la Liga de San Francisco o la Liga Rafaelina que, por presupuesto o historia, suelen estar siempre en los primeros puestos. 

- Cuerpos Técnicos: Entrenadores y analistas que buscan profesionalizar su trabajo pero carecen de presupuesto para herramientas de élite. 

##### 2. Problema: ¿Qué pasa exactamente? 

Existe un techo táctico invisible generado por la superioridad individual. Al ganar partidos a nivel local basándose únicamente en la calidad de los jugadores, se genera una falsa sensación de eficiencia. 

Esto oculta fallas estructurales (mala compactación, lentitud en transiciones, desorden en retroceso) que no son castigadas por los rivales locales, pero que se vuelven letales frente a equipos de mayor jerarquía. No hay una vara de medir objetiva que compare el rendimiento local con el estándar de nivel federal. 

##### 3. Contexto: ¿Cuándo y dónde ocurre? 

- Dónde: Específicamente en el ámbito de las ligas regionales del interior y torneos de ascenso. 

   - Cuándo: * Durante el campeonato doméstico (donde se gesta la "burbuja"). 

      - En las fases de cruce de Torneos Provinciales o Federativos. 

      - En la temporada inmediata posterior a un ascenso (Efecto Ascensor). 

4. Impacto: ¿Qué se está perdiendo si no se resuelve? 

   - Desperdicio de Recursos: Clubes que invierten en jugadores para pelear un torneo y quedan eliminados por errores tácticos "evitables" si se hubieran medido antes. 

   - Estancamiento Deportivo: No poder superar una instancia de eliminación directa repetidamente destruye proyectos institucionales y desmotiva al cuerpo técnico y jugadores. 

   - Fuga de Talento: Jugadores que parecen "estrellas" en la burbuja local pero no logran adaptarse a un ritmo mayor por falta de formación táctica. 

**<u>Problema 2:</u>** La Inviabilidad del Ascenso (LRF): El caso de la Liga Rafaelina es un ejemplo clásico de falta de transición táctica. Un equipo de Primera B asciende con una estructura amateur y se encuentra con un ritmo de Primera A para el cual no tiene herramientas de análisis. El sistema permitiría que un equipo con menos recursos pueda compensar esa diferencia mediante una preparación táctica basada en datos, optimizando cada movimiento para maximizar sus chances de permanencia. 

   1. Usuario: ¿A quién le pasa? 

- Clubes de Primera B (LRF) recientemente ascendidos: Instituciones con presupuestos limitados que logran el mérito deportivo de subir de categoría pero carecen de la infraestructura de análisis necesaria para mantenerse. 

- Entrenadores de equipos "cenicienta": Directores técnicos que deben enfrentar a rivales con planteles mucho más caros y necesitan una ventaja estratégica para nivelar la cancha. 

   2. Problema: ¿Qué pasa exactamente? 

Se produce un choque de realidad táctica y física. Los equipos que ascienden suelen hacerlo con una estructura de trabajo puramente amateur o basada en el esfuerzo voluntario. Al llegar a la Primera A, se encuentran con un ritmo de juego, una velocidad de transición y una ocupación de espacios para la cual no tienen parámetros de medición. 

Sin herramientas de análisis, estos equipos no pueden identificar qué aspectos de su juego deben "profesionalizar" urgentemente (por ejemplo, reducir el tiempo de recuperación de tras pérdida o ajustar la basculación defensiva), lo que los lleva a perder partidos por detalles técnicos que la IA podría detectar. 

3. Contexto: ¿Cuándo y dónde ocurre? 

   - Dónde: En el ámbito de la Liga Rafaelina de Fútbol (LRF), particularmente en la transición entre la Primera B y la Primera A. 

   - Cuándo: Durante el primer torneo posterior al ascenso y en las semanas de preparación táctica previas a enfrentar a los equipos consolidados de la categoría superior. 

4. Impacto: ¿Qué se está perdiendo si no se resuelve? 

   - Estabilidad Institucional: El "efecto ascensor" genera un ciclo de frustración que vacía las canchas, aleja a los sponsors y desarticula los proyectos de divisiones inferiores. 

   - Competitividad de la Liga: Una liga donde los ascendidos bajan casi siempre se vuelve predecible y pierde interés general. 

   - Eficiencia de Recursos: Los clubes gastan sus pocos recursos en refuerzos "por nombre" en lugar de invertir en una estructura táctica basada en datos que optimice el plantel que ya tienen. 

**<u>Problema 3:</u>** Sesgo Cognitivo en Tiempo Real: Durante un partido, el entrenador está bajo estrés y puede perder de vista patrones tácticos (como un carrilero que no retrocede o un hueco constante en el mediocampo). El sistema actuaría como un "segundo par de ojos" objetivo. 

1. Usuario: ¿A quién le pasa? 

   - El Director Técnico (DT): La persona responsable de la toma de decisiones inmediata bajo condiciones de estrés extremo. 

   - El Ayudante de Campo / Analista de Banco: Quien debe asistir al DT con información relevante pero que a menudo sufre el mismo agotamiento cognitivo o "ceguera de taller" al estar inmerso en la misma dinámica emocional del partido. 

2. Problema: ¿Qué pasa exactamente? 

Se produce un fenómeno de "Túnel de Atención" o Saturación Cognitiva. El cerebro humano, ante situaciones de estrés y flujo constante de estímulos (el griterío de la hinchada, las protestas, la velocidad del juego), tiende a seguir casi exclusivamente la trayectoria del balón. 

Esto genera una incapacidad biológica para percibir patrones periféricos o fallas estructurales "sin pelota". Como resultado, el entrenador puede notar que su sistema defensivo se está descompensado por un carrilero que no llega a cubrir su zona o que el rival está acumulando gente en un pasillo específico de forma sistemática. La subjetividad del momento impide ver el "bosque" (la táctica) por mirar el "árbol" (la jugada puntual). 

##### 3. Contexto: ¿Cuándo y dónde ocurre? 

Dónde: En el área técnica y el banco de suplentes durante el transcurso de los partidos. 

Cuándo: Con mayor intensidad en momentos críticos del encuentro: los minutos finales de cada tiempo, situaciones de resultado adverso o inmediatamente después de un cambio táctico propio o del rival, donde el sistema está más inestable. 

##### 4. Impacto: ¿Qué se está perdiendo si no se resuelve? 

Capacidad de Reacción Proactiva: El DT realiza correcciones "ex-post" (después de que el error costó un gol o una situación clara) en lugar de actuar sobre la tendencia detectada. 

Precisión en los Cambios: Se realizan sustituciones basadas en el cansancio visible o en la intuición, perdiendo la oportunidad de hacer cambios tácticos basados en métricas de ocupación de espacios que realmente neutralicen al rival. 

Efectividad Táctica: Un plan de juego bien diseñado durante la semana se desmorona en minutos porque el entrenador no tiene los medios para verificar si sus jugadores están cumpliendo con las distancias y roles asignados bajo la fatiga del partido. 

**<u>Problema 4:</u>** Inoperancia del Análisis Post-Partido: En ligas como la de San Francisco o la Rafaelina, el análisis posterior suele ser inexistente o puramente basado en recuerdos, perdiendo la oportunidad de corregir movimientos tácticos específicos con evidencia visual. 

##### 1. Usuario: ¿A quién le pasa? 

- El Cuerpo Técnico (DT y analistas): Quienes deben planificar la semana de entrenamiento basándose en lo que sucedió el domingo, pero carecen de registros fiables. 

- El Jugador: El receptor del feedback, que a menudo tiene una percepción de su propio rendimiento diferente a la realidad y necesita "verse" para corregir hábitos. 

- Coordinadores de Divisiones Inferiores: Que necesitan evaluar si se están respetando los procesos de formación táctica en las categorías formativas. 

##### 2. Problema: ¿Qué pasa exactamente? 

Se produce una "Desconexión entre Percepción y Realidad". En el fútbol regional, el análisis post-partido suele reducirse a una charla basada en la memoria selectiva de los protagonistas, la cual está fuertemente sesgada por el resultado final (si se ganó, todo fue bueno; si se perdió, todo fue malo). 

Al no existir un registro objetivo con datos procesados, las correcciones son abstractas y genéricas ("hay que marcar más cerca", "nos faltó intensidad"). Se pierde la capacidad de señalar el segundo exacto y la coordenada precisa donde un movimiento táctico falló, transformando la enseñanza en un debate de opiniones en lugar de una sesión de corrección técnica basada en hechos. 

##### 3. Contexto: ¿Cuándo y dónde ocurre? 

   - Dónde: En los vestuarios, salas de video improvisadas o directamente en el campo de entrenamiento durante los primeros días de la semana (lunes o martes). 

   - Cuándo: En la fase de "debriefing" post-competencia, donde el nivel de adrenalina ha bajado y el jugador está más receptivo al aprendizaje táctico. 

4. Impacto: ¿Qué se está perdiendo si no se resuelve? 

   - Crecimiento Individual y Colectivo Lento: Los jugadores repiten los mismos errores tácticos jornada tras jornada porque no hay un soporte visual que les permita internalizar el concepto correcto. 

   - Pérdida de autoridad técnica: La crítica del entrenador puede ser percibida como "subjetiva" o "persecución personal" por el jugador. La evidencia visual de la IA elimina la discusión y profesionaliza la relación DT-Jugador. 

   - Inexistencia de una Base de Datos Histórica: El club no guarda registro de su evolución. Si el DT se va, se lleva toda la "información" con él, obligando al club a empezar de cero constantemente. 
