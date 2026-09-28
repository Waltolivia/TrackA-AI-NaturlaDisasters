from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class WorkerConfig:
    outbox: Path
    state_db: Path
    targets: Path
    question_bank_dir: Path
    output_dir: Path
    ai_project: Path
    queue_layout: str = "v5"
    poll_seconds: float = 5.0
    max_attempts: int = 3
    retry_base_seconds: float = 30.0
    lease_seconds: int = 7200
    job_timeout_seconds: int = 7200
    probe_delay_seconds: float = 0.0

    def resolved(self) -> "WorkerConfig":
        root = REPOSITORY_ROOT

        def absolute(path: Path) -> Path:
            return path if path.is_absolute() else (root / path).resolve()

        if self.queue_layout not in {"v5", "flat"}:
            raise ValueError("queue_layout must be 'v5' or 'flat'")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be greater than zero")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.retry_base_seconds < 0:
            raise ValueError("retry_base_seconds cannot be negative")
        if self.lease_seconds <= 0 or self.job_timeout_seconds <= 0:
            raise ValueError("lease and job timeouts must be greater than zero")

        return WorkerConfig(
            outbox=absolute(self.outbox),
            state_db=absolute(self.state_db),
            targets=absolute(self.targets),
            question_bank_dir=absolute(self.question_bank_dir),
            output_dir=absolute(self.output_dir),
            ai_project=absolute(self.ai_project),
            queue_layout=self.queue_layout,
            poll_seconds=self.poll_seconds,
            max_attempts=self.max_attempts,
            retry_base_seconds=self.retry_base_seconds,
            lease_seconds=self.lease_seconds,
            job_timeout_seconds=self.job_timeout_seconds,
            probe_delay_seconds=self.probe_delay_seconds,
        )


def default_config() -> WorkerConfig:
    return WorkerConfig(
        outbox=Path("disaster_monitor-v5/outbox"),
        state_db=Path("pipeline_data/worker.db"),
        targets=Path("ai_probe_runner/config/targets.mock.json"),
        question_bank_dir=Path("ai_probe_runner/config/question_banks"),
        output_dir=Path("pipeline_data/results"),
        ai_project=Path("ai_probe_runner"),
    )
