"""
SmartRAGService wrapper with detailed performance profiling
Wraps SmartRAGService.process_contextual_query to measure each stage
"""

import logging
import time
from typing import Optional, List, Dict, Any
import psutil
import os
from functools import wraps
from datetime import datetime

logger = logging.getLogger(__name__)


class QueryProfiler:
    """Detailed query profiler for performance analysis"""

    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.stages: Dict[str, Dict[str, Any]] = {}
        self.query_start_time = None
        self.start_memory_mb = None

    def start_query(self, query: str):
        """Start tracking a new query"""
        self.query_start_time = time.time()
        self.start_memory_mb = self.process.memory_info().rss / 1024 / 1024
        self.stages = {}
        logger.info(f"\n{'='*80}")
        logger.info(f"🚀 QUERY PROFILING START")
        logger.info(f"Query: {query[:60]}...")
        logger.info(f"Start Memory: {self.start_memory_mb:.1f} MB")
        logger.info(f"Timestamp: {datetime.now().isoformat()}")
        logger.info(f"{'='*80}\n")

    def mark_stage(self, stage_name: str):
        """Mark start of a stage"""
        if stage_name not in self.stages:
            self.stages[stage_name] = {
                "start_time": time.time(),
                "start_memory_mb": self.process.memory_info().rss / 1024 / 1024,
                "duration_sec": 0,
                "memory_delta_mb": 0,
                "cpu_percent": 0
            }

    def end_stage(self, stage_name: str):
        """End a stage and record metrics"""
        if stage_name not in self.stages:
            return

        stage = self.stages[stage_name]
        elapsed = time.time() - stage["start_time"]
        end_memory = self.process.memory_info().rss / 1024 / 1024
        cpu = self.process.cpu_percent(interval=0.01)

        stage["duration_sec"] = round(elapsed, 3)
        stage["memory_delta_mb"] = round(end_memory - stage["start_memory_mb"], 1)
        stage["cpu_percent"] = round(cpu, 1)

        # Log with emoji based on duration
        if elapsed < 0.1:
            emoji = "⚡"
        elif elapsed < 0.5:
            emoji = "🟢"
        elif elapsed < 1.0:
            emoji = "🟡"
        elif elapsed < 3.0:
            emoji = "🟠"
        else:
            emoji = "🔴"

        logger.info(f"{emoji} {stage_name:40} | {elapsed:7.3f}s | Mem: {stage['memory_delta_mb']:+6.1f}MB | CPU: {cpu:5.1f}%")

    def finish_query(self):
        """Finish profiling and print report"""
        if not self.query_start_time:
            return

        total_time = time.time() - self.query_start_time
        end_memory_mb = self.process.memory_info().rss / 1024 / 1024
        memory_delta = end_memory_mb - self.start_memory_mb

        logger.info(f"\n{'='*80}")
        logger.info(f"📊 PERFORMANCE REPORT")
        logger.info(f"{'='*80}\n")

        # Sort stages by duration
        sorted_stages = sorted(
            self.stages.items(),
            key=lambda x: x[1]["duration_sec"],
            reverse=True
        )

        logger.info(f"{'Stage':<40} | {'Time':>8} | {'%':>5} | {'Memory':>8} | {'CPU':>5}")
        logger.info("-" * 80)

        for stage_name, metrics in sorted_stages:
            duration = metrics["duration_sec"]
            percentage = (duration / total_time * 100) if total_time > 0 else 0
            mem_delta = metrics["memory_delta_mb"]
            cpu = metrics["cpu_percent"]

            # Bar chart
            bar_length = int(percentage / 2)
            bar = "▓" * bar_length + "░" * (50 - bar_length)

            logger.info(f"{stage_name:<40} | {duration:7.3f}s | {percentage:4.1f}% | {mem_delta:+7.1f}MB | {cpu:4.1f}%")

        logger.info("-" * 80)
        logger.info(f"{'TOTAL':<40} | {total_time:7.3f}s | {'100.0':>4}% | {memory_delta:+7.1f}MB")
        logger.info(f"{'='*80}\n")

        # Print bottlenecks
        if sorted_stages:
            slowest = sorted_stages[0]
            slowest_percentage = (slowest[1]["duration_sec"] / total_time * 100)
            if slowest_percentage > 30:
                logger.warning(f"⚠️  BOTTLENECK DETECTED: {slowest[0]} takes {slowest_percentage:.1f}% of total time")

        return {
            "total_time": total_time,
            "memory_delta_mb": memory_delta,
            "stages": self.stages
        }


# Global profiler instance
_query_profiler: Optional[QueryProfiler] = None


def get_query_profiler() -> QueryProfiler:
    """Get or create global query profiler"""
    global _query_profiler
    if _query_profiler is None:
        _query_profiler = QueryProfiler()
    return _query_profiler


def profile_method(method_name: str):
    """Decorator to profile a method"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            profiler = get_query_profiler()
            profiler.mark_stage(method_name)
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                profiler.end_stage(method_name)
        return wrapper
    return decorator
