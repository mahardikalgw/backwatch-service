"""Configuration for the backup agent, loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """Runtime configuration for the backup agent.

    Attributes:
        application: Application slug reported to the API.
        db_type: Database type (``postgresql``/``mysql``).
        db_host: Database host.
        db_port: Database port.
        db_name: Database name to dump.
        db_user: Database user.
        db_password: Database password.
        storage_driver: Storage driver name (``local`` or ``s3``).
        storage_base_dir: Local base directory for the local driver.
        storage_bucket: Bucket/path prefix for stored files.
        storage_endpoint: Optional S3 endpoint URL (MinIO/S3-compatible).
        storage_access_key: S3 access key.
        storage_secret_key: S3 secret key.
        storage_region: S3 region (default ``us-east-1``).
        api_url: Base URL of the Backup API.
        api_key: Per-application API key.
        retention_days: How many days of backups to retain.
        temp_dir: Directory for temporary dump files.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    application: str = "talenta"
    database_type: str = "postgresql"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "talenta"
    db_user: str = "talenta"
    db_password: str = "change-me"

    storage_driver: str = "local"
    storage_base_dir: str = "./backups"
    storage_bucket: str = "database-backups"
    storage_endpoint: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_region: str = "us-east-1"

    api_url: str = "http://localhost:8000"
    api_key: str = "change-me"

    retention_days: int = 30
    temp_dir: str = "./tmp"

    @property
    def dump_command_name(self) -> str:
        """Return the dump binary for the configured database type.

        Returns:
            ``pg_dump`` for PostgreSQL, ``mysqldump`` for MySQL.
        """
        return "mysqldump" if self.database_type == "mysql" else "pg_dump"


@lru_cache
def get_config() -> AgentConfig:
    """Return the cached agent configuration.

    Returns:
        The single shared AgentConfig instance.
    """
    return AgentConfig()
