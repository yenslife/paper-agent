from paper_agent.services.paper_lookup import PaperLookupService
import pytest


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


def test_extract_ieee_page_metadata_builds_stamp_pdf_url() -> None:
    service = PaperLookupService()
    html = """
    <html>
      <head>
        <title>Practical Full-Stack Memory Deduplication Attacks in Sandboxed JavaScript | IEEE Conference Publication</title>
        <meta name="description" content="A practical memory-deduplication attack in sandboxed JavaScript." />
        <meta name="citation_doi" content="10.1109/SP61157.2025.00139" />
      </head>
      <body></body>
    </html>
    """

    result = service._extract_ieee_page_metadata(  # pyright: ignore[reportPrivateUsage]
        html,
        url="https://ieeexplore.ieee.org/document/11023476",
        title="Practical Full-Stack Memory Deduplication Attacks in Sandboxed JavaScript",
        venue="IEEE Symposium on Security and Privacy",
        year=2025,
    )

    assert result.pdf_url == "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=11023476"
    assert result.doi == "10.1109/SP61157.2025.00139"
    assert result.abstract == "A practical memory-deduplication attack in sandboxed JavaScript."


def test_extract_acm_page_metadata_builds_pdf_url_from_doi() -> None:
    service = PaperLookupService()
    html = """
    <html>
      <body>
        <h1>Sample ACM Paper</h1>
        <meta name="citation_abstract" content="This is an ACM abstract." />
      </body>
    </html>
    """

    result = service._extract_acm_page_metadata(  # pyright: ignore[reportPrivateUsage]
        html,
        url="https://dl.acm.org/doi/10.1145/3719027.3744836",
        title="Sample ACM Paper",
        venue="ACM CCS",
        year=2025,
    )

    assert result.pdf_url == "https://dl.acm.org/doi/pdf/10.1145/3719027.3744836"
    assert result.doi == "10.1145/3719027.3744836"
    assert result.abstract == "This is an ACM abstract."


def test_extract_arxiv_page_metadata_builds_pdf_url_and_abstract() -> None:
    service = PaperLookupService()
    html = """
    <html>
      <head>
        <meta name="citation_title" content="Sample arXiv Paper" />
      </head>
      <body>
        <blockquote class="abstract">
          Abstract: This is an arXiv abstract.
        </blockquote>
      </body>
    </html>
    """

    result = service._extract_arxiv_page_metadata(  # pyright: ignore[reportPrivateUsage]
        html,
        url="https://arxiv.org/abs/2501.00001",
        title="Sample arXiv Paper",
        venue=None,
        year=2025,
    )

    assert result.pdf_url == "https://arxiv.org/pdf/2501.00001.pdf"
    assert result.abstract == "This is an arXiv abstract."
    assert result.venue == "arXiv"


@pytest.mark.asyncio
async def test_lookup_paper_enriches_openalex_fallback_with_acm_pdf_and_inputs() -> None:
    service = PaperLookupService()

    async def fake_page_lookup(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    async def fake_semantic_lookup(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    async def fake_openalex_lookup(*args, **kwargs):  # type: ignore[no-untyped-def]
        return service._pick_openalex_match(  # pyright: ignore[reportPrivateUsage]
            [
                {
                    "display_name": "SecAlign: Defending Against Prompt Injection with Preference Optimization",
                    "publication_year": 2025,
                    "ids": {
                        "doi": "https://doi.org/10.1145/3719027.3744836",
                        "openalex": "https://openalex.org/W4416549384",
                    },
                    "primary_location": {
                        "landing_page_url": "https://doi.org/10.1145/3719027.3744836",
                    },
                    "best_oa_location": {},
                    "abstract_inverted_index": None,
                }
            ],
            title="SecAlign: Defending Against Prompt Injection with Preference Optimization",
            venue="ACM CCS",
            year=2025,
        )

    service._lookup_from_known_page = fake_page_lookup  # type: ignore[method-assign]
    service._lookup_via_semantic_scholar = fake_semantic_lookup  # type: ignore[method-assign]
    service._lookup_via_openalex = fake_openalex_lookup  # type: ignore[method-assign]

    result = await service.lookup_paper(
        title="SecAlign: Defending Against Prompt Injection with Preference Optimization",
        paper_url="https://dl.acm.org/doi/10.1145/3719027.3744836",
        source_page_url="https://www.sigsac.org/ccs/CCS2025/accepted-papers/",
        venue="ACM CCS",
        year=2025,
    )

    assert result is not None
    assert result.provider == "openalex"
    assert result.pdf_url == "https://dl.acm.org/doi/pdf/10.1145/3719027.3744836"
    assert result.venue == "ACM CCS"
    assert result.source_page_url == "https://www.sigsac.org/ccs/CCS2025/accepted-papers/"
    assert result.year == 2025
