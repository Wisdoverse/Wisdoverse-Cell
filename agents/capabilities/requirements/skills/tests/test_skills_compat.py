"""Verify skills compat layer."""


def test_help_skill_same():
    from agents.capabilities.requirements.skills import HelpSkill as New
    from skills import HelpSkill as Old
    assert New is Old


def test_confirm_skill_same():
    from agents.capabilities.requirements.skills import ConfirmSkill as New
    from skills import ConfirmSkill as Old
    assert New is Old


def test_all_skills_present():
    from agents.capabilities.requirements.skills import (
        BatchConfirmSkill,
        BatchRejectSkill,
        ConfirmSkill,
        ExportSkill,
        HelpSkill,
        ListSkill,
        RejectSkill,
        StatsSkill,
    )
    assert all([HelpSkill, ListSkill, ConfirmSkill, RejectSkill,
                BatchConfirmSkill, BatchRejectSkill, StatsSkill, ExportSkill])
