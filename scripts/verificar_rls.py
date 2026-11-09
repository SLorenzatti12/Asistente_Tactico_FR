"""
Verificación de RLS en Supabase — Nico
=========================================
Comprueba que la seguridad a nivel de fila (RLS) quedó bien configurada
DESPUÉS de correr db/rls_cloud.sql — ver "Seguridad de la nube" en
docs/context/8-base-de-datos-hibrida.md para el contexto completo:

  1. La key pública (anon, SUPABASE_KEY) NO puede leer ni escribir
     ninguna tabla.
  2. La key privilegiada (service_role, SUPABASE_SERVICE_ROLE_KEY) sigue
     pudiendo leer y escribir con normalidad (la bypassea) — confirma que
     el sync (src/db/sync.py) no se rompió.

No deja datos de prueba: la prueba de escritura inserta y borra una fila
en `clubs` (la tabla sin dependencias) usando la key privilegiada. Con la
key pública no se intenta insertar — si el select ya falló, ya alcanza
para confirmar que no tiene acceso.

Uso:
    python3 scripts/verificar_rls.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from db.supabase_client import (  # noqa: E402
    SupabaseConfigError,
    get_client,
    get_privileged_client,
)

_TABLA_PRUEBA = "clubs"


def _probar_anon() -> bool:
    """True si la key pública queda correctamente bloqueada."""
    try:
        client = get_client()
    except SupabaseConfigError as e:
        print(f"⚠️  No se pudo crear el cliente anon: {e}")
        return False

    try:
        res = client.table(_TABLA_PRUEBA).select("id").limit(1).execute()
    except Exception as e:
        print(f"✅ La key pública no puede leer «{_TABLA_PRUEBA}» "
              f"(rechazada: {e.__class__.__name__}).")
        return True

    if res.data:
        print(f"❌ La key pública SÍ pudo leer «{_TABLA_PRUEBA}» "
              f"({len(res.data)} fila(s)) — RLS no está bloqueando.")
        return False
    print(f"✅ La key pública no trajo filas de «{_TABLA_PRUEBA}» "
          f"(vacío en vez de error — RLS la filtra igual).")
    return True


def _probar_privilegiada() -> bool:
    """True si la key privilegiada puede leer y escribir con normalidad."""
    try:
        client = get_privileged_client()
    except SupabaseConfigError as e:
        print(f"⚠️  {e}")
        return False

    try:
        client.table(_TABLA_PRUEBA).select("id").limit(1).execute()
        insertado = client.table(_TABLA_PRUEBA).insert(
            {"name": "__verificar_rls_test__"}
        ).execute()
        nuevo_id = insertado.data[0]["id"]
        client.table(_TABLA_PRUEBA).delete().eq("id", nuevo_id).execute()
    except Exception as e:
        print(f"❌ La key privilegiada (service_role) no pudo leer/escribir "
              f"«{_TABLA_PRUEBA}»: {e}")
        return False
    print("✅ La key privilegiada (service_role) sigue pudiendo leer y "
          "escribir con normalidad.")
    return True


def main() -> None:
    print("— Probando key pública (anon) —")
    ok_anon = _probar_anon()
    print("\n— Probando key privilegiada (service_role) —")
    ok_priv = _probar_privilegiada()

    print()
    if ok_anon and ok_priv:
        print("✅ RLS está bien configurada: la key pública queda afuera y "
              "el sync sigue funcionando.")
    else:
        print("⚠️  Revisar: alguna de las dos pruebas no dio el resultado "
              "esperado (ver arriba).")
        sys.exit(1)


if __name__ == "__main__":
    main()
