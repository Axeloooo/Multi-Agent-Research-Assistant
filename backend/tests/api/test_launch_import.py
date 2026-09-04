"""Regression coverage for the documented local API launch target."""

from pathlib import Path


def test_api_factory_imports_from_the_backend_working_directory() -> None:
    from src.api.app import create_app

    assert callable(create_app)


def test_frontend_distribution_path_is_relative_to_the_repository_root() -> None:
    from src.api.app import _frontend_dist

    assert _frontend_dist() == Path(__file__).parents[3] / "frontend" / "dist"
