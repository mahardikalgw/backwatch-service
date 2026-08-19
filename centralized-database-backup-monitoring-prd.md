# PRD — Centralized Database Backup & Monitoring System

**Status:** Draft  
**Version:** 1.0  
**Target:** Internal Infrastructure

## 1. Problem Statement

There are currently 5 applications, each of which requires a database backup.

The problems to be solved:

- Backups run separately on each server.
- Backup status is difficult to monitor centrally.
- If a backup fails, it is not always detected quickly.
- Backup logs are scattered across each server.
- There is no easily viewable backup history.
- It is difficult to know whether the last backup actually succeeded.
- It is difficult to know the size and duration of backups over time.
- There is no centralized mechanism to detect overdue backups.

The system will provide a single place to know:

> Have the databases of all applications been successfully backed up, and are those backups safe to use?

## 2. Goals

### Primary Goals

1. Run database backups automatically.
2. Support PostgreSQL and MySQL.
3. Store backup results in object storage such as rustfs.
4. Record every backup as a structured record.
5. Provide centralized monitoring for 5 applications.
6. Know the status: Success, Failed, Running, and Overdue.
7. Store backup history.
8. Provide health checks.
9. Provide monitoring metrics.
10. Make it easier to investigate when a backup fails.

### Secondary Goals

- Know the backup duration.
- Know the backup size.
- Know the storage used.
- Know the backup error.
- Know when the last backup succeeded.
- Know the backup failure frequency.

## 3. Non-Goals

For the MVP, the system will not handle:

- Full disaster recovery orchestration.
- Automatic server provisioning.
- Kubernetes.
- Multi-region replication.
- Database replication.
- Real-time database synchronization.
- Automated production restore without approval.
- User-facing backup management.
- Complex RBAC.

Restore remains supported as a manual operation for now.

## 4. High-Level Architecture

```text
                    ┌──────────────────┐
                    │    Application   │
                    │     Servers      │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
           Backup           Backup        Backup
           Agent            Agent         Agent
              │              │              │
              └──────────────┼──────────────┘
                             │
                         HTTPS/API
                             │
                             ▼
                  ┌────────────────────┐
                  │   Backup API       │
                  │      FastAPI       │
                  └─────────┬──────────┘
                            │
                    ┌───────┴────────┐
                    │                │
                    ▼                ▼
             PostgreSQL          rustfs
             Metadata            Backup Files
                    │
                    ▼
                Dashboard
                    │
                    ▼
              Monitoring / Ops
```

## 5. System Components

### 5.1 Backup Agent

The backup agent is a Python application that runs on each server.

```text
backup-agent/
├── main.py
├── backup.py
├── database.py
├── storage.py
├── validator.py
├── config.py
└── logger.py
```

Responsibilities:

- Run `pg_dump` / `mysqldump`.
- Compress the backup.
- Compute the checksum.
- Upload the backup.
- Send the backup result to the Backup API.
- Store local logs.
- Remove temporary files.
- Return the appropriate exit code.

## 6. Backup Flow

Normal flow:

```text
Scheduler
    ↓
Backup Agent
    ↓
Start backup
    ↓
Database dump
    ↓
Compression
    ↓
Checksum
    ↓
Upload to rustfs
    ↓
Verify upload
    ↓
Report result
    ↓
Backup API
    ↓
Store metadata
```

Example:

```text
PostgreSQL
    ↓
pg_dump
    ↓
talenta_2026-08-12_000000.sql.gz
    ↓
SHA256
    ↓
rustfs
    ↓
POST /api/v1/backups
```

## 7. Backup Record

Every backup must produce a structured record.

```json
{
  "application": "talenta",
  "database_type": "postgresql",
  "database_name": "talenta",
  "status": "success",
  "started_at": "2026-08-12T00:00:00Z",
  "finished_at": "2026-08-12T00:03:12Z",
  "duration_seconds": 192,
  "size_bytes": 2483920128,
  "storage": "rustfs",
  "storage_path": "talenta/2026/08/12/backup.sql.gz",
  "checksum": "sha256:...",
  "error": null
}
```

## 8. Backup Status

### `RUNNING`

The backup is currently in progress.

### `SUCCESS`

The backup completed and the upload succeeded.

### `FAILED`

The backup failed, for example:

