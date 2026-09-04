from importlib import import_module
from types import ModuleType

import pytest


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
