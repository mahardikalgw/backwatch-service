"""Tests for the backup agent (storage, validator, engine)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.backup import BackupEngine
from agent.config import AgentConfig
from agent.storage import S3Storage, build_storage
from agent.validator import Validator


def _config(tmp_path: Path, **overrides: object) -> AgentConfig:
    values: dict[str, object] = {
        "application": "talenta",
        "database_type": "postgresql",
        "db_name": "talenta",
        "storage_driver": "local",
        "storage_base_dir": str(tmp_path / "store"),
        "storage_bucket": "database-backups",
        "temp_dir": str(tmp_path / "tmp"),
        "api_url": "http://test",
        "api_key": "key",
    }
    values.update(overrides)
    return AgentConfig(**values)


def test_local_storage_upload_and_exists(tmp_path: Path) -> None:
    """Local storage uploads a file and reports existence."""
    config = _config(tmp_path)
    storage = build_storage(config)

    source = tmp_path / "backup.gz"
    source.write_bytes(b"hello")

    checksum = storage.upload(str(source), "database-backups/talenta/2026/08/12/backup.gz")
    assert checksum.startswith("sha256:")
    assert (Path(config.storage_base_dir) / "database-backups/talenta/2026/08/12/backup.gz").is_file()
    assert storage.exists("database-backups/talenta/2026/08/12/backup.gz")


def test_validator_rejects_missing_file(tmp_path: Path) -> None:
    """The validator fails when the file does not exist."""
    config = _config(tmp_path)
    storage = build_storage(config)
    validator = Validator(storage)

    result = validator.validate_local(str(tmp_path / "nope.gz"))
    assert not result.valid
    assert result.error == "file not created"


def test_backup_engine_success_with_fakes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The engine reports success when dump and upload succeed."""
    config = _config(tmp_path)
    dumper = tmp_path / "store"
    dumper.mkdir(parents=True, exist_ok=True)

    class FakeDumper:
        def dump(self, started_at):
            path = tmp_path / "tmp" / "talenta.dump.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"dump")
            from agent.database import DumpResult

            return DumpResult(local_path=str(path), database_name="talenta")

    class FakeStorage:
        def __init__(self, base: Path) -> None:
            self._base = base

        def upload(self, local_path: str, remote_path: str) -> str:
            from agent.storage import BaseStorage

            dest = self._base / remote_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            Path(local_path).rename(dest)
            return BaseStorage.sha256(str(dest))

        def exists(self, remote_path: str) -> bool:
            return (self._base / remote_path).is_file()

        def sha256(self, path: str) -> str:
            from agent.storage import BaseStorage

            return BaseStorage.sha256(path)

    engine = BackupEngine(config, storage=FakeStorage(tmp_path / "store"))
    engine._dumper = FakeDumper()  # type: ignore[assignment]

    outcome = engine.run()
    assert outcome.status == "success"
    assert outcome.checksum is not None
    assert outcome.storage_path.startswith("database-backups/")


def test_backup_engine_failure_when_dump_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The engine reports failure when the dump produces no file."""
    config = _config(tmp_path)

    class FakeDumper:
        def dump(self, started_at):
            from agent.database import DumpResult

            return DumpResult(local_path=None, database_name="talenta", error="dump failed")

    storage = build_storage(config)
    engine = BackupEngine(config, storage=storage)
    engine._dumper = FakeDumper()  # type: ignore[assignment]

    outcome = engine.run()
    assert outcome.status == "failed"
    assert outcome.error == "dump failed"


def test_build_storage_unknown_driver(tmp_path: Path) -> None:
    """An unknown storage driver raises ValueError."""
    config = _config(tmp_path, storage_driver="minio")
    with pytest.raises(ValueError):
        build_storage(config)


def test_build_storage_s3_driver(tmp_path: Path) -> None:
    """The s3 driver builds an S3Storage instance."""
    config = _config(tmp_path, storage_driver="s3", storage_endpoint="http://minio:9000")
    storage = build_storage(config)
    assert isinstance(storage, S3Storage)


class FakeS3Client:
    """In-memory stand-in for a boto3 S3 client (no network)."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, bytes]] = {}

    def put_object(self, Bucket: str, Key: str, Body) -> dict[str, str]:
        self._store.setdefault(Bucket, {})[Key] = Body.read()
        return {"ETag": '"fake"', "ResponseMetadata": {"HTTPStatusCode": 200}}

    def head_object(self, Bucket: str, Key: str) -> dict[str, str]:
        if Key in self._store.get(Bucket, {}):
            return {"ContentLength": "42", "ResponseMetadata": {"HTTPStatusCode": 200}}
        from botocore.exceptions import ClientError

        raise ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}, "ResponseMetadata": {}},
            "HeadObject",
        )


def test_s3_storage_upload_and_exists(tmp_path: Path) -> None:
    """S3 storage uploads a file, verifies existence, and hashes it."""
    config = _config(tmp_path, storage_driver="s3", storage_endpoint="http://minio:9000")
    storage = S3Storage(config)
    storage._client = FakeS3Client()  # type: ignore[assignment]

    source = tmp_path / "backup.gz"
    source.write_bytes(b"s3payload")

    checksum = storage.upload(str(source), "talent/2026/08/12/backup.gz")
    assert checksum.startswith("sha256:")
    assert storage.exists("talent/2026/08/12/backup.gz")
    assert not storage.exists("talent/2026/08/12/missing.gz")
