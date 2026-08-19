"""Run ``pg_dump`` / ``mysqldump`` and compress the result (PRD sections 5.1, 6)."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from agent.config import AgentConfig
from agent.logger import get_logger


@dataclass
class DumpResult:
    """Outcome of a database dump.

    Attributes:
        local_path: Path to the compressed dump file.
        database_name: Name of the database dumped.
        error: Error message when the dump failed, else None.
        commands: The subprocess commands that were attempted.
    """

    local_path: str | None = None
    database_name: str | None = None
    error: str | None = None
    commands: list[str] = field(default_factory=list)


class DatabaseDumper:
    """Execute a database dump using the CLI tooling for the configured DB.

    Args:
        config: Agent configuration.
    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._logger = get_logger("backup-agent.database")

    def _build_command(self, dump_path: Path) -> list[str]:
        """Build the raw dump command for the configured database.

        Args:
            dump_path: Where the uncompressed dump will be written.

        Returns:
            The argv list (excluding any password via command line).
        """
        cfg = self._config
        if cfg.database_type == "mysql":
            return [
                "mysqldump",
                f"--host={cfg.db_host}",
                f"--port={cfg.db_port}",
                f"--user={cfg.db_user}",
                cfg.db_name,
            ]
        return [
            "pg_dump",
            f"--host={cfg.db_host}",
            f"--port={cfg.db_port}",
            f"--username={cfg.db_user}",
            f"--dbname={cfg.db_name}",
            "--format=custom",
            "--no-owner",
            "--file",
            str(dump_path),
        ]

    def _environment(self) -> dict[str, str]:
        """Return an environment with the DB password injected.

        Returns:
            A copy of os.environ including the database password variable.
        """
        env = os.environ.copy()
        cfg = self._config
        if cfg.database_type == "mysql":
            env["MYSQL_PWD"] = cfg.db_password
        else:
            env["PGPASSWORD"] = cfg.db_password
        return env

    def dump(self, started_at: datetime) -> DumpResult:
        """Run the dump and compress it to ``.gz``.

        Args:
            started_at: Timestamp used to namespace the output filename.

        Returns:
            A DumpResult with the compressed file path or an error.
        """
        cfg = self._config
        temp_dir = Path(cfg.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        timestamp = started_at.strftime("%Y%m%d_%H%M%S")
        raw_path = temp_dir / f"{cfg.db_name}_{timestamp}.dump"
        gz_path = temp_dir / f"{cfg.db_name}_{timestamp}.dump.gz"

        command = self._build_command(raw_path)
        self._logger.info("database dump started", command=" ".join(command))
        try:
            env = self._environment()
            if cfg.database_type == "mysql":
                with open(raw_path, "wb") as output:
                    process = subprocess.run(command, env=env, stdout=output, stderr=subprocess.PIPE)
            else:
                process = subprocess.run(
                    command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
        except FileNotFoundError as exc:
            error = f"{cfg.dump_command_name} not found on PATH"
            self._logger.error("database dump failed", error=error)
            return DumpResult(database_name=cfg.db_name, error=error, commands=command)

        if process.returncode != 0:
            message = process.stderr.decode(errors="replace").strip() or "unknown error"
            error = f"{cfg.dump_command_name} exited with code {process.returncode}: {message}"
            self._logger.error("database dump failed", error=error)
            return DumpResult(database_name=cfg.db_name, error=error, commands=command)

        if not raw_path.exists() or raw_path.stat().st_size == 0:
            error = "dump produced an empty file"
            self._logger.error("database dump failed", error=error)
            return DumpResult(database_name=cfg.db_name, error=error, commands=command)

        self._logger.info("database dump completed", duration="compressing")
        with open(raw_path, "rb") as source, gzip.open(gz_path, "wb") as target:
            shutil.copyfileobj(source, target)
        raw_path.unlink(missing_ok=True)
        return DumpResult(local_path=str(gz_path), database_name=cfg.db_name)