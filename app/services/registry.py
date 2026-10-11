from __future__ import annotations

from typing import Dict

from ..core.http import HttpClient
from ..providers.atcoder import AtCoderProvider
from ..providers.base import PlatformProvider
from ..providers.codechef import CodeChefProvider
from ..providers.codeforces import CodeforcesProvider
from ..providers.geeksforgeeks import GeeksForGeeksProvider
from ..providers.hackerrank import HackerRankProvider
from ..providers.leetcode import LeetCodeProvider
from ..providers.topcoder import ClistClient, TopCoderProvider

# Platforms that publish contest schedules (same four Krono synced).
CONTEST_PLATFORMS = ("codeforces", "leetcode", "codechef", "atcoder")


def build_providers(http: HttpClient, clist_username: str = "", clist_api_key: str = "") -> Dict[str, PlatformProvider]:
    clist = ClistClient(http, clist_username, clist_api_key)
    providers = [CodeforcesProvider(http), LeetCodeProvider(http), CodeChefProvider(http), AtCoderProvider(http),
                 GeeksForGeeksProvider(http), HackerRankProvider(http), TopCoderProvider(http, clist)]
    return {p.platform_id: p for p in providers}
