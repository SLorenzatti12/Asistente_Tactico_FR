# Analizador Táctico — Mockup Visual de Alta Fidelidad

Prototipo exploratorio de diseño y experiencia de usuario (UX/UI) para el sistema de análisis táctico post-partido del fútbol amateur (Liga de San Francisco, Córdoba).

Este prototipo es **100% standalone** y no requiere compilación, servidores ni librerías externas. Funciona directamente abriéndolo con doble clic en cualquier navegador web moderno bajo el protocolo `file://`.

---

## Cómo abrirlo

- **En macOS:** Doble clic sobre `mockup/index.html` o desde la terminal:
  ```bash
  open mockup/index.html
  ```
- **En Windows:** Doble clic sobre `mockup/index.html` o `start mockup/index.html`.
- **En Linux:** `xdg-open mockup/index.html`.

---

## Vistas Disponibles en el Prototipo

1. **📹 Mesa Táctica (Pantalla Principal de Análisis):**
   - **Video Anotado en Perspectiva:** Simula la cámara fija panorámica con cajas delimitadoras de tracking (RF-DETR + ByteTrack), identificación de equipo y vectores de los jugadores.
   - **Cancha 2D Cenital (105 × 68 m):** Sincronizada a 60 fps, con envolventes convexas de los bloques de ambos equipos, centroides y líneas defensivas.
   - **Selector de Visor:** Alterna entre *Vista Dividida (Split)*, *Solo Cancha 2D (Modo Táctico)* y *Solo Video Anotado*.
   - **Métricas de Bloque en Vivo:** Amplitud, profundidad, superficie ocupada en m² y compacidad (stretch index) con barras de progreso y comparativa directa Local vs. Visitante.
   - **Tagueo One-Click:** Botones táctiles con colchón automático de -10 segundos (`Presión`, `Salida`, `Transición`, `Pelota Parada`, `Recuperación`, `Pérdida`), historial interactivo y marcas en el timeline.
   - **Transporte y Scrubber:** Reproducción fluida, paso cuadro a cuadro (±0.5s), velocidades (0.5x, 1x, 2x) y arrastre interactivo.

2. **🏃 Rendimiento Individual (Jugadores):**
   - Filtros inmediatos por equipo y línea de juego (Arquero, Defensa, Medio, Ataque).
   - Tabla analítica completa con ordenamiento interactivo por dorsal, minutos, distancia recorrida, velocidad máxima, velocidad promedio y volumen de sprints.
   - **Ficha Inspectora Táctica:** Al seleccionar cualquier jugador, muestra su centroide promedio sobre una mini cancha, su elipse de calor/dispersión espacial, el desglose físico por 4 rangos de velocidad (Caminata, Trote, Carrera, Sprint) y la observación cualitativa del DT.
   - Botón directo para saltar a las participaciones de ese jugador en la Mesa Táctica.

3. **⚠️ Patrones Tácticos Detectados:**
   - Alertas estructuradas por severidad (Alta, Media, En Observación) basadas en los algoritmos del sistema (`desconectado`, `no_achica`, `bloque_estirado`, `cobertura_lateral`).
   - Redacción con lenguaje de campo orientado al DT: señales de desajuste geométrico para contrastar en video, respetando el principio de que *posición no es intención*.
   - Botones *"▶ Ver jugada"* con timestamps exactos que saltan directamente al segundo en cuestión en la Mesa Táctica y destacan al jugador con un halo luminoso.

4. **🚦 Semáforo Post-Partido:**
   - Pizarra evaluativa para la noche del domingo posterior al partido.
   - Calificación ágil de los 11 titulares y suplentes en tres estados: 🟢 Destacado, 🟡 Regular, 🔴 Bajo.
   - Actualización dinámica del balance global del equipo y el desglose de rendimiento por líneas.
   - Campo para notas y tareas de la semana por jugador.
   - **Exportación para WhatsApp:** Genera un mensaje formateado con emojis, calificaciones y puntos prioritarios listo para copiar y enviar al cuerpo técnico.

---

## Atajos de Teclado (Visor Táctico)

| Tecla | Acción |
|---|---|
| `Espacio` | Reproducir / Pausar video y cancha |
| `←` / `→` | Retroceder / Avanzar 1 segundo |
| `Shift + ←` / `Shift + →` | Retroceder / Avanzar 5 segundos |
| `P` | Taguear *Presión Alta* (-10s) |
| `S` | Taguear *Salida de Fondo* (-10s) |
| `T` | Taguear *Transición Rápida* (-10s) |
| `B` | Taguear *Pelota Parada* (-10s) |
| `R` | Taguear *Recuperación* (-10s) |
| `X` | Taguear *Pérdida Crítica* (-10s) |
