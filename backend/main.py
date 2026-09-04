topic: str = "The impact of AI on the Canadian job market in 2026"


def main() -> None:
    from research_assistant.pipelines.pipeline import run_research_pipeline

    run_research_pipeline(topic)


if __name__ == "__main__":
    main()