- `pg_dump` failed.
- Upload failed.
- Checksum failed.
- Storage is not available.

### `OVERDUE`

A backup has not been successfully performed past the defined schedule.

Example:

```text
Expected: every 24 hours

Last successful backup:
36 hours ago

Status:
OVERDUE
```

## 9. Backup Schedule

Each application can have a different schedule.

| Application | Frequency |
|---|---|
| Talenta | Daily |
| Simaira | Daily |
| Cakra | Daily |
| Liyatra | Daily |
| App E | Daily |

The MVP can use systemd timers or cron for scheduling.

Example:

```text
00:00 → Talenta
01:00 → Simaira
02:00 → Cakra
03:00 → Liyatra
04:00 → App E
```

The schedule can be changed without modifying the backup engine code.

## 10. Backup API

The central API uses FastAPI.

### MVP Endpoints

```http
GET /health
```

Service health check.

```http
POST /api/v1/backups
```

Accepts backup results from the agent.

```http
GET /api/v1/backups
```

Retrieves backup history.

Filters:

- application
- status
- date
- database_type

```http
GET /api/v1/backups/{id}
```

Details of a single backup.

```http
GET /api/v1/applications
```

Lists registered applications.

```http
GET /api/v1/applications/{id}/backup-status
```

Last backup status of an application.

```http
GET /api/v1/health/backups
```

Health status of all backups.

Example:

```json
{
  "status": "degraded",
  "total": 5,
  "healthy": 4,
  "failed": 1,
  "overdue": 0
}
```

## 11. Database Schema

### applications

```text
id
name
environment
database_type
schedule
is_active
created_at
updated_at
```

### backup_runs

```text
id
application_id
status
started_at
finished_at
duration_seconds
size_bytes
storage_provider
storage_path
checksum
error_message
created_at
```

### Optional: backup_events

To store detailed events:

```text
id
backup_run_id
event
message
timestamp
```

Example events:

```text
STARTED
DUMP_COMPLETED
COMPRESSED
UPLOADING
UPLOAD_COMPLETED
VERIFIED
COMPLETED
```

## 12. Storage

Backup files are not stored in the database.

Use:

```text
rustfs
```

Structure:

```text
bucket: database-backups

talenta/
├── 2026/
│   └── 08/
│       └── 12/
│           └── talenta_20260812_000000.sql.gz

simaira/
├── 2026/
│   └── 08/
│       └── 12/
│           └── simaira_20260812_000000.sql.gz
```

The database only stores metadata.

## 13. Retention

Backups have a retention policy.

MVP example:

```text
Daily backup
Retention: 30 days
```

Older backups will be deleted automatically.

Retention should be handled by the backup system, not solely by relying on object storage.

## 14. Verification

A completed backup is not automatically considered valid.

Minimum MVP:

```text
pg_dump
   ↓
file created
   ↓
file size > 0
   ↓
checksum
   ↓
upload
   ↓
verify object exists
   ↓
SUCCESS
```

For the next phase:

```text
Backup
   ↓
Temporary database
   ↓
Restore
   ↓
Run validation
   ↓
SUCCESS
```

This will become restore verification.

## 15. Logging

The backup agent produces structured logs.

Example:

```text
INFO  backup started
INFO  database dump started
INFO  database dump completed duration=82s
INFO  compression completed size=850MB
INFO  upload started
INFO  upload completed
INFO  checksum verified
INFO  backup completed
```

On failure:

```text
ERROR backup failed
ERROR pg_dump exited with code 1
```

Local logs are useful for debugging.

Meanwhile, `backup_runs` is used for monitoring.

## 16. Monitoring

The Backup API provides metrics for Prometheus.

Example metrics:

```text
backup_last_success_timestamp
backup_last_failure_timestamp
backup_duration_seconds
backup_size_bytes
backup_failure_total
backup_success_total
backup_overdue
```

Example:

```text
backup_overdue{application="talenta"} 0
backup_overdue{application="simaira"} 0
backup_overdue{application="cakra"} 1
```

Grafana can then be used for monitoring.

## 17. Dashboard

MVP Dashboard:

