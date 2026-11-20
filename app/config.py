"""Configuración centralizada de la aplicación mediante variables de entorno."""

import os
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Red y servidor
    PORT: int = Field(default=8000, description="Puerto del servidor HTTP")
    TRUST_PROXY: bool = Field(default=False, description="Confiar en X-Forwarded-For para IPs")

    # Rutas de almacenamiento
    DATA_DIR: Path = Field(default=Path("data"), description="Directorio persistente (bases de datos)")
    TMP_DIR: Path = Field(default=Path("tmp"), description="Directorio temporal para procesado")

    # Límites operativos
    MAX_FILE_MB: int = Field(default=100, description="Tamaño máximo en MB por archivo")
    MAX_FILES: int = Field(default=20, description="Número máximo de archivos por lote")
    TTL_MINUTES: int = Field(default=30, description="Tiempo de vida en minutos de archivos temporales")
    GS_TIMEOUT: int = Field(default=120, description="Timeout en segundos para Ghostscript")
    MAX_CONCURRENT_JOBS: int = Field(default=2, description="Límite de tareas simultáneas de procesado")

    # Registro y privacidad
    LOG_CLIENT_MODE: str = Field(default="hash", description="Modo de registro de IP: 'none', 'hash', 'ip'")
    LOG_RETENTION_DAYS: int = Field(default=365, description="Días de retención de registros de uso")
    LOG_LEVEL: str = Field(default="INFO", description="Nivel de logs técnicos a stdout")
    HASH_SALT: str = Field(default="pdf-secret-salt-2024", description="Sal para hashear IPs")

    # Seguridad / Control de Acceso
    ADMIN_PASSWORD: str = Field(
        default="admin1234",
        description="Clave maestra de acceso al panel /admin"
    )
    ADMIN_SESSION_HOURS: int = Field(
        default=8,
        description="Duración en horas de la sesión de administrador"
    )
    SECRET_KEY: str = Field(
        default="pdf-tools-session-secret-key-2024",
        description="Clave para firma criptográfica de cookies de sesión"
    )
    ADMIN_ALLOWED_NETWORKS: str = Field(
        default="",
        description="Redes CIDR opcionales para /admin (vacío para permitir cualquier IP con contraseña)"
    )

    # Módulos habilitados
    ENABLED_MODULES: str = Field(
        default="compress,watermark,merge,split,rotate,protect,strip_metadata,img2pdf",
        description="Lista de módulos activos separados por coma"
    )

    @field_validator("LOG_CLIENT_MODE")
    @classmethod
    def validate_log_client_mode(cls, v: str) -> str:
        valid = {"none", "hash", "ip"}
        mode = v.lower().strip()
        if mode not in valid:
            raise ValueError(f"LOG_CLIENT_MODE debe ser uno de: {valid}")
        return mode

    @property
    def admin_networks_list(self) -> list[str]:
        return [net.strip() for net in self.ADMIN_ALLOWED_NETWORKS.split(",") if net.strip()]

    @property
    def enabled_modules_set(self) -> set[str]:
        return {m.strip().lower() for m in self.ENABLED_MODULES.split(",") if m.strip()}

    def setup_directories(self) -> None:
        """Crea los directorios necesarios si no existen."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.TMP_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
