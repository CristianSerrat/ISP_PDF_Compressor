#!/bin/sh
set -e

# Asegurar permisos correctos sobre los volúmenes montados (data y tmp)
# Esto soluciona automáticamente cualquier problema de permisos con Docker en Linux/CasaOS
mkdir -p /app/data /app/tmp
chown -R appuser:appuser /app/data /app/tmp 2>/dev/null || true
chmod -R 775 /app/data /app/tmp 2>/dev/null || true

# Ejecutar el comando principal como el usuario seguro sin privilegios (appuser)
exec gosu appuser "$@"
