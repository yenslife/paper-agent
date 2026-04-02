from paper_agent.services.paper_lookup import PaperLookupService


def test_extract_ndss_page_metadata_parses_pdf_slide_and_video_links() -> None:
    service = PaperLookupService()
    html = """
    <html>
      <body>
        <h1>Who Is Trying to Access My Account? Exploring User Perceptions and Reactions to Risk-Based Authentication Notifications</h1>
        <a href="/wp-content/uploads/2025-133-paper.pdf">Paper</a>
        <a href="/wp-content/uploads/8D-f0133-Wei.pdf">Slides</a>
        <a href="https://youtu.be/4pgLGpIcXfg">Video</a>
      </body>
    </html>
    """

    result = service._extract_ndss_page_metadata(  # pyright: ignore[reportPrivateUsage]
        html,
        url="https://www.ndss-symposium.org/ndss-paper/example-paper/",
        title="Who Is Trying to Access My Account? Exploring User Perceptions and Reactions to Risk-Based Authentication Notifications",
        venue="NDSS Symposium",
        year=2025,
    )

    assert result.pdf_url == "https://www.ndss-symposium.org/wp-content/uploads/2025-133-paper.pdf"
    assert result.slide_url == "https://www.ndss-symposium.org/wp-content/uploads/8D-f0133-Wei.pdf"
    assert result.video_url == "https://youtu.be/4pgLGpIcXfg"
    assert result.venue == "NDSS Symposium"


def test_extract_usenix_page_metadata_parses_pdf_prepub_slide_and_embedded_video() -> None:
    service = PaperLookupService()
    html = """
    <html>
      <body>
        <h1>Sample USENIX Paper</h1>
        <a href="/system/files/usenixsecurity24-sample.pdf">PDF</a>
        <a href="/system/files/sec24fall-prepub-sample.pdf">Prepublication PDF</a>
        <a href="/system/files/usenixsecurity24_slides-sample.pdf">Slides</a>
        <iframe src="//www.youtube.com/embed/7qCpygabkP0"></iframe>
      </body>
    </html>
    """

    result = service._extract_usenix_page_metadata(  # pyright: ignore[reportPrivateUsage]
        html,
        url="https://www.usenix.org/conference/usenixsecurity24/presentation/sample",
        title="Sample USENIX Paper",
        venue="USENIX Security",
        year=2024,
    )

    assert result.pdf_url == "https://www.usenix.org/system/files/usenixsecurity24-sample.pdf"
    assert result.preprint_pdf_url == "https://www.usenix.org/system/files/sec24fall-prepub-sample.pdf"
    assert result.slide_url == "https://www.usenix.org/system/files/usenixsecurity24_slides-sample.pdf"
    assert result.video_url == "https://www.youtube.com/embed/7qCpygabkP0"


def test_score_candidate_penalizes_artifact_evaluation_noise() -> None:
    service = PaperLookupService()

    exact_score = service._score_candidate(  # pyright: ignore[reportPrivateUsage]
        "zksl verifiable and efficient split federated learning via asynchronous zero knowledge proofs",
        "zksl verifiable and efficient split federated learning via asynchronous zero knowledge proofs",
        year=2025,
        expected_year=2025,
        venue=None,
        expected_venue=None,
    )
    artifact_score = service._score_candidate(  # pyright: ignore[reportPrivateUsage]
        "zksl verifiable and efficient split federated learning via asynchronous zero knowledge proofs",
        "artifact evaluation of zksl verifiable and efficient split federated learning via asynchronous zero knowledge proofs",
        year=2025,
        expected_year=2025,
        venue=None,
        expected_venue=None,
    )

    assert exact_score > artifact_score
    assert artifact_score < 0.82
