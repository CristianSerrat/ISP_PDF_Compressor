"""Registro estructurado de uso en SQLite con modo WAL y estricta privacidad."""

import asyncio
import csv
import io
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from app.config import settings


class UsageRepository:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (settings.DATA_DIR / "usage.db")
        self._initialized = False

    def get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexión con soporte de filas como diccionario y WAL habilitado."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_db(self) -> None:
        """Crea la tabla de registro de uso e índices si no existen."""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    params TEXT NOT NULL,
                    pages INTEGER NOT NULL DEFAULT 0,
                    original_size INTEGER NOT NULL DEFAULT 0,
                    final_size INTEGER NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    client_id TEXT NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_logs(timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_operation ON usage_logs(operation);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_status ON usage_logs(status);")
            conn.commit()
        self._initialized = True

    def _log_operation_sync(
        self,
        operation: str,
        params: dict[str, Any],
        pages: int,
        original_size: int,
        final_size: int,
        duration_ms: int,
        status: str,
        error_code: str | None,
        client_id: str,
    ) -> None:
        """Inserción síncrona en base de datos. NUNCA incluye nombres de archivos ni rutas."""
        # Limpiar parámetros de cualquier potencial dato sensible
        safe_params = {
            k: v for k, v in params.items()
            if k not in {"filename", "file_path", "name", "path", "password"}
        }
        params_json = json.dumps(safe_params, ensure_ascii=False)
        now_utc = datetime.now(timezone.utc).isoformat()

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO usage_logs (
                    timestamp, operation, params, pages,
                    original_size, final_size, duration_ms,
                    status, error_code, client_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_utc,
                    operation,
                    params_json,
                    max(0, pages),
                    max(0, original_size),
                    max(0, final_size),
                    max(0, duration_ms),
                    status,
                    error_code,
                    client_id,
                ),
            )
            conn.commit()

    async def log_operation(
        self,
        operation: str,
        params: dict[str, Any],
        pages: int,
        original_size: int,
        final_size: int,
        duration_ms: int,
        status: str = "ok",
        error_code: str | None = None,
        client_id: str = "anon",
    ) -> None:
        """Registra una operación de forma asíncrona mediante un thread."""
        await asyncio.to_thread(
            self._log_operation_sync,
            operation=operation,
            params=params,
            pages=pages,
            original_size=original_size,
            final_size=final_size,
            duration_ms=duration_ms,
            status=status,
            error_code=error_code,
            client_id=client_id,
        )

    def _cleanup_retention_sync(self, retention_days: int) -> int:
        """Elimina registros que superen el periodo de retención."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM usage_logs WHERE timestamp < ?", (cutoff,))
            deleted = cur.rowcount
            conn.commit()
            return deleted

    async def cleanup_retention(self, retention_days: int | None = None) -> int:
        """Ejecuta la purga de retención de forma asíncrona."""
        days = retention_days if retention_days is not None else settings.LOG_RETENTION_DAYS
        return await asyncio.to_thread(self._cleanup_retention_sync, days)

    def _get_stats_sync(self, days: int = 30) -> dict[str, Any]:
        """Calcula métricas agregadas para el panel de administración."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        with self.get_connection() as conn:
            # 1. Resumen global
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total_ops,
                    SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) as ok_ops,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_ops,
                    SUM(original_size) as total_original_bytes,
                    SUM(final_size) as total_final_bytes,
                    AVG(duration_ms) as avg_duration_ms,
                    SUM(pages) as total_pages
                FROM usage_logs
                WHERE timestamp >= ?
                """,
                (cutoff,),
            ).fetchone()

            total_ops = row["total_ops"] or 0
            ok_ops = row["ok_ops"] or 0
            error_ops = row["error_ops"] or 0
            orig_bytes = row["total_original_bytes"] or 0
            final_bytes = row["total_final_bytes"] or 0
            saved_bytes = max(0, orig_bytes - final_bytes)
            saved_pct = (saved_bytes / orig_bytes * 100) if orig_bytes > 0 else 0.0

            # 2. Operaciones por día
            ops_by_day = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT substr(timestamp, 1, 10) as date, COUNT(*) as count,
                           SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) as ok,
                           SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors
                    FROM usage_logs
                    WHERE timestamp >= ?
                    GROUP BY substr(timestamp, 1, 10)
                    ORDER BY date ASC
                    """,
                    (cutoff,),
                ).fetchall()
            ]

            # 3. Operaciones por tipo
            ops_by_type = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT operation, COUNT(*) as count,
                           SUM(original_size) as original_bytes,
                           SUM(final_size) as final_bytes,
                           AVG(duration_ms) as avg_duration_ms
                    FROM usage_logs
                    WHERE timestamp >= ?
                    GROUP BY operation
                    ORDER BY count DESC
                    """,
                    (cutoff,),
                ).fetchall()
            ]

            # 4. Distribución por preset de compresión
            presets = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT json_extract(params, '$.preset') as preset, COUNT(*) as count
                    FROM usage_logs
                    WHERE timestamp >= ? AND operation = 'compress'
                    GROUP BY preset
                    ORDER BY count DESC
                    """,
                    (cutoff,),
                ).fetchall()
            ]

            # 5. Picos de uso por franja horaria (00-23 UTC)
            hourly = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT substr(timestamp, 12, 2) as hour, COUNT(*) as count
                    FROM usage_logs
                    WHERE timestamp >= ?
                    GROUP BY hour
                    ORDER BY hour ASC
                    """,
                    (cutoff,),
                ).fetchall()
            ]

            # 6. Clientes más activos (top 10 según identificador configurado)
            top_clients = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT client_id, COUNT(*) as count,
                           SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) as ok_count
                    FROM usage_logs
                    WHERE timestamp >= ?
                    GROUP BY client_id
                    ORDER BY count DESC
                    LIMIT 10
                    """,
                    (cutoff,),
                ).fetchall()
            ]

            # 7. Desglose de errores más comunes
            top_errors = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT error_code, COUNT(*) as count
                    FROM usage_logs
                    WHERE timestamp >= ? AND status = 'error'
                    GROUP BY error_code
                    ORDER BY count DESC
                    LIMIT 10
                    """,
                    (cutoff,),
                ).fetchall()
            ]

            return {
                "period_days": days,
                "total_operations": total_ops,
                "successful_operations": ok_ops,
                "error_operations": error_ops,
                "error_rate_pct": round((error_ops / total_ops * 100), 2) if total_ops > 0 else 0.0,
                "total_original_bytes": orig_bytes,
                "total_final_bytes": final_bytes,
                "saved_bytes": saved_bytes,
                "saved_pct": round(saved_pct, 2),
                "total_pages": row["total_pages"] or 0,
                "avg_duration_ms": round(row["avg_duration_ms"] or 0, 1),
                "by_day": ops_by_day,
                "by_type": ops_by_type,
                "by_preset": presets,
                "hourly": hourly,
                "top_clients": top_clients,
                "top_errors": top_errors,
            }

    async def get_stats(self, days: int = 30) -> dict[str, Any]:
        """Obtiene métricas de uso agregadas."""
        return await asyncio.to_thread(self._get_stats_sync, days)

    def _export_csv_sync(self, start_date: str | None = None, end_date: str | None = None) -> str:
        """Exporta registros de uso a formato CSV filtrables por fechas."""
        query = "SELECT timestamp, operation, params, pages, original_size, final_size, duration_ms, status, error_code, client_id FROM usage_logs WHERE 1=1"
        params_list = []

        if start_date:
            query += " AND timestamp >= ?"
            params_list.append(start_date)
        if end_date:
            query += " AND timestamp <= ?"
            params_list.append(end_date)

        query += " ORDER BY timestamp DESC"

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "timestamp",
            "operation",
            "params",
            "pages",
            "original_size_bytes",
            "final_size_bytes",
            "duration_ms",
            "status",
            "error_code",
            "client_id",
        ])

        with self.get_connection() as conn:
            for row in conn.execute(query, params_list):
                writer.writerow(list(row))

        return output.getvalue()

    async def export_csv(self, start_date: str | None = None, end_date: str | None = None) -> str:
        """Exporta registros de uso a CSV de forma asíncrona."""
        return await asyncio.to_thread(self._export_csv_sync, start_date, end_date)


usage_repo = UsageRepository()