```text
DATABASE BACKUP MONITORING

┌─────────────────────────────────────────────┐
│ Total Applications              5           │
│ Healthy                         4           │
│ Failed                          1           │
│ Overdue                         0           │
└─────────────────────────────────────────────┘

Application     Last Backup     Status
─────────────────────────────────────────────
Talenta         12 min ago      SUCCESS
Simaira         18 min ago      SUCCESS
Cakra           2 hours ago     FAILED
Liyatra         14 min ago      SUCCESS
App E           20 min ago      SUCCESS
```

Application details:

```text
Talenta
─────────────────────────────

Last Backup
12 Aug 2026 00:03

Status
SUCCESS

Duration
3m 12s

Size
2.4 GB

Recent Backups
─────────────────────────────
12 Aug   SUCCESS   2.4 GB
11 Aug   SUCCESS   2.3 GB
10 Aug   SUCCESS   2.3 GB
09 Aug   FAILED
08 Aug   SUCCESS   2.2 GB
```

## 18. Alerting

The system must be able to send alerts when:

- A backup fails.
- A backup is overdue.
- Storage is not available.
- Backup size is abnormal.
- Backup duration is abnormal.

Example:

```text
BACKUP FAILED

Application: Cakra
Database: PostgreSQL
Time: 12 Aug 2026 02:04
Error: pg_dump exited with code 1
```

For the MVP, notifications can use:

- Telegram
- Discord
- Email

## 19. Security

The backup system holds database credentials, so security is a priority.

### Database credentials

Do not hardcode credentials.

Use:

- Environment variables.
- Secret manager.
- Podman secrets.

### API authentication

The backup agent must be authenticated when sending:

```http
POST /api/v1/backups
```

The MVP can use API Keys.

Each application has a different key.

```text
talenta → key A
simaira → key B
cakra   → key C
```

If one credential leaks, the credentials of other applications are not affected.

## 20. Reliability Requirements

### Backup Success Rate

Target:

```text
≥ 99%
```

### Detection

A backup failure must be detected within at most:

```text
≤ 15 minutes
```

### No Silent Failure

Every scheduled backup must result in one of:

```text
SUCCESS
FAILED
OVERDUE
```

It must never be just:

```text
nothing happened
```

## 21. MVP Scope

### Backup Agent

- [ ] PostgreSQL backup
- [ ] MySQL backup
- [ ] Compression
- [ ] Checksum
- [ ] rustfs upload
- [ ] Structured logging
- [ ] Backup result reporting
- [ ] Retention

### Backup API

- [ ] FastAPI
- [ ] Authentication
- [ ] Applications
- [ ] Backup runs
- [ ] Health endpoint
- [ ] Backup health endpoint

### Database

- [ ] Applications
- [ ] Backup runs

### Monitoring

- [ ] Prometheus metrics
- [ ] Grafana dashboard
- [ ] Failed backup alert
- [ ] Overdue alert

## 22. Phase 2

After the MVP is stable:

- [ ] Web dashboard
- [ ] Manual backup trigger
- [ ] Backup history
- [ ] Restore workflow
- [ ] Restore verification
- [ ] Advanced retention
- [ ] Backup size anomaly detection
- [ ] Backup duration anomaly detection
- [ ] Notification management

## 23. Phase 3

If the number of applications/servers grows:

```text
Backup API
    ↓
Queue
    ↓
Workers
    ↓
Backup Agents
```

Then the following can be considered:

- Redis
- Celery / Dramatiq
- Distributed workers
- Centralized log aggregation
- RBAC
- Audit log
- Multi-storage
- Disaster recovery

Not yet needed for 5 applications.

## 24. Recommended Tech Stack

```text
Backup Agent
    Python

Backup API
    FastAPI

Database
    PostgreSQL

Backup Storage
    rustfs

Monitoring
    Prometheus

Visualization
    Grafana

Scheduling
    systemd timer / cron

Container
    Podman

Deployment
    Podman Compose (podman-compose)
```

## 25. Architecture Principles

1. **The Agent is responsible for performing backups.**
2. **The API is responsible for receiving and recording backup results.**
3. **PostgreSQL stores metadata.**
4. **rustfs stores backup files.**
5. **Prometheus measures health and metrics.**
6. **Grafana visualizes monitoring.**
7. **FastAPI does not run `pg_dump` directly.**
8. **Backup jobs must not leave API requests hanging.**
9. **Every backup must produce a status that can be monitored.**
10. **Backups must be verified, not just created.**
