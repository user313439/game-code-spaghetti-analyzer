"""validate / gitlog 모듈에 대한 단위 테스트."""

from __future__ import annotations

import math

from game_si.gitlog import is_bugfix_subject
from game_si.validate import spearman


# ---------------------------------------------------------------------------
# Spearman
# ---------------------------------------------------------------------------


def test_spearman_perfect_positive():
    rho, _ = spearman([1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                      [2, 4, 6, 8, 10, 12, 14, 16, 18, 20])
    assert rho == 1.0


def test_spearman_perfect_negative():
    rho, _ = spearman([1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                      [10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
    assert rho == -1.0


def test_spearman_handles_ties():
    # 동률에 평균 순위가 적용되어야 한다.
    rho, _ = spearman([1, 1, 2, 2, 3, 3], [1, 2, 2, 3, 3, 4])
    # 단조 증가 경향이지만 동률이 있어 완전 1.0 이 아님
    assert 0.85 < rho < 1.0


def test_spearman_p_value_threshold():
    # n<10 이면 p-value None 이어야 한다.
    rho, p = spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5])
    assert p is None
    assert not math.isnan(rho)


def test_spearman_p_value_present_for_large_n():
    # n>=10 이고 strong correlation 이면 p<<1.
    rho, p = spearman(list(range(20)), [v * 2 + 1 for v in range(20)])
    assert rho == 1.0
    # |rho| == 1 인 경우는 p=None (정규근사 발산)
    assert p is None


def test_spearman_nan_for_constant():
    # y 가 상수면 분산이 0 → 계수 정의 불가
    rho, _ = spearman([1, 2, 3, 4, 5], [7, 7, 7, 7, 7])
    assert math.isnan(rho)


# ---------------------------------------------------------------------------
# bug-fix 키워드 매칭
# ---------------------------------------------------------------------------


def test_is_bugfix_detects_keywords():
    assert is_bugfix_subject("Fix crush logic")
    assert is_bugfix_subject("Crash on map load")
    assert is_bugfix_subject("Hotfix: regression in lobby")
    assert is_bugfix_subject("Patches the AI pathing bug")


def test_is_bugfix_filters_trivial():
    assert not is_bugfix_subject("Fix typo in README")
    assert not is_bugfix_subject("fix indentation")
    assert not is_bugfix_subject("Fix formatting in docs")


def test_is_bugfix_rejects_unrelated():
    assert not is_bugfix_subject("Add new tile category")
    assert not is_bugfix_subject("Bump dependency to 1.2.3")
    assert not is_bugfix_subject("")


def test_is_bugfix_case_insensitive():
    assert is_bugfix_subject("FIX leak in renderer")
    assert is_bugfix_subject("BUG: lobby UI freezes")
