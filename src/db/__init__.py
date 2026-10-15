"""
Capa de base de datos híbrida — Asistente Táctico FR
======================================================
Nico — ver docs/context/8-base-de-datos-hibrida.md para el diseño completo.

`local.py`   — helpers sobre la SQLite existente (data/db/analizador.sqlite),
               sin tocar el esquema que ya usa app/components/tagging.py.
`supabase_client.py` — conexión a Supabase (Postgres en la nube).
`sync.py`    — empuja partidos de SQLite hacia Supabase (una sola dirección,
               manual, pensado para correr cuando hay conexión a internet).
"""
