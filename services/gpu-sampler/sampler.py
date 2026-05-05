"""Operator-observability sampler for the admin /usage page.

Polls two signal sources every SAMPLE_INTERVAL_SECONDS and writes a
row to private.gpu_samples and private.tei_samples respectively:

  1. NVML (nvidia-ml-py) for live VRAM / GPU utilisation / temp / power.
     Read-only, no CUDA context, ~0 VRAM impact on the device it watches.
  2. TEI's native Prometheus /metrics endpoint at $TEI_URL/metrics for
     queue depth, request count, and latency-histogram percentiles.

Both writes happen in one transaction per tick so an admin dashboard
poll never sees a half-tick. The connection is opened-and-closed each
cycle — at 30s cadence the open cost is negligible and we don't hold
a pool slot through the sleep.

Failure handling is shallow on purpose: NVML or TEI hiccups are logged
to stderr and the row is skipped. Restart-on-failure handles the rare
case where pynvml itself dies; everything else lives in the loop body.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

import httpx
import psycopg
from pynvml import (  # type: ignore[import-untyped]
    nvmlDeviceGetCount,
    nvmlDeviceGetHandleByIndex,
    nvmlDeviceGetMemoryInfo,
    nvmlDeviceGetPowerUsage,
    nvmlDeviceGetTemperature,
    nvmlDeviceGetUtilizationRates,
    NVML_TEMPERATURE_GPU,
    nvmlInit,
    nvmlShutdown,
    NVMLError,
)

DATABASE_URL = os.environ["DATABASE_URL"]
TEI_URL = os.environ.get("TEI_URL", "http://tei:80").rstrip("/")
SAMPLE_INTERVAL_SECONDS = int(os.environ.get("SAMPLE_INTERVAL_SECONDS", "30"))
GPU_INDEX = int(os.environ.get("GPU_INDEX", "0"))

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("gpu-sampler")


def read_gpu_sample() -> dict[str, Any] | None:
    """One NVML poll. Returns None if NVML is unreachable."""
    try:
        handle = nvmlDeviceGetHandleByIndex(GPU_INDEX)
        mem = nvmlDeviceGetMemoryInfo(handle)
        util = nvmlDeviceGetUtilizationRates(handle)
        try:
            temp_c = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
        except NVMLError:
            temp_c = None
        try:
            # NVML returns power in milliwatts.
            power_w = nvmlDeviceGetPowerUsage(handle) / 1000.0
        except NVMLError:
            power_w = None
        return {
            "gpu_index": GPU_INDEX,
            "mem_used_mb": mem.used // (1024 * 1024),
            "mem_total_mb": mem.total // (1024 * 1024),
            "util_gpu_pct": util.gpu,
            "util_mem_pct": util.memory,
            "temperature_c": temp_c,
            "power_w": power_w,
        }
    except NVMLError as err:
        log.warning("NVML read failed: %s", err)
        return None


def parse_tei_metrics(text: str) -> dict[str, Any]:
    """Lightweight Prometheus text-format parser. Returns just the
    fields we surface on the dashboard.

    We avoid pulling in prometheus_client just to parse 6 numbers —
    the format is a few lines of `metric{labels} value` and a regex
    walk is plenty.

    Histogram percentiles use the cumulative-bucket trick: pick the
    smallest le-bucket whose count ≥ pct × total_count. Approximate
    (returns the bucket upper bound, not interpolated) but consistent
    over time, which is what the admin sparkline needs.
    """
    out: dict[str, Any] = {
        "queue_size": None,
        "request_count_total": None,
        "request_failure_total": None,
        "request_duration_p50_ms": None,
        "request_duration_p95_ms": None,
        "request_duration_p99_ms": None,
        "batch_next_size_avg": None,
        "raw_metrics": text,
    }

    # Histogram buckets for te_request_duration_seconds: list of (le, cum_count).
    duration_buckets: list[tuple[float, float]] = []
    duration_count = 0.0

    # te_batch_next_size is a histogram too — derive a rough mean as
    # sum / count for a single number on the dashboard.
    batch_sum = None
    batch_count = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        # Split on the LAST whitespace — labels can contain spaces in
        # quoted values, the metric value is always the trailing token.
        try:
            metric_part, value_part = line.rsplit(" ", 1)
        except ValueError:
            continue
        try:
            value = float(value_part)
        except ValueError:
            continue

        # Strip labels: `name{l1="v1",...}` → `name`. Capture le for
        # histogram buckets.
        name = metric_part
        le_value: str | None = None
        if "{" in metric_part:
            name, _, label_block = metric_part.partition("{")
            label_block = label_block.rstrip("}")
            for kv in label_block.split(","):
                k, _, v = kv.partition("=")
                if k.strip() == "le":
                    le_value = v.strip().strip('"')

        # TEI metric names start with `te_`. Match on the metric base.
        if name == "te_queue_size":
            out["queue_size"] = int(value)
        elif name == "te_request_count":
            # Total requests served. Sum across status labels.
            out["request_count_total"] = int(
                (out["request_count_total"] or 0) + value
            )
        elif name == "te_request_failure":
            out["request_failure_total"] = int(
                (out["request_failure_total"] or 0) + value
            )
        elif name == "te_request_duration_bucket" and le_value is not None:
            try:
                duration_buckets.append((float(le_value), value))
            except ValueError:
                # le="+Inf" lands here.
                duration_buckets.append((float("inf"), value))
        elif name == "te_request_duration_count":
            duration_count = value
        elif name == "te_batch_next_size_sum":
            batch_sum = value
        elif name == "te_batch_next_size_count":
            batch_count = value

    if duration_buckets and duration_count > 0:
        # Buckets are reported cumulative in Prometheus.
        duration_buckets.sort(key=lambda b: b[0])
        out["request_duration_p50_ms"] = _bucket_percentile(
            duration_buckets, duration_count, 0.50
        )
        out["request_duration_p95_ms"] = _bucket_percentile(
            duration_buckets, duration_count, 0.95
        )
        out["request_duration_p99_ms"] = _bucket_percentile(
            duration_buckets, duration_count, 0.99
        )

    if batch_sum is not None and batch_count and batch_count > 0:
        out["batch_next_size_avg"] = round(batch_sum / batch_count, 2)

    return out


def _bucket_percentile(
    buckets: list[tuple[float, float]],
    total: float,
    pct: float,
) -> float | None:
    """Return the smallest bucket upper-bound whose cumulative count
    ≥ pct × total, in milliseconds. Returns None on +Inf-only data.
    """
    if not buckets or total <= 0:
        return None
    target = pct * total
    for le, count in buckets:
        if count >= target:
            if le == float("inf"):
                return None
            return round(le * 1000.0, 2)
    return None


async def fetch_tei_metrics(client: httpx.AsyncClient) -> dict[str, Any] | None:
    try:
        res = await client.get(f"{TEI_URL}/metrics", timeout=5.0)
        res.raise_for_status()
        return parse_tei_metrics(res.text)
    except (httpx.HTTPError, ValueError) as err:
        log.warning("TEI /metrics fetch failed: %s", err)
        return None


def write_samples(
    conn: psycopg.Connection[Any],
    gpu: dict[str, Any] | None,
    tei: dict[str, Any] | None,
) -> None:
    with conn.cursor() as cur:
        if gpu is not None:
            cur.execute(
                """
                INSERT INTO private.gpu_samples (
                  gpu_index, mem_used_mb, mem_total_mb,
                  util_gpu_pct, util_mem_pct, temperature_c, power_w
                ) VALUES (%(gpu_index)s, %(mem_used_mb)s, %(mem_total_mb)s,
                          %(util_gpu_pct)s, %(util_mem_pct)s, %(temperature_c)s, %(power_w)s)
                """,
                gpu,
            )
        if tei is not None:
            cur.execute(
                """
                INSERT INTO private.tei_samples (
                  queue_size, request_count_total, request_failure_total,
                  request_duration_p50_ms, request_duration_p95_ms,
                  request_duration_p99_ms, batch_next_size_avg, raw_metrics
                ) VALUES (%(queue_size)s, %(request_count_total)s, %(request_failure_total)s,
                          %(request_duration_p50_ms)s, %(request_duration_p95_ms)s,
                          %(request_duration_p99_ms)s, %(batch_next_size_avg)s, %(raw_metrics)s)
                """,
                tei,
            )
    conn.commit()


async def main() -> None:
    log.info(
        "starting gpu-sampler interval=%ss tei_url=%s gpu_index=%s",
        SAMPLE_INTERVAL_SECONDS, TEI_URL, GPU_INDEX,
    )
    nvmlInit()
    try:
        device_count = nvmlDeviceGetCount()
        log.info("NVML up; %d device(s) visible", device_count)

        async with httpx.AsyncClient() as client:
            while True:
                gpu = read_gpu_sample()
                tei = await fetch_tei_metrics(client)
                if gpu is None and tei is None:
                    log.warning("both samplers failed this tick; skipping write")
                else:
                    try:
                        with psycopg.connect(DATABASE_URL) as conn:
                            write_samples(conn, gpu, tei)
                        log.debug(
                            "tick: gpu=%s tei=%s",
                            "ok" if gpu else "skip",
                            "ok" if tei else "skip",
                        )
                    except psycopg.Error as err:
                        log.warning("DB write failed: %s", err)
                await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)
    finally:
        try:
            nvmlShutdown()
        except NVMLError:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
