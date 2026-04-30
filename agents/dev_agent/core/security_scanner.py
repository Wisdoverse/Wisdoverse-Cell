"""pip-audit + detect-secrets wrapper for supply chain security."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from shared.utils.logger import get_logger

logger = get_logger("dev_agent.security")


@dataclass
class ScanReport:
    passed: bool = True
    issues: list[str] = field(default_factory=list)


class SecurityScanner:
    async def scan(self, workspace_path: str = ".") -> ScanReport:
        """Run security scans on the given workspace directory.

        Args:
            workspace_path: Directory path to scan (AgentForge workspace).
                           Defaults to current directory for MVP.
        """
        report = ScanReport()
        # pip-audit runs against installed packages (not path-specific)
        try:
            proc = await asyncio.create_subprocess_exec(
                "pip-audit",
                "--strict",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                report.passed = False
                report.issues.append(f"pip-audit: {stdout.decode()[:500]}")
        except FileNotFoundError:
            logger.error("pip_audit_not_installed", exc_info=True)
            report.passed = False
            report.issues.append("pip-audit not installed - security scan skipped")
        except asyncio.TimeoutError:
            report.passed = False
            report.issues.append("pip-audit timed out - treating as failure")
        # detect-secrets scans the workspace_path
        try:
            proc = await asyncio.create_subprocess_exec(
                "detect-secrets", "scan", workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode != 0:
                output = stdout.decode()[:500]
                if "secret" in output.lower() or "potential" in output.lower():
                    report.passed = False
                    report.issues.append(f"detect-secrets: {output}")
        except FileNotFoundError:
            logger.error("detect_secrets_not_installed", exc_info=True)
            report.passed = False
            report.issues.append("detect-secrets not installed - security scan skipped")
        except asyncio.TimeoutError:
            report.passed = False
            report.issues.append("detect-secrets timed out - treating as failure")
        return report
