"""Import boundaries for the isolated backend runtime."""


def test_backend_packages_import_without_root_src_package() -> None:
    from research_assistant.api.app import create_app
    from research_assistant.pipelines.pipeline import stream_research_pipeline

    assert callable(create_app)
    assert callable(stream_research_pipeline)
