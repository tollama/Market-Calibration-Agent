from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import DefaultDict


def _escape(v: str) -> str:
    return v.replace('\\', r'\\').replace('"', r'\"')


def _labels_to_text(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    parts = [f'{k}="{_escape(str(v))}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


@dataclass
class TSFMMetricsEmitter:
    _lock: Lock = field(default_factory=Lock)
    _counters: DefaultDict[tuple[str, tuple[tuple[str, str], ...]], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    _gauges: DefaultDict[tuple[str, tuple[tuple[str, str], ...]], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    _hist: DefaultDict[tuple[str, float, tuple[tuple[str, str], ...]], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    _hist_sum: DefaultDict[tuple[str, tuple[tuple[str, str], ...]], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    _hist_count: DefaultDict[tuple[str, tuple[tuple[str, str], ...]], float] = field(
        default_factory=lambda: defaultdict(float)
    )

    latency_buckets_ms: tuple[float, ...] = (50, 100, 200, 300, 400, 800, 1500, 3000)
    cycle_buckets_s: tuple[float, ...] = (0.05, 0.1, 0.2, 0.3, 0.6, 1.0, 2.0, 5.0)

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
        with self._lock:
            self._counters[key] += float(value)

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
        with self._lock:
            self._gauges[key] = float(value)

    def observe_hist(self, name: str, value: float, buckets: tuple[float, ...], **labels: str) -> None:
        label_items = tuple(sorted((k, str(v)) for k, v in labels.items()))
        with self._lock:
            self._hist_sum[(name, label_items)] += float(value)
            self._hist_count[(name, label_items)] += 1.0
            for bucket in buckets:
                if value <= bucket:
                    self._hist[(name, bucket, label_items)] += 1.0
            self._hist[(name, float("inf"), label_items)] += 1.0

    def observe_request_latency_ms(self, value_ms: float, **labels: str) -> None:
        self.observe_hist("tsfm_request_latency_ms_bucket", value_ms, self.latency_buckets_ms, **labels)

    def observe_cycle_time_s(self, value_s: float, **labels: str) -> None:
        self.observe_hist("tsfm_cycle_time_seconds_bucket", value_s, self.cycle_buckets_s, **labels)

    def update_calibration_gauges(
        self,
        *,
        brier: float | None = None,
        ece: float | None = None,
        log_loss: float | None = None,
        conformal_coverage: float | None = None,
        conformal_width: float | None = None,
        drift_detected: bool | None = None,
        low_confidence_market_count: int | None = None,
        total_market_count: int | None = None,
    ) -> None:
        """Bulk-update all calibration quality gauges."""
        if brier is not None:
            self.set_gauge("calibration_brier_score", brier)
        if ece is not None:
            self.set_gauge("calibration_ece", ece)
        if log_loss is not None:
            self.set_gauge("calibration_log_loss", log_loss)
        if conformal_coverage is not None:
            self.set_gauge("calibration_conformal_coverage", conformal_coverage)
        if conformal_width is not None:
            self.set_gauge("calibration_conformal_width", conformal_width)
        if drift_detected is not None:
            self.set_gauge("calibration_drift_detected", 1.0 if drift_detected else 0.0)
        if low_confidence_market_count is not None:
            self.set_gauge("calibration_low_confidence_markets", float(low_confidence_market_count))
        if total_market_count is not None:
            self.set_gauge("calibration_total_markets", float(total_market_count))

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            lines.append("# TYPE tsfm_request_total counter")
            lines.append("# TYPE tsfm_route_selected_total counter")
            lines.append("# TYPE tsfm_fallback_total counter")
            lines.append("# TYPE tsfm_breaker_open_total counter")
            lines.append("# TYPE tsfm_invalid_output_total counter")
            lines.append("# TYPE tsfm_quantile_crossing_total counter")
            lines.append("# TYPE tsfm_cache_hit_total counter")
            lines.append("# TYPE tsfm_request_latency_ms_bucket histogram")
            lines.append("# TYPE tsfm_cycle_time_seconds_bucket histogram")
            lines.append("# TYPE tsfm_interval_width gauge")
            lines.append("# TYPE tsfm_target_coverage gauge")
            lines.append("# TYPE calibration_brier_score gauge")
            lines.append("# TYPE calibration_ece gauge")
            lines.append("# TYPE calibration_log_loss gauge")
            lines.append("# TYPE calibration_conformal_coverage gauge")
            lines.append("# TYPE calibration_conformal_width gauge")
            lines.append("# TYPE calibration_drift_detected gauge")
            lines.append("# TYPE calibration_low_confidence_markets gauge")
            lines.append("# TYPE calibration_total_markets gauge")

            for (name, label_items), value in sorted(self._counters.items()):
                labels = _labels_to_text(dict(label_items))
                lines.append(f"{name}{labels} {value}")

            hist_names = sorted({k[0] for k in self._hist_sum})
            for name in hist_names:
                by_labels = [k for k in self._hist_sum if k[0] == name]
                for _, label_items in sorted(by_labels):
                    base_labels = dict(label_items)
                    for (h_name, bucket, h_labels), b_value in sorted(self._hist.items()):
                        if h_name != name or h_labels != label_items:
                            continue
                        labels = dict(base_labels)
                        labels["le"] = "+Inf" if bucket == float("inf") else str(bucket)
                        lines.append(f"{name}{_labels_to_text(labels)} {b_value}")
                    lines.append(
                        f"{name.replace('_bucket', '_sum')}{_labels_to_text(base_labels)} {self._hist_sum[(name, label_items)]}"
                    )
                    lines.append(
                        f"{name.replace('_bucket', '_count')}{_labels_to_text(base_labels)} {self._hist_count[(name, label_items)]}"
                    )

            for (name, label_items), value in sorted(self._gauges.items()):
                labels = _labels_to_text(dict(label_items))
                lines.append(f"{name}{labels} {value}")

        return "\n".join(lines) + "\n"
