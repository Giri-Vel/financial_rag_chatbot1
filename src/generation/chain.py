"""
RegulatorAI - RAG Chain
=========================
The core pipeline: takes a user question, retrieves relevant regulatory
document chunks, and generates a cited answer using an LLM.

Usage:
    from src.generation.chain import RAGChain
    rag = RAGChain()
    response = rag.query("What are the KYC norms for V-CIP?")
    print(response["answer"])
    print(response["sources"])
"""

from langchain_openai import ChatOpenAI
from loguru import logger

from src.config import settings, SYSTEM_PROMPT, QUERY_PROMPT
from src.retrieval.vector_store import VectorStore


class RAGChain:
    """RAG pipeline: retrieve → format context → generate answer."""

    def __init__(self, premium: bool = False):
        """
        Initialize the RAG chain.

        Args:
            premium: If True, use the premium LLM model (gpt-4o) for complex queries
        """
        model = settings.LLM_MODEL_PREMIUM if premium else settings.LLM_MODEL

        self.llm = ChatOpenAI(
            model=model,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            openai_api_key=settings.OPENAI_API_KEY,
        )
        self.vector_store = VectorStore()
        self.model_name = model

        logger.info(f"RAGChain initialized with model: {model}")

    def query(
        self,
        question: str,
        top_k: int = settings.TOP_K_RETRIEVAL,
        topic: str | None = None,
        regulator: str | None = None,
    ) -> dict:
        """
        Answer a question using RAG.

        Args:
            question: User's question
            top_k: Number of chunks to retrieve
            topic: Optional filter by topic
            regulator: Optional filter by regulator

        Returns:
            {
                "answer": "The KYC norms require...",
                "sources": [
                    {"title": "...", "section": "...", "date": "...", "similarity": 0.65},
                    ...
                ],
                "context_used": 5,
                "model": "gpt-4o-mini",
            }
        """
        # Step 1: Retrieve relevant chunks
        logger.info(f"Query: '{question[:80]}...' | top_k={top_k}, topic={topic}")

        results = self.vector_store.search(
            query=question,
            top_k=top_k,
            topic=topic,
            regulator=regulator,
        )

        if not results:
            return {
                "answer": (
                    "I couldn't find relevant information in the regulatory documents "
                    "to answer this question. Try rephrasing your query or broadening "
                    "the topic filter."
                ),
                "sources": [],
                "context_used": 0,
                "model": self.model_name,
            }

        # Step 2: Format context from retrieved chunks
        context = self._format_context(results)

        # Step 3: Build the prompt
        system_message = SYSTEM_PROMPT.format(context=context)
        user_message = QUERY_PROMPT.format(question=question)

        # Step 4: Generate answer
        try:
            response = self.llm.invoke([
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ])
            answer = response.content
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return {
                "answer": f"Error generating response: {str(e)}",
                "sources": [],
                "context_used": len(results),
                "model": self.model_name,
            }

        # Step 5: Format sources
        sources = self._format_sources(results)

        logger.info(
            f"Generated answer: {len(answer)} chars, "
            f"{len(sources)} sources cited"
        )

        return {
            "answer": answer,
            "sources": sources,
            "context_used": len(results),
            "model": self.model_name,
        }

    def _format_context(self, results: list[dict]) -> str:
        """Format retrieved chunks into a context string for the LLM."""
        context_parts = []

        for i, result in enumerate(results, 1):
            meta = result["metadata"]
            text = result["text"]
            similarity = result["similarity"]

            context_parts.append(
                f"[Document {i}]\n"
                f"Title: {meta['title']}\n"
                f"Section: {meta['section_title']}\n"
                f"Regulator: {meta['regulator']}\n"
                f"Date: {meta['date']}\n"
                f"Type: {meta['doc_type']}\n"
                f"Relevance: {similarity:.2f}\n"
                f"Content:\n{text}\n"
            )

        return "\n---\n".join(context_parts)

    def _format_sources(self, results: list[dict]) -> list[dict]:
        """Extract clean source references from results."""
        seen = set()
        sources = []

        for result in results:
            meta = result["metadata"]
            # Deduplicate by document + section
            key = f"{meta['doc_id']}|{meta['section_title']}"
            if key in seen:
                continue
            seen.add(key)

            sources.append({
                "title": meta["title"],
                "section": meta["section_title"],
                "regulator": meta["regulator"],
                "topic": meta["topic"],
                "date": meta["date"],
                "doc_type": meta["doc_type"],
                "similarity": result["similarity"],
            })

        return sources


# ── Interactive CLI ────────────────────────────────────

def interactive_cli():
    """Run an interactive Q&A session in the terminal."""
    print("\n" + "=" * 60)
    print("  RegulatorAI — RBI/SEBI Regulatory Assistant")
    print("  Type your question, or 'quit' to exit")
    print("  Prefix with 'topic:kyc_aml' to filter by topic")
    print("=" * 60 + "\n")

    rag = RAGChain()

    while True:
        try:
            user_input = input("\n📋 Your question: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input or user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        # Parse optional topic filter
        topic = None
        question = user_input
        if user_input.startswith("topic:"):
            parts = user_input.split(" ", 1)
            topic = parts[0].replace("topic:", "")
            question = parts[1] if len(parts) > 1 else ""
            if not question:
                print("Please provide a question after the topic filter.")
                continue

        # Query
        result = rag.query(question, topic=topic)

        # Display answer
        print(f"\n{'─' * 60}")
        print(f"🤖 Answer:\n")
        print(result["answer"])

        # Display sources
        if result["sources"]:
            print(f"\n{'─' * 60}")
            print(f"📚 Sources ({len(result['sources'])} documents):\n")
            for i, src in enumerate(result["sources"], 1):
                print(
                    f"  {i}. [{src['regulator']}] {src['title']}\n"
                    f"     Section: {src['section']}\n"
                    f"     Date: {src['date']} | Relevance: {src['similarity']:.2f}"
                )

        print(f"\n  Model: {result['model']} | Chunks used: {result['context_used']}")


if __name__ == "__main__":
    interactive_cli()