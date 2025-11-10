import time
import logging
import json
from typing import Dict, Any, Optional
from contextlib import contextmanager
from datetime import datetime
import psutil
import os

logger = logging.getLogger(__name__)


class PerformanceProfiler:
    """Performance profiling tool for tracking query execution time and resource usage"""

    def __init__(self):
        self.metrics: Dict[str, Any] = {}
        self.start_time = None
        self.start_memory = None
        self.start_cpu = None
        self.process = psutil.Process(os.getpid())

    def start_profiling(self):
        """Start profiling session"""
        self.start_time = time.time()
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.start_cpu = self.process.cpu_percent(interval=0.1)
        self.metrics = {}
        logger.info(f"🔍 Profiling started | Memory: {self.start_memory:.1f}MB | CPU: {self.start_cpu:.1f}%")

    def end_profiling(self) -> Dict[str, Any]:
        """End profiling session and return summary"""
        if not self.start_time:
            return {}

        total_time = time.time() - self.start_time
        end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        end_cpu = self.process.cpu_percent(interval=0.1)
        memory_delta = end_memory - self.start_memory

        summary = {
            "total_time_sec": round(total_time, 3),
            "start_memory_mb": round(self.start_memory, 1),
            "end_memory_mb": round(end_memory, 1),
            "memory_delta_mb": round(memory_delta, 1),
            "cpu_percent": round(end_cpu, 1),
            "timestamp": datetime.now().isoformat(),
            "metrics": self.metrics
        }

        logger.info(f"📊 Profiling finished | Total: {total_time:.2f}s | Memory Δ: {memory_delta:+.1f}MB | CPU: {end_cpu:.1f}%")
        return summary

    @contextmanager
    def measure(self, operation_name: str):
        """Context manager for measuring operation time"""
        start = time.time()
        mem_before = self.process.memory_info().rss / 1024 / 1024

        try:
            logger.debug(f"⏱️  Starting: {operation_name}")
            yield
        finally:
            elapsed = time.time() - start
            mem_after = self.process.memory_info().rss / 1024 / 1024
            mem_delta = mem_after - mem_before

            self.metrics[operation_name] = {
                "time_sec": round(elapsed, 3),
                "memory_delta_mb": round(mem_delta, 1)
            }

            # Log with color coding for slow operations
            emoji = "⚡" if elapsed < 0.5 else "🔶" if elapsed < 2 else "🔴"
            logger.info(f"{emoji} {operation_name}: {elapsed:.3f}s | Memory Δ: {mem_delta:+.1f}MB")

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        return self.metrics.copy()

    def log_detailed_report(self):
        """Log detailed performance report"""
        if not self.metrics:
            return

        sorted_metrics = sorted(
            self.metrics.items(),
            key=lambda x: x[1]["time_sec"],
            reverse=True
        )

        logger.info("\n" + "="*60)
        logger.info("📈 PERFORMANCE REPORT")
        logger.info("="*60)

        total_time = sum(m["time_sec"] for _, m in sorted_metrics)

        for operation, metrics in sorted_metrics:
            time_sec = metrics["time_sec"]
            mem_delta = metrics["memory_delta_mb"]
            percentage = (time_sec / total_time * 100) if total_time > 0 else 0

            bar = "█" * int(percentage / 5)
            logger.info(f"{operation:40} | {time_sec:7.3f}s ({percentage:5.1f}%) {bar} | Mem: {mem_delta:+.1f}MB")

        logger.info("="*60)
        logger.info(f"Total execution time: {total_time:.3f}s")
        logger.info("="*60 + "\n")


# Global profiler instance
_profiler: Optional[PerformanceProfiler] = None


def get_profiler() -> PerformanceProfiler:
    """Get or create global profiler instance"""
    global _profiler
    if _profiler is None:
        _profiler = PerformanceProfiler()
    return _profiler
