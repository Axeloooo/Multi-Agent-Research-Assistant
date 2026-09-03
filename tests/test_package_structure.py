import sys
from importlib import import_module
from types import ModuleType

import pytest


def test_importing_main_does_not_run_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    fake_pipeline = ModuleType("src.pipelines.pipeline")
    fake_pipeline.run_reseaerch_pipeline = lambda topic: calls.append(topic)
    monkeypatch.setitem(sys.modules, "src.pipelines.pipeline", fake_pipeline)
    sys.modules.pop("main", None)

    try:
        import_module("main")

        assert calls == []
    finally:
        sys.modules.pop("main", None)


@pytest.mark.parametrize(
    "module_name",
    [
        "src",
        "src.agents",
        "src.pipelines",
        "src.tools",
        "src.tools.tools",
    ],
)
def test_project_module_imports(module_name: str) -> None:
    module = import_module(module_name)

    assert isinstance(module, ModuleType)
