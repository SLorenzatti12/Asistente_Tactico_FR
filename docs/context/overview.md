# Overview del proyecto

**Asistente Táctico IA** — MVP de análisis táctico automatizado para clubes de fútbol regional (Liga de San Francisco), pensado para procesamiento post-partido (offline, en diferido).

## Problema que resuelve

Los clubes regionales filman sus partidos con dos cámaras fijas de fondo (Norte y Sur), en perspectiva diagonal. El sistema:
1. Detecta y sigue a los jugadores en video.
2. Unifica las dos perspectivas en un único plano métrico 2D (origen en el centro de la cancha) mediante doble homografía.
3. Calcula métricas tácticas cuantitativas (compacidad del bloque) sobre ese plano.
4. Permite etiquetar eventos clave (salidas, presión, pelota parada) y exportar clips de 10 s con un click.

Todo debe funcionar **100% offline**, porque los estadios regionales no garantizan conectividad.

## Equipo (Lorenzatti - Tribolo - Pesce)

- **Santiago Lorenzatti** — Product Manager & UX
- **Lucia Pesce** — Lead AI & Computer Vision Engineer
- **Nicolas Tribolo** — Full-Stack Architect & Integrator

## Estado actual

- V1 demostrado en vivo al club **Sportivo Belgrano** (ver `docs/validacion_v1_sportivo_belgrano.md`) — feedback y backlog priorizado ya recogidos.
- Pipeline de detección/tracking validado de punta a punta sobre clip real (ver `docs/context/decisiones.md` y `docs/bitacora_2026-08-17.md`).
- Mapa 2D (Plotly) + panel de métricas tácticas verificado (ver `docs/map_view_ejecucion_2026-08-24.md`).

Para el detalle día a día del trabajo, ver las bitácoras en `docs/` (son historial, no se resumen acá).
