"""Hardware and package versions, recorded with every throughput number."""

from __future__ import annotations

import os
import platform
import resource
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from docfunnel.evals.parse.models import (
    Hardware,
)


def _sysctl(name: str) -> str | None:
    try:
        return subprocess.run(
            ["sysctl", "-n", name], capture_output=True, text=True, check=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def hardware_info() -> Hardware:
    cpu = platform.processor() or platform.machine()
    memory = None
    if sys.platform == "darwin":
        cpu = _sysctl("machdep.cpu.brand_string") or cpu
        raw = _sysctl("hw.memsize")
        memory = int(raw) / 2**30 if raw else None
    else:
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal"):
                    memory = int(line.split()[1]) / 2**20
                    break
        except OSError:
            pass
    return Hardware(
        cpu=cpu,
        logical_cores=os.cpu_count() or 1,
        memory_gb=round(memory, 1) if memory else None,
        os=f"{platform.system()} {platform.release()} ({platform.machine()})",
        python=platform.python_version(),
    )


def package_versions() -> dict[str, str]:
    found = {}
    for name in ("pypdfium2", "rapidocr", "onnxruntime", "pytesseract", "pypdf", "reportlab"):
        try:
            found[name] = version(name)
        except PackageNotFoundError:
            continue
    try:
        import pytesseract

        found["tesseract"] = str(pytesseract.get_tesseract_version())
    except Exception:  # binary or wrapper missing
        pass
    return found


def peak_child_rss_mb() -> float | None:
    rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if not rss:
        return None
    return round(rss / 2**20 if sys.platform == "darwin" else rss / 2**10, 1)
