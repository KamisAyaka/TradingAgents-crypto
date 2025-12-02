import hashlib
import logging
import random
from math import sqrt

try:
    import chromadb
    from chromadb.config import Settings

    _CHROMA_AVAILABLE = True
    _CHROMA_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - best effort fallback
    chromadb = None
    Settings = None
    _CHROMA_AVAILABLE = False
    _CHROMA_IMPORT_ERROR = exc

from openai import OpenAI
from openai import OpenAIError


logger = logging.getLogger(__name__)


class _SimpleMemoryCollection:
    """Minimal in-memory replacement for a Chroma collection."""

    def __init__(self, name):
        self.name = name
        self._documents = []
        self._metadatas = []
        self._embeddings = []

    def count(self):
        return len(self._documents)

    def add(self, documents, metadatas, embeddings, ids):  # ids kept for parity
        self._documents.extend(documents)
        self._metadatas.extend(metadatas)
        self._embeddings.extend(embeddings)

    def _cosine_distance(self, a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sqrt(sum(x * x for x in a))
        norm_b = sqrt(sum(x * x for x in b))
        if not norm_a or not norm_b:
            return 1.0
        return 1 - (dot / (norm_a * norm_b))

    def query(self, query_embeddings, n_results, include):
        if not self._documents:
            return {key: [[]] for key in include}

        query_emb = query_embeddings[0]
        scored = [
            (self._cosine_distance(query_emb, emb), idx)
            for idx, emb in enumerate(self._embeddings)
        ]
        scored.sort(key=lambda item: item[0])
        top = scored[:n_results]

        result = {key: [[]] for key in include}
        for distance, idx in top:
            if "documents" in include:
                result.setdefault("documents", [[]])[0].append(self._documents[idx])
            if "metadatas" in include:
                result.setdefault("metadatas", [[]])[0].append(self._metadatas[idx])
            if "distances" in include:
                result.setdefault("distances", [[]])[0].append(distance)
        return result


class FinancialSituationMemory:
    def __init__(self, name, config):
        if config["backend_url"] == "http://localhost:11434/v1":
            self.embedding = "nomic-embed-text"
        else:
            self.embedding = "text-embedding-3-small"
        try:
            self.client = OpenAI(base_url=config["backend_url"])
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("无法初始化远程 embedding 客户端，改用本地降级方案: %s", exc)
            self.client = None
        self.situation_collection = None
        self.chroma_client = None
        self._fallback_dim = 256
        self._remote_embeddings_enabled = self.client is not None

        if _CHROMA_AVAILABLE:
            try:
                self.chroma_client = chromadb.Client(
                    Settings(allow_reset=True, chroma_api_impl="chromadb.api.fastapi.FastAPI")
                )
                self.situation_collection = self.chroma_client.create_collection(name=name)
            except Exception as exc:
                logger.warning("Falling back to simple in-memory collection due to Chroma error: %s", exc)

        if self.situation_collection is None:
            if _CHROMA_IMPORT_ERROR:
                logger.warning(
                    "Chroma import failed (%s). Using simple in-memory memory store instead.",
                    _CHROMA_IMPORT_ERROR,
                )
            self.situation_collection = _SimpleMemoryCollection(name)

    def get_embedding(self, text):
        """Get OpenAI embedding for a text"""
        if self._remote_embeddings_enabled and self.client is not None:
            try:
                response = self.client.embeddings.create(
                    model=self.embedding, input=text
                )
                return response.data[0].embedding
            except OpenAIError as exc:
                logger.warning(
                    "远程 embedding 失败 (%s)，自动降级为本地 hash 向量。", exc
                )
                self._remote_embeddings_enabled = False
            except Exception as exc:  # pragma: no cover - network/runtime issues
                logger.warning(
                    "调用 embedding 服务异常 (%s)，将使用本地降级方案。",
                    exc,
                )
                self._remote_embeddings_enabled = False

        return self._fallback_embedding(text)

    def _fallback_embedding(self, text: str):
        """Deterministic hash-based embedding to avoid external quotas."""
        vector = [0.0] * self._fallback_dim
        tokens = [tok for tok in text.lower().split() if tok]
        if not tokens:
            return vector

        for token in tokens:
            seed = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            rng = random.Random(seed)
            weight = 1.0
            for idx in range(self._fallback_dim):
                vector[idx] += weight * (rng.random() * 2 - 1)

        norm = sqrt(sum(val * val for val in vector))
        if norm:
            vector = [val / norm for val in vector]
        return vector

    def add_situations(self, situations_and_advice):
        """Add financial situations and their corresponding advice. Parameter is a list of tuples (situation, rec)"""

        situations = []
        advice = []
        ids = []
        embeddings = []

        offset = self.situation_collection.count()

        for i, (situation, recommendation) in enumerate(situations_and_advice):
            situations.append(situation)
            advice.append(recommendation)
            ids.append(str(offset + i))
            embeddings.append(self.get_embedding(situation))

        self.situation_collection.add(
            documents=situations,
            metadatas=[{"recommendation": rec} for rec in advice],
            embeddings=embeddings,
            ids=ids,
        )

    def get_memories(self, current_situation, n_matches=1):
        """Find matching recommendations using OpenAI embeddings"""
        query_embedding = self.get_embedding(current_situation)

        results = self.situation_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_matches,
            include=["metadatas", "documents", "distances"],
        )

        matched_results = []
        for i in range(len(results["documents"][0])):
            matched_results.append(
                {
                    "matched_situation": results["documents"][0][i],
                    "recommendation": results["metadatas"][0][i]["recommendation"],
                    "similarity_score": 1 - results["distances"][0][i],
                }
            )

        return matched_results


if __name__ == "__main__":
    # Example usage
    matcher = FinancialSituationMemory()

    # Example data
    example_data = [
        (
            "High inflation rate with rising interest rates and declining consumer spending",
            "Consider defensive sectors like consumer staples and utilities. Review fixed-income portfolio duration.",
        ),
        (
            "Tech sector showing high volatility with increasing institutional selling pressure",
            "Reduce exposure to high-growth tech stocks. Look for value opportunities in established tech companies with strong cash flows.",
        ),
        (
            "Strong dollar affecting emerging markets with increasing forex volatility",
            "Hedge currency exposure in international positions. Consider reducing allocation to emerging market debt.",
        ),
        (
            "Market showing signs of sector rotation with rising yields",
            "Rebalance portfolio to maintain target allocations. Consider increasing exposure to sectors benefiting from higher rates.",
        ),
    ]

    # Add the example situations and recommendations
    matcher.add_situations(example_data)

    # Example query
    current_situation = """
    Market showing increased volatility in tech sector, with institutional investors 
    reducing positions and rising interest rates affecting growth stock valuations
    """

    try:
        recommendations = matcher.get_memories(current_situation, n_matches=2)

        for i, rec in enumerate(recommendations, 1):
            print(f"\nMatch {i}:")
            print(f"Similarity Score: {rec['similarity_score']:.2f}")
            print(f"Matched Situation: {rec['matched_situation']}")
            print(f"Recommendation: {rec['recommendation']}")

    except Exception as e:
        print(f"Error during recommendation: {str(e)}")
