import hashlib
import logging
import os
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
    """简单的内存向量库，实现 Chroma 集合的最小替代品。"""

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
        dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
        dashscope_base_url = os.getenv(
            "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        dashscope_model = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")

        if not dashscope_api_key:
            raise RuntimeError(
                "未检测到 DASHSCOPE_API_KEY。请参考 https://help.aliyun.com/zh/model-studio/embedding "
                "配置阿里云百炼的 embedding Key 后再运行。"
            )

        self.embedding = dashscope_model
        try:
                self.client = OpenAI(
                    api_key=dashscope_api_key,
                    base_url=dashscope_base_url,
                )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("无法初始化阿里云 embedding 客户端，将使用本地降级方案: %s", exc)
            self.client = None

        self.situation_collection = None
        self.chroma_client = None
        self._fallback_dim = 256
        self._remote_embeddings_enabled = self.client is not None
        self._max_remote_input_len = 8192

        use_chroma = config.get("use_chroma_memory", True)
        chroma_path = config.get("chroma_path") or os.path.join(
            config.get("project_dir", os.getcwd()), "data", "chroma_store"
        )

        if use_chroma and _CHROMA_AVAILABLE:
            try:
                os.makedirs(chroma_path, exist_ok=True)
                self.chroma_client = chromadb.PersistentClient(
                    path=chroma_path,
                    settings=Settings(allow_reset=True),
                )
                self.situation_collection = self.chroma_client.get_or_create_collection(
                    name=name
                )
            except Exception as exc:
                logger.warning("Chroma 初始化失败，自动使用内存向量库: %s", exc)
        elif use_chroma and not _CHROMA_AVAILABLE:
            logger.warning("检测到 use_chroma_memory=True，但本地未安装 chromadb，自动使用内存向量库。")

        if self.situation_collection is None:
            if _CHROMA_IMPORT_ERROR:
                logger.warning(
                    "Chroma import failed (%s). Using simple in-memory memory store instead.",
                    _CHROMA_IMPORT_ERROR,
                )
            self.situation_collection = _SimpleMemoryCollection(name)

    def get_embedding(self, text):
        """获取文本的 embedding，用远程服务失败时自动降级为本地 hash 向量。"""
        clean_text = (text or "").strip()
        if not clean_text:
            clean_text = "空上下文，无可供嵌入的有效内容。"
        elif len(clean_text) > self._max_remote_input_len:
            logger.warning(
                "嵌入文本长度超出 %d 字符，已自动截断以适配 DashScope 限制。",
                self._max_remote_input_len,
            )
            clean_text = clean_text[: self._max_remote_input_len]

        if self._remote_embeddings_enabled and self.client is not None:
            try:
                response = self.client.embeddings.create(
                    model=self.embedding, input=clean_text
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

        return self._fallback_embedding(clean_text)

    def _fallback_embedding(self, text: str):
        """使用确定性的 hash 方法生成向量，避免依赖外部额度。"""
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
        """新增情景与建议。参数为 [(situation, recommendation), ...] 列表。"""

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
        """根据当前情景查找最相似的历史建议。"""
        query_embedding = self.get_embedding(current_situation)

        results = self.situation_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_matches,
            include=["metadatas", "documents", "distances"],
        )

        matched_results = []
        documents = results.get("documents") or [[]]
        metadatas = results.get("metadatas") or [[]]
        distances = results.get("distances") or [[]]

        if not documents or not documents[0]:
            return matched_results

        count = min(len(documents[0]), len(metadatas[0]), len(distances[0]))

        for i in range(count):
            matched_results.append(
                {
                    "matched_situation": documents[0][i],
                    "recommendation": metadatas[0][i]["recommendation"],
                    "similarity_score": 1 - distances[0][i],
                }
            )

        return matched_results


if __name__ == "__main__":
    # 使用示例
    matcher = FinancialSituationMemory("demo_memory", {"backend_url": None})

    # 示例情景与建议
    example_data = [
        (
            "通胀高企、利率上行、消费支出走弱",
            "优先考虑防御型板块，例如必选消费与公用事业，同时回顾固收久期配置。",
        ),
        (
            "科技板块波动剧烈，机构抛售压力上升",
            "降低高成长科技敞口，寻找现金流稳健的成熟科技公司价值机会。",
        ),
        (
            "美元走强冲击新兴市场，外汇波动上升",
            "对海外仓位做汇率对冲，适度下调新兴市场债券配置。",
        ),
        (
            "收益率走高引发板块轮动迹象",
            "重新平衡组合，增配受益于高利率环境的行业。",
        ),
    ]

    matcher.add_situations(example_data)

    current_situation = """
    科技板块波动扩大，机构投资者持续减仓，利率上行侵蚀成长股估值
    """

    try:
        recommendations = matcher.get_memories(current_situation, n_matches=2)

        for i, rec in enumerate(recommendations, 1):
            print(f"\n匹配案例 {i}:")
            print(f"相似度: {rec['similarity_score']:.2f}")
            print(f"匹配情境: {rec['matched_situation']}")
            print(f"建议: {rec['recommendation']}")

    except Exception as e:
        print(f"推荐时出现错误: {str(e)}")
