topic: str = "The impact of AI on the canadian job market in 2026"


def main() -> None:
    from src.pipelines.pipeline import run_reseaerch_pipeline

    run_reseaerch_pipeline(topic)


if __name__ == "__main__":
    main()
