from paper_agent.services.abstract_fetcher import AbstractFetcher
from paper_agent.services.browser_use_service import BrowserUseService
from paper_agent.services.chat import ChatService
from paper_agent.services.embeddings import EmbeddingService
from paper_agent.services.ingestion import IngestionService
from paper_agent.services.markdown_parser import MarkdownParser
from paper_agent.services.paper_lookup import PaperLookupService
from paper_agent.services.pdf_markdown import PdfMarkdownService
from paper_agent.services.retrieval import RetrievalService

embedding_service = EmbeddingService()
abstract_fetcher = AbstractFetcher()
paper_lookup_service = PaperLookupService(abstract_fetcher)
pdf_markdown_service = PdfMarkdownService(paper_lookup_service)
browser_use_service = BrowserUseService()
retrieval_service = RetrievalService(embedding_service)
markdown_parser = MarkdownParser()
ingestion_service = IngestionService(abstract_fetcher, embedding_service, markdown_parser=markdown_parser)
chat_service = ChatService(
    retrieval_service,
    ingestion_service,
    paper_lookup_service,
    pdf_markdown_service,
    browser_use_service,
)
