"""Uniqueness boundary for concurrently imported company templates."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .tables import ControlPlaneBase


class CompanyTemplateNameTable(ControlPlaneBase):
    __tablename__ = "control_plane_company_template_names"
    normalized_name: Mapped[str] = mapped_column(String(256), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(48), unique=True)
