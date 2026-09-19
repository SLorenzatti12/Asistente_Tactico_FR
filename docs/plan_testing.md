# Plan de Testing — Analizador Táctico

## Objetivo

Asegurar que cada tarjeta del tablero cumple criterios técnicos mínimos antes de darse
por terminada, y que el sistema en su conjunto se valida con usuarios reales (DTs,
ayudantes de campo) de forma periódica — no solo al final del proyecto.

Este plan tiene **dos niveles**, que se usan juntos pero responden preguntas distintas:

| Nivel | Pregunta que responde | Frecuencia |
|---|---|---|
| **A. Testing por tarjeta** | ¿Esta funcionalidad puntual funciona como se espera? | Cada tarjeta, antes de moverla a "Hecho" |
| **B. Validación con usuario real** | ¿Esto le sirve de verdad a un DT en la práctica? | Cada 2 sprints |

---

## A. Testing por tarjeta

Cada tarjeta del tablero (Trello/Notion/lo que usen) debe tener, antes de cerrarse,
una sección de **Criterios de Aceptación** con este formato:

```
### Criterios de Aceptación
- [ ] Funcional: ¿qué tiene que pasar cuando se usa correctamente?
- [ ] Casos borde: ¿qué pasa con datos vacíos, video corto, sin conexión, etc.?
- [ ] Integración: ¿sigue funcionando el resto del pipeline después de este cambio?
- [ ] Evidencia: captura de pantalla, log de consola, o video corto del resultado
```

### Tipos de prueba según el tipo de tarjeta

| Tipo de tarjeta | Cómo se prueba |
|---|---|
| Módulo de detección/tracking (`run_inference.py`) | Correr sobre 2 videos distintos, confirmar rango razonable de IDs y detecciones por clase esperadas |
| Homografía (`calibrate.py`) | Confirmar % de detecciones fuera de cancha < 10%; revisar visualmente que los puntos calibrados caigan en el lugar correcto |
| Componente de dashboard (Streamlit) | Probar con datos reales (no solo placeholder), confirmar que no rompe si faltan columnas o el archivo no existe |
| Persistencia (SQLite) | Insertar un dato de prueba, cerrar y reabrir la app, confirmar que persiste |
| Fix de bug | Reproducir el bug original antes del fix (para confirmar que existía) y después (para confirmar que se resolvió) |

### Ejemplo aplicado — Tarjeta "Mapa 2D con Plotly" (Nico)

```
### Criterios de Aceptación
- [x] Funcional: al mover el slider de tiempo, las posiciones de los jugadores
      en el mapa cambian acorde al frame correspondiente
- [x] Casos borde: si el .parquet no tiene detecciones para un frame puntual,
      el mapa se muestra vacío sin romper la app
- [x] Integración: probado con partido_clip.mp4 Y partido_clip2.mp4 (no solo
      el primer clip usado para desarrollar)
- [x] Evidencia: captura adjunta del mapa con jugadores/árbitro/arquero
      distinguidos por color
```

---

## B. Validación con usuario real (cada 2 sprints)

### Cronograma propuesto

| Checkpoint | Cuándo | Qué se muestra | Con quién |
|---|---|---|---|
| **V1** | Fin de Sprint 3 (dashboard funcional básico) | Video anotado + mapa 2D + métricas de bloque | 1 DT (ej. de Sportivo o Rivadavia) |
| **V2** | Fin de Sprint 5 (tagueo + semáforo completos) | Flujo completo: cargar partido → taguear jugadas → calificar jugadores | 1-2 DTs, idealmente distintos a V1 |
| **V3** | Sprint 6 (demo final) | Sistema completo, con un partido real de la liga si ya está disponible | 2-3 DTs / referentes de la liga |

### Guion para cada sesión de validación (30-40 min)

1. **No explicar nada al principio.** Dejar que el DT abra la app solo y trate de usarla — anotar dónde se traba o duda, sin ayudarlo salvo que quede completamente bloqueado. Esto revela problemas de usabilidad reales que el equipo, por estar tan metido en el código, ya no ve.

2. **Tareas concretas a pedirle** (no preguntas abiertas tipo "¿qué te parece?"):
   - "Encontrá el momento donde el bloque defensivo está más abierto"
   - "Tagueá una jugada de presión"
   - "Calificá a 3 jugadores en el semáforo"

3. **Al final, sí preguntar abierto:**
   - ¿Esto reemplazaría algo que hacés hoy a mano? ¿Qué?
   - ¿Qué le falta para que lo usarías en un partido real de la semana que viene?
   - ¿Qué mostrarías primero si tuvieras 10 segundos con otro DT?

4. **Registrar todo** en una plantilla simple (ver abajo), no solo memoria.

### Plantilla de registro de sesión

```
Fecha: ___________
DT / rol: ___________
Checkpoint: V1 / V2 / V3

Tareas completadas sin ayuda: ___/3
Puntos de fricción observados:
  1.
  2.
  3.

Cita textual más útil:
"..."

Cambios a priorizar en el próximo sprint (máx. 3):
  1.
  2.
  3.
```

### Qué hacer con el feedback

- Los "puntos de fricción" se convierten en tarjetas nuevas del tablero, con prioridad alta si bloquearon una tarea completa.
- No todo el feedback se implementa — algunas cosas quedan fuera de alcance del MVP. Documentar por qué se descarta algo también es parte del proceso (útil para el informe final).

---

## Resumen para pegar en el tablero

> **Antes de mover una tarjeta a "Hecho":** completar los 4 checkboxes de Criterios
> de Aceptación (funcional, casos borde, integración, evidencia).
>
> **Cada 2 sprints:** sesión de 30-40 min con un DT real, siguiendo el guion de
> este documento. El feedback genera tarjetas nuevas para el sprint siguiente.
