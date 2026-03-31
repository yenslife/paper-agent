from paper_agent.services.abstract_fetcher import AbstractFetcher
from paper_agent.services.chat import ChatService
from paper_agent.services.embeddings import EmbeddingService
from paper_agent.services.ingestion import IngestionService
from paper_agent.services.markdown_parser import MarkdownParser
from paper_agent.services.retrieval import RetrievalService

embedding_service = EmbeddingService()
abstract_fetcher = AbstractFetcher()
retrieval_service = RetrievalService(embedding_service)
markdown_parser = MarkdownParser()
ingestion_service = IngestionService(abstract_fetcher, embedding_service, markdown_parser=markdown_parser)
chat_service = ChatService(retrieval_service, ingestion_service)
