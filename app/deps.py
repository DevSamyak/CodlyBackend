from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from .services.contest_service import ContestService
from .services.potd_service import PotdService
from .services.profile_service import ProfileService


@dataclass
class Services:
    profiles: ProfileService
    contests: ContestService
    potd: PotdService


def get_services(request: Request) -> Services:
    return request.app.state.services
