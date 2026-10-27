# Ficha de criterio — un patrón que el club quiere marcar

Para completar con el DT o el ayudante de campo, un patrón por ficha. No hace falta saber nada técnico: describilo como lo explicarías en la charla.

Con la ficha, el equipo de desarrollo contesta tres cosas:
- si se puede medir con lo que registra el sistema;
- con qué precisión;
- qué parte queda afuera.

**Lo que el sistema sabe y lo que no** (para no pedir algo imposible):

| Sabe | No sabe |
|---|---|
| Dónde está cada jugador en la cancha, en metros, varias veces por segundo | Quién tiene la pelota (no hay posesión confiable) |
| De qué equipo es cada uno (por el color de la camiseta) | Quién es cada jugador: ve "track 587", no "Riquelme" |
| En qué línea juega cada uno (defensa, medio, ataque) | La intención: si se abrió para recibir o porque se desordenó |
| Si el bloque del equipo avanza o repliega, y a qué velocidad | Lo que pasa fuera de cuadro o con la cámara movida |

---

## 1. Nombre

Cómo lo llaman en el vestuario.

> _Ej.: "El lateral que no vuelve"_

## 2. Qué tiene que pasar

En una o dos oraciones, con números si los tienen.

> _Ej.: Cuando el equipo repliega, el lateral queda más de 10 metros adelante de la línea de los centrales._

## 3. A quién le aplica

Línea (defensa, medio, ataque), zona (banda o centro) o "a todos".

> _Ej.: Defensores que juegan sobre la banda._

## 4. En qué momento del juego

Cuando el bloque **sube**, cuando **repliega**, en cualquier momento, o en pelota parada (hoy no se distingue pelota parada).

> _Ej.: Cuando el bloque repliega._

## 5. Cuánto tiene que repetirse para que importe

Cuántas veces, o qué parte del partido. Una sola vez, ¿alcanza?

> _Ej.: En al menos 3 repliegues del partido._

## 6. Cuándo NO es un problema

Las excepciones tácticas: desmarques, marcas personales, el plan del día…

> _Ej.: Si el equipo quedó con un hombre más arriba por una contra propia; si el plan del partido era que el lateral se quede arriba._

## 7. Un ejemplo real

Un partido y un minuto donde lo hayan visto, para comparar lo que marca el sistema con lo que ve el DT.

> _Ej.: Sportivo – Crecer, 1° tiempo, alrededor del minuto 21._

## 8. Para qué lo usarían

¿Corrección individual, charla grupal, cambio en el entrenamiento? Define cómo se muestra.

> _Ej.: Para mostrarle el clip al jugador el martes._

---

**Lo completa el equipo de desarrollo:**

| | |
|---|---|
| ¿Se puede medir? | Sí / En parte / No — por qué |
| Cómo se mediría | |
| Perillas que puede ajustar el club | |
| Qué queda afuera | |
| Patrón existente relacionado | `desconectado` / `no_achica` / `no_repliega` (sin implementar) / nuevo |

**Para ajustar un patrón que ya existe**, alcanza con el punto 6 (cuándo no es un problema) y con calificar los momentos en la vista Patrones: útil, correcto tácticamente o no se ve. La vista "Probar otros criterios" muestra qué cambiaría con otros umbrales antes de cambiar nada.
