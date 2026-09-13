"""Weekly scheduler for orchestrator runs."""

import logging
from datetime import datetime, time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from groww_pulse.config.settings import Settings
from groww_pulse.logging_utils.logger import StructuredLogger
from groww_pulse.orchestration.orchestrator import RunOrchestrator


class RunScheduler:
    """Background scheduler for weekly review pulse runs."""
    
    def __init__(
        self,
        orchestrator: RunOrchestrator,
        settings: Settings | None = None,
        day_of_week: str = "0",  # Monday
        hour: int = 9,
        minute: int = 0,
    ) -> None:
        """Initialize scheduler.
        
        Args:
            orchestrator: RunOrchestrator instance to execute
            settings: Settings (unused, kept for future extensibility)
            day_of_week: Cron day of week (0=Monday, 6=Sunday)
            hour: Hour to run (0-23)
            minute: Minute to run (0-59)
        """
        self.orchestrator = orchestrator
        self.day_of_week = day_of_week
        self.hour = hour
        self.minute = minute
        self.scheduler = BackgroundScheduler()
    
    def start(self) -> None:
        """Start the background scheduler."""
        if self.scheduler.running:
            return
        
        # Add weekly job
        trigger = CronTrigger(
            day_of_week=self.day_of_week,
            hour=self.hour,
            minute=self.minute,
        )
        
        self.scheduler.add_job(
            self._run_pulse,
            trigger=trigger,
            id="weekly_pulse_run",
            name="Weekly Review Pulse Generation",
            replace_existing=True,
        )
        
        self.scheduler.start()
        StructuredLogger.info(
            "scheduler_started",
            day_of_week=self.day_of_week,
            hour=self.hour,
            minute=self.minute,
        )
    
    def stop(self) -> None:
        """Stop the background scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            StructuredLogger.info("scheduler_stopped")
    
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self.scheduler.running
    
    def get_next_run_time(self) -> datetime | None:
        """Get the next scheduled run time."""
        job = self.scheduler.get_job("weekly_pulse_run")
        if job:
            return job.next_run_time
        return None
    
    def _run_pulse(self) -> None:
        """Execute the pulse generation run."""
        try:
            StructuredLogger.info("scheduled_run_started")
            run, pulse = self.orchestrator.execute_run()
            StructuredLogger.info(
                "scheduled_run_completed",
                run_id=run.id,
                status=run.status.value,
            )
        except Exception as exc:
            StructuredLogger.error(
                "scheduled_run_failed",
                error=str(exc),
            )


class SimpleScheduler:
    """Simple non-async scheduler for CLI-based execution."""
    
    def __init__(
        self,
        orchestrator: RunOrchestrator,
        day_of_week: str = "0",
        hour: int = 9,
        minute: int = 0,
    ) -> None:
        """Initialize simple scheduler.
        
        Args:
            orchestrator: RunOrchestrator instance
            day_of_week: Cron day of week
            hour: Hour to run
            minute: Minute to run
        """
        self.orchestrator = orchestrator
        self.day_of_week = int(day_of_week)  # 0=Monday
        self.hour = hour
        self.minute = minute
    
    def should_run(self, now: datetime | None = None) -> bool:
        """Check if run should execute at given time."""
        now = now or datetime.now()
        
        # Check day of week (Monday=0)
        if now.weekday() != self.day_of_week:
            return False
        
        # Check hour and minute
        if now.hour != self.hour or now.minute != self.minute:
            return False
        
        return True
    
    def run_if_scheduled(self) -> tuple | None:
        """Run if scheduled for now, return (run, pulse) or None."""
        if not self.should_run():
            return None
        
        try:
            run, pulse = self.orchestrator.execute_run()
            return run, pulse
        except Exception as exc:
            StructuredLogger.error(
                "scheduled_run_failed",
                error=str(exc),
            )
            raise
