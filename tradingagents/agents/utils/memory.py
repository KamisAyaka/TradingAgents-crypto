import hashlib
import logging
import os
import random
from math import sqrt
from typing import Any, Dict, cast, List, Literal
from dotenv import load_dotenv

try:
    import chromadb
    from chromadb.config import Settings
except Exception as exc:  # pragma: no cover - hard fail
    chromadb = None
    Settings = None
    _CHROMA_IMPORT_ERROR = exc

from openai import OpenAI
from openai import OpenAIError


logger = logging.getLogger(__name__)


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

        self.situation_collection: Any = None
        self.chroma_client: Any = None
        self._fallback_dim = 256
        self._remote_embeddings_enabled = self.client is not None
        self._max_remote_input_len = 8192

        use_chroma = config.get("use_chroma_memory", True)
        chroma_path = config.get("chroma_path") or os.path.join(
            config.get("project_dir", os.getcwd()), "data", "chroma_store"
        )
        if not use_chroma:
            raise RuntimeError("use_chroma_memory=False 当前已不支持内存向量库降级。")
        if chromadb is None or Settings is None:
            raise RuntimeError(
                f"Chroma 未安装或导入失败: {_CHROMA_IMPORT_ERROR}. 请安装 chromadb。"
            )
        os.makedirs(chroma_path, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(
            path=chroma_path,
            settings=Settings(allow_reset=True),
        )
        self.situation_collection = self.chroma_client.get_or_create_collection(
            name=name
        )
        if self.situation_collection is None:
            raise RuntimeError("Chroma collection 初始化失败。")

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

    def add_situations(self, situations_and_advice, metadata_list=None):
        """新增情景与建议。参数为 [(situation, recommendation), ...] 列表。"""

        situations = []
        advice = []
        ids = []
        embeddings = []

        collection = cast(Any, self.situation_collection)
        offset = collection.count()

        for i, (situation, recommendation) in enumerate(situations_and_advice):
            situations.append(situation)
            advice.append(recommendation)
            ids.append(str(offset + i))
            embeddings.append(self.get_embedding(situation))

        metadatas = []
        for idx, rec in enumerate(advice):
            base_meta = {"recommendation": rec}
            if metadata_list and idx < len(metadata_list):
                extra = metadata_list[idx] or {}
                base_meta.update(extra)
            metadatas.append(base_meta)

        collection.add(
            documents=situations,
            metadatas=metadatas,
            embeddings=embeddings,
            ids=ids,
        )

    def get_entries(self, where=None, limit=None):
        """按 metadata 过滤原始条目，返回 [{id, document, metadata}, ...]。"""
        include = ["metadatas", "documents", "ids"]
        collection = cast(Any, self.situation_collection)
        include_typed: List[Literal["metadatas", "documents", "ids"]] = [
            "metadatas",
            "documents",
            "ids",
        ]
        raw = collection.get(where=where, limit=limit, include=include_typed)
        ids = raw.get("ids") or raw.get("ids", [])
        documents = raw.get("documents") or []
        metadatas = raw.get("metadatas") or []

        entries = []
        # Chroma 返回 list 或 list of list
        if documents and isinstance(documents[0], list):
            doc_iter = documents[0]
            meta_iter = metadatas[0] if metadatas else []
            id_iter = raw.get("ids", [])[0] if ids and isinstance(ids[0], list) else ids
        else:
            doc_iter = documents
            meta_iter = metadatas
            id_iter = ids

        count = min(len(doc_iter), len(meta_iter), len(id_iter))
        for idx in range(count):
            entries.append(
                {
                    "id": id_iter[idx],
                    "document": doc_iter[idx],
                    "metadata": meta_iter[idx],
                }
            )
        return entries

    def delete_entries(self, ids=None, where=None):
        """根据 id 或 metadata 条件删除条目。"""
        delete_kwargs = {}
        if ids:
            delete_kwargs["ids"] = ids
        if where:
            delete_kwargs["where"] = where
        if not delete_kwargs:
            return
        collection = cast(Any, self.situation_collection)
        collection.delete(**delete_kwargs)

    def get_memories(self, current_situation, n_matches=1):
        """根据当前情景查找最相似的历史建议。"""
        query_embedding = self.get_embedding(current_situation)

        collection = cast(Any, self.situation_collection)
        include_query: List[Literal["metadatas", "documents", "distances"]] = [
            "metadatas",
            "documents",
            "distances",
        ]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_matches,
            include=include_query,
        )

        matched_results = []
        documents = cast(List[List[Any]], results.get("documents") or [[]])
        metadatas = cast(List[List[Dict[str, Any]]], results.get("metadatas") or [[]])
        distances = cast(List[List[float]], results.get("distances") or [[]])

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
    load_dotenv()
    # 用于 trade 复盘向量库的示例
    matcher = FinancialSituationMemory(
        "trade_memory",
        {
            "project_dir": os.getcwd(),
            "use_chroma_memory": True,
        },
    )

    example_data = [
        (
            "开仓上下文: BTC 多头，趋势转强，关键支撑 98000。\n平仓上下文: 触发止盈，波动回落。",
            '{"summary":"止盈兑现","hypothesis_check":"趋势成立","execution_review":"按计划执行",'
            '"value_assessment":"高","mistake_tags":[],"next_rules":["继续跟踪支撑位"]}',
        )
    ]

    matcher.add_situations(example_data)

    current_situation = "开仓上下文: BTC 多头，趋势转强。平仓上下文: 触发止盈。"
    recommendations = matcher.get_memories(current_situation, n_matches=1)
    for i, rec in enumerate(recommendations, 1):
        print(f"\n匹配案例 {i}:")
        print(f"相似度: {rec['similarity_score']:.2f}")
        print(f"匹配情境: {rec['matched_situation']}")
        print(f"复盘: {rec['recommendation']}")
