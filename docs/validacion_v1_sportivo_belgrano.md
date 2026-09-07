# Registro de validación V1 — Sportivo Belgrano

**Fecha:** 3 de septiembre de 2026
**Formato:** presencial, demo en vivo sobre laptop propia
**Checkpoint:** V1 (adelantado respecto al cronograma original de fin de Sprint 3)

---

## Resultado general

Reunión muy positiva. Alto interés del club, con voluntad explícita de colaborar en el
desarrollo. Las preguntas fueron sustantivas y orientadas al uso real, no de cortesía —
indicador de que evaluaron el sistema como algo que podrían adoptar, no solo como
demostración académica.

---

## Preguntas del club (y qué revelan)

| Pregunta | Qué revela | Estado en el proyecto |
|---|---|---|
| ¿Esto elimina la tarea manual de taguear? | Confirma que el tagueo manual es un dolor real, tal como se detectó en la validación de problema | ✅ Sí, el tagueo one-click reduce el tiempo drásticamente (aunque no lo elimina del todo) |
| ¿Puede llegar a ser tagueo 100% automático, sin botonera? | Expectativa alta sobre automatización; quieren llegar más lejos que el MVP planeado | 🔜 Fuera del alcance actual — requiere detección automática de eventos (posesión, presión, transición) a partir de las posiciones. Técnicamente posible como evolución |
| ¿Cómo hacemos de visitante? | Preocupación logística concreta: no controlan la cancha ni el lugar de filmación en partidos fuera de casa | ⚠️ No resuelto — depende de conseguir un punto elevado en cada estadio visitante |
| ¿Podemos usar el video de la transmisión de YouTube del partido? | Buscan alternativa a filmar ellos mismos | ⚠️ Limitado — las transmisiones panean y cortan de plano, lo que rompe el tracking y la homografía (validado empíricamente: 1.828 IDs fragmentados vs. 68 con cámara estable) |
| ¿Se pueden personalizar las métricas? | Cada DT tiene su propio modelo de juego y quiere medir lo suyo | 🔜 No implementado, pero arquitectónicamente viable — las métricas se calculan sobre las coordenadas en metros, se pueden agregar nuevas |
| ¿Qué necesitamos para análisis en vivo? | Interés en tiempo real, no solo post-partido | ⚠️ Fuera del alcance reducido actual (se acotó a batch por recomendación de cátedra). El diseño original contemplaba esta opción |
| ¿Podría reconocer patrones de juego? (central que no achica, lateral que no vuelve, extremo que no ayuda) | **La pregunta más valiosa.** Es exactamente el salto de "datos" a "análisis táctico" que le daría valor diferencial al producto | 🔜 No implementado. Requiere lógica de reglas sobre las trayectorias por jugador. Es la evolución natural del sistema |

---

## Ofrecimientos del club

- **Videos de partidos** (entrenamientos y partidos de liga)
- **Permiso para filmar** en el estadio y en el campo de entrenamiento
- **Cámaras Vevo** disponibles para usar

### Por qué esto resuelve el mayor bloqueante del proyecto

Hasta esta reunión, el material de prueba dependía de videos de YouTube con cámaras que
panean, lo que degradaba severamente el tracking y la homografía. Con acceso a filmación
propia, se puede controlar la variable crítica: **cámara fija, elevada, lateral, sin
operador siguiendo la jugada**.

---

## Acciones derivadas (candidatas a tarjetas del tablero)

### Prioridad alta (habilitan todo lo demás)
1. **Armar guía de filmación** para pasarle al club: posición de cámara, altura, encuadre, duración, formato de archivo.
2. **Coordinar primera filmación** de un entrenamiento o partido con las condiciones correctas.
3. **Validar el pipeline completo** sobre ese primer video propio (reemplaza los clips de YouTube como material de referencia).

### Prioridad media (responden a lo que pidieron)
4. **Evaluar métricas configurables** — al menos permitir elegir qué métricas se muestran, aunque el cálculo esté fijo.
5. **Documentar la limitación de video de transmisión** con los datos empíricos ya obtenidos, para poder explicarles el "por qué no" con evidencia.

### Backlog futuro (fuera del MVP, pero registrado)
6. Tagueo automático de eventos a partir de posiciones.
7. Reconocimiento de patrones tácticos por jugador (el central que no achica, etc.).
8. Análisis en vivo (estaba en el diseño original, se descartó al acotar alcance).
9. Solución para partidos de visitante.

---

## Nota para el informe

Esta sesión funciona como **primera validación con usuario real** según el plan de testing.
Se adelantó al cronograma previsto (estaba planificada para fin de Sprint 3) por interés
espontáneo del club, lo cual es en sí mismo un indicador de validación de la propuesta de valor.
