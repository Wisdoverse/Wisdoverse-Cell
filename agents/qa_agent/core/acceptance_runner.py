"""Async wrapper around .acceptance/runner.py.

Runs the acceptance framework as a subprocess using asyncio,
avoiding blocking the event loop (per CLAUDE.md constitution).
Uses create_subprocess_exec (not shell) — safe from injection.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from shared.utils.logger import get_logger

from .config import QACoreConfig

logger = get_logger("qa_agent.runner")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RUNNER_SCRIPT = str(PROJECT_ROOT / ".acceptance" / "runner.py")


class AcceptanceRunnerService:
    """Runs .acceptance/runner.py via async subprocess."""

    def __init__(
        self,
        timeout: int | None = None,
        config: QACoreConfig | None = None,
    ):
        self._config = config or QACoreConfig()
        self._timeout = timeout or self._config.runner_timeout_seconds

    async def run_json(
        self,
        agent_name: str,
        *,
        level: str = "all",
        diff_ref: str | None = None,
        mr_id: str = "",
    ) -> dict:
        """Run acceptance checks and return parsed JSON report."""
        target = f"agents/{agent_name}"
        args = [
            "python",
            RUNNER_SCRIPT,
            "--target",
            target,
            "--level",
            level,
            "--format",
            "json",
        ]
        if diff_ref:
            args.extend(["--diff", diff_ref])
        if mr_id:
            args.extend(["--mr-id", mr_id])

        logger.info("runner_start", agent_name=agent_name, level=level)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=PROJECT_ROOT,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
            stdout_str = stdout_bytes.decode(errors="replace")
            stderr_str = stderr_bytes.decode(errors="replace")
            exit_code = proc.returncode or 0

            try:
                report = json.loads(stdout_str)
            except json.JSONDecodeError:
                logger.error(
                    "runner_parse_failed",
                    stdout=stdout_str[:500],
                    stderr=stderr_str[:500],
                )
                return self._error_report(
                    f"JSON parse failed: {stderr_str[:200]}",
                    exit_code=exit_code,
                    stdout=stdout_str[:1000],
                    stderr=stderr_str[:1000],
                )

            report["exit_code"] = exit_code
            if exit_code != 0:
                report["stdout"] = stdout_str[:2000]
            if stderr_str.strip():
                report["stderr"] = stderr_str[:2000]

            logger.info(
                "runner_complete",
                agent_name=agent_name,
                l0=report.get("summary", {}).get("l0_gate"),
                exit_code=exit_code,
                duration=report.get("duration_seconds"),
            )
            return report

        except asyncio.TimeoutError:
            logger.error(
                "runner_timeout",
                agent_name=agent_name,
                timeout=self._timeout,
            )
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass  # Process already exited
            except Exception as e:
                logger.warning("runner_kill_failed", error=str(e), error_type=type(e).__name__)
            return self._error_report(
                f"Runner timed out after {self._timeout}s",
                duration=float(self._timeout),
            )
        except (OSError, FileNotFoundError) as e:
            logger.error("runner_exec_failed", agent_name=agent_name, error=str(e))
            return self._error_report(f"Runner execution failed: {e}")
        except Exception as e:
            logger.error(
                "runner_unexpected_error",
                agent_name=agent_name,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def run_markdown(
        self,
        agent_name: str,
        *,
        level: str = "all",
    ) -> str:
        """Run acceptance and return Markdown report for MR comments."""
        target = f"agents/{agent_name}"
        args = [
            "python",
            RUNNER_SCRIPT,
            "--target",
            target,
            "--level",
            level,
            "--format",
            "markdown",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=PROJECT_ROOT,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
            out = stdout_bytes.decode(errors="replace")
            return out or stderr_bytes.decode(errors="replace")
        except asyncio.TimeoutError:
            logger.error("runner_markdown_timeout", agent_name=agent_name, timeout=self._timeout)
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass  # Process already exited
            except Exception as e:
                logger.warning("runner_kill_failed", error=str(e), error_type=type(e).__name__)
            return f"> **ERROR**: Acceptance check timed out after {self._timeout}s. Please re-run."
        except Exception as e:
            logger.error(
                "runner_markdown_error",
                agent_name=agent_name,
                error=str(e),
                error_type=type(e).__name__,
            )
            return f"> **ERROR**: Acceptance check failed: {e}"

    @staticmethod
    def _error_report(
        error: str,
        *,
        exit_code: int = -1,
        duration: float = 0,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> dict:
        report: dict = {
            "summary": {
                "l0_gate": "ERROR",
                "l1_check": "ERROR",
                "l2_report": "INFO",
                "total_checks": 0,
                "l0_failures": 0,
                "l1_warnings": 0,
            },
            "results": [],
            "duration_seconds": duration,
            "exit_code": exit_code,
            "error": error,
        }
        if stdout:
            report["stdout"] = stdout
        if stderr:
            report["stderr"] = stderr
        return report
