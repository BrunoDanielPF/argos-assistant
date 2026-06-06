from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class Timer:
    started_at: float

    @classmethod
    def start(cls) -> "Timer":
        return cls(started_at=monotonic())

    def elapsed_ms(self) -> float:
        return max(0.0, (monotonic() - self.started_at) * 1000)
