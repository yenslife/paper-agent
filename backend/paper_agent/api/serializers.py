from paper_agent.models import Paper
from paper_agent.schemas import PaperRead


def to_paper_read(paper: Paper) -> PaperRead:
    return PaperRead(
        id=paper.id,
        title=paper.title,
        url=paper.url,
        conference_id=paper.conference_id,
        conference_name=paper.conference.name if paper.conference else None,
        source_page_url=paper.source_page_url,
        venue=paper.venue,
        year=paper.year,
        abstract=paper.abstract,
        ingest_status=paper.ingest_status.value,
    )
