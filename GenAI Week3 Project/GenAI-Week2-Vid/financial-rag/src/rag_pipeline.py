"""End-to-end RAG pipeline: retrieve -> (rerank) -> generate.

Ties the components together behind a single ``RAGPipeline`` class and an
``answer()`` method that returns both the generated answer and the supporting
chunks, so the UI and the evaluation harness consume identical objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI

from src.config import SETTINGS, require_api_key
from src.retrieval import RetrievedChunk, retrieve
from src.reranker import rerank
from src.vector_store import load_index

PROMPT_TEMPLATE = """You are a financial document analyst.

Use only the provided context to answer the question.

If the answer is not contained in the context, say:

"Information not found in provided documents."

Context:
{context}

Question:
{question}

Answer:"""

NOT_FOUND = "Information not found in provided documents."


@dataclass
class RAGResult:
    question: str
    answer: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    method: str = "fixed"
    reranked: bool = False

    @property
    def contexts(self) -> list[str]:
        """Plain context strings — the shape RAGAS expects."""
        return [c.text for c in self.chunks]


def _format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, c in enumerate(chunks, 1):
        blocks.append(f"[{i}] Source: {c.source}\n{c.text}")
    return "\n\n".join(blocks)


class RAGPipeline:
    """Reusable pipeline bound to one chunking strategy / FAISS index."""

    def __init__(self, method: str = "fixed", use_reranker: bool = False):
        self.method = method
        self.use_reranker = use_reranker
        self.store = load_index(method)
        require_api_key()
        self.llm = ChatOpenAI(model=SETTINGS.llm_model, temperature=0.0)

    def _select_chunks(self, question: str) -> list[RetrievedChunk]:
        candidates = retrieve(self.store, question, k=SETTINGS.retrieval.top_k)
        if self.use_reranker:
            return rerank(question, candidates, top_n=SETTINGS.retrieval.rerank_top_n)
        # Without reranking we still trim to the same final-k for a fair comparison.
        return candidates[: SETTINGS.retrieval.rerank_top_n]

    def answer(self, question: str) -> RAGResult:
        chunks = self._select_chunks(question)
        if not chunks:
            return RAGResult(question, NOT_FOUND, [], self.method, self.use_reranker)

        prompt = PROMPT_TEMPLATE.format(
            context=_format_context(chunks), question=question
        )
        response = self.llm.invoke(prompt)
        answer = response.content.strip()
        return RAGResult(question, answer, chunks, self.method, self.use_reranker)


def build_pipeline(method: str = "fixed", use_reranker: bool = False) -> RAGPipeline:
    """Factory used by the app and experiment runner."""
    return RAGPipeline(method=method, use_reranker=use_reranker)
