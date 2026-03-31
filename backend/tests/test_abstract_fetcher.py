from paper_agent.services.abstract_fetcher import AbstractFetcher


def test_extract_inverted_index_text_rebuilds_abstract() -> None:
    fetcher = AbstractFetcher()

    abstract = fetcher._extract_inverted_index_text(  # pyright: ignore[reportPrivateUsage]
        {
            "world": [1],
            "Hello": [0],
            "again": [2],
        }
    )

    assert abstract == "Hello world again"


def test_title_similarity_prefers_exact_matches() -> None:
    fetcher = AbstractFetcher()

    exact = fetcher._title_similarity("paper title", "paper title")  # pyright: ignore[reportPrivateUsage]
    partial = fetcher._title_similarity("paper title", "different title")  # pyright: ignore[reportPrivateUsage]

    assert exact == 1.0
    assert partial < exact
