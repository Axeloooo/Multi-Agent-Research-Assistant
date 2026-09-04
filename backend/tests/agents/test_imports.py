"""Import boundaries for the isolated backend runtime."""


def test_backend_packages_import_from_the_src_package() -> None:
    from src.api.app import create_app
    from src.pipelines.pipeline import stream_research_pipeline

    assert callable(create_app)
    assert callable(stream_research_pipeline)
