"""cpp_analyzer (tree-sitter 기반 C/C++ 분석기) 단위 테스트.

`tests/samples/cpp/` 의 합성 샘플(`game_core.c`, `render.c`, `render.h`)에
대해 schema 호환성 · CC · invoked_names · global state · 게임 루프 진입점
인식을 확인한다.
"""

from __future__ import annotations

from pathlib import Path

from game_si.cpp_analyzer import analyze_cpp


SAMPLE_DIR = Path(__file__).parent / "samples" / "cpp"


def _by_relpath(data: dict) -> dict[str, dict]:
    return {f["relative_path"]: f for f in data["files"]}


def _methods_by_name(file_node: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for c in file_node["classes"]:
        for m in c["methods"]:
            out[m["name"]] = m
    return out


# ---------------------------------------------------------------------------
# 스키마 호환성
# ---------------------------------------------------------------------------


def test_schema_keys_match_csharp_analyzer():
    r = analyze_cpp(SAMPLE_DIR).data
    assert r["schema_version"] == "0.2"
    assert "summary" in r and "files" in r and "errors" in r
    summary_keys = {"total_files", "total_classes", "total_methods", "total_loc", "elapsed_ms"}
    assert summary_keys <= r["summary"].keys()
    for f in r["files"]:
        assert {"path", "relative_path", "loc", "classes"} <= f.keys()
        for c in f["classes"]:
            assert {
                "name", "fully_qualified_name", "namespace", "kind",
                "start_line", "end_line", "is_static", "is_partial", "is_abstract",
                "base_types", "referenced_types", "static_member_accesses",
                "singleton_accesses", "methods",
            } <= c.keys()
            for m in c["methods"]:
                assert {
                    "name", "signature", "start_line", "end_line", "parameter_count",
                    "return_type", "is_static", "is_async", "is_override",
                    "cyclomatic_complexity", "loc", "invoked_names", "is_game_loop_entry",
                } <= m.keys()
                # 내부 helper 키는 직렬화에서 제외되어야 한다.
                assert "_global_accesses" not in m


# ---------------------------------------------------------------------------
# 파일 수집
# ---------------------------------------------------------------------------


def test_headers_excluded():
    r = analyze_cpp(SAMPLE_DIR).data
    by_path = _by_relpath(r)
    assert "game_core.c" in by_path
    assert "render.c" in by_path
    # render.h 는 body 가 없으므로 분석 단위에 포함되지 않는다.
    assert "render.h" not in by_path
    # namespaces.cpp 는 namespace 추적 테스트용 파일 (추가 분석 단위)
    assert "namespaces.cpp" in by_path
    assert r["summary"]["total_files"] == 3


# ---------------------------------------------------------------------------
# Cyclomatic Complexity
# ---------------------------------------------------------------------------


def test_cyclomatic_complexity_values():
    r = analyze_cpp(SAMPLE_DIR).data
    methods = _methods_by_name(_by_relpath(r)["game_core.c"])
    # 본문 구조에 근거한 정답
    assert methods["IncCounter"]["cyclomatic_complexity"] == 1     # 분기 없음
    assert methods["Tick"]["cyclomatic_complexity"] == 3            # if + if
    assert methods["RenderFrame"]["cyclomatic_complexity"] == 6     # for + if + && + else-if + ||
    assert methods["MainLoop"]["cyclomatic_complexity"] == 2        # while


# ---------------------------------------------------------------------------
# 호출 관계
# ---------------------------------------------------------------------------


def test_invoked_names_capture_calls():
    r = analyze_cpp(SAMPLE_DIR).data
    methods = _methods_by_name(_by_relpath(r)["game_core.c"])
    assert "IncCounter" in methods["Tick"]["invoked_names"]
    assert "DrawSprite" in methods["RenderFrame"]["invoked_names"]
    assert set(methods["MainLoop"]["invoked_names"]) >= {"Tick", "RenderFrame"}


# ---------------------------------------------------------------------------
# 전역 상태 검출
# ---------------------------------------------------------------------------


def test_global_state_aggregates_uses():
    r = analyze_cpp(SAMPLE_DIR).data
    game_core = _by_relpath(r)["game_core.c"]
    cls = game_core["classes"][0]
    accesses = cls["static_member_accesses"]
    assert "tick_counter" in accesses
    assert "frame_index" in accesses
    assert "player_count" in accesses
    # 중복(횟수) 그대로 유지되어야 한다 — GlobalState 메트릭은 총 횟수로 계산된다.
    assert accesses.count("tick_counter") >= 2
    assert accesses.count("frame_index") >= 3


# ---------------------------------------------------------------------------
# 게임 루프 진입점 인식
# ---------------------------------------------------------------------------


def test_game_loop_entry_detection():
    r = analyze_cpp(SAMPLE_DIR).data
    methods = _methods_by_name(_by_relpath(r)["game_core.c"])
    assert methods["MainLoop"]["is_game_loop_entry"]   # ^MainLoop$
    assert methods["Tick"]["is_game_loop_entry"]       # .*Tick$
    assert methods["RenderFrame"]["is_game_loop_entry"]  # .*Frame$
    assert not methods["IncCounter"]["is_game_loop_entry"]


# ---------------------------------------------------------------------------
# Include → 클래스 의존성 그래프 입력
# ---------------------------------------------------------------------------


def test_includes_become_referenced_types():
    r = analyze_cpp(SAMPLE_DIR).data
    game_core = _by_relpath(r)["game_core.c"]
    cls = game_core["classes"][0]
    # 본문 파일 stem(="render") 이 ref 에 들어가야 metrics.py 의 클래스 그래프가
    # 이를 다른 compilation_unit 으로 매핑해 fan-out 으로 잡을 수 있다.
    assert "render" in cls["referenced_types"]


# ---------------------------------------------------------------------------
# C++ namespace 추적
# ---------------------------------------------------------------------------


def _all_classes(data: dict) -> dict[str, dict]:
    """fqn -> class node 매핑."""
    out: dict[str, dict] = {}
    for f in data["files"]:
        for c in f["classes"]:
            out[c["fully_qualified_name"]] = c
    return out


def test_cpp_namespace_tracking():
    r = analyze_cpp(SAMPLE_DIR).data
    by_fqn = _all_classes(r)

    # namespace OpenRA { class Actor { ... } } 가 OpenRA.Actor 로
    assert "OpenRA.Actor" in by_fqn
    actor = by_fqn["OpenRA.Actor"]
    assert actor["namespace"] == "OpenRA"
    assert actor["name"] == "Actor"
    assert actor["kind"] == "class"

    # 중첩 namespace
    assert "OpenRA.Network.Server" in by_fqn
    server = by_fqn["OpenRA.Network.Server"]
    assert server["namespace"] == "OpenRA.Network"


def test_cpp_nested_namespace_specifier():
    """C++17 nested namespace (A::B) 가 단일 점-구분 문자열로."""
    r = analyze_cpp(SAMPLE_DIR).data
    by_fqn = _all_classes(r)
    assert "Game.Physics.Collider" in by_fqn
    c = by_fqn["Game.Physics.Collider"]
    assert c["namespace"] == "Game.Physics"


def test_cpp_nested_class():
    """Outer class 안의 struct 도 FQN 에 outer 포함."""
    r = analyze_cpp(SAMPLE_DIR).data
    by_fqn = _all_classes(r)
    # Game::Physics::Collider 안의 struct Bounds → "Game.Physics.Collider.Bounds"
    assert "Game.Physics.Collider.Bounds" in by_fqn
    b = by_fqn["Game.Physics.Collider.Bounds"]
    assert b["namespace"] == "Game.Physics"
    assert b["kind"] == "struct"
