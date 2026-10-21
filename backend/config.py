"""配置：全部走 .env，前缀 TPA_，共 19 项。

必填项缺失时**启动即报错退出**（见 BACKEND.md 第 5 章）。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """19 项配置，前缀 TPA_。"""

    model_config = SettingsConfigDict(
        env_prefix="TPA_",
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用 ----
    env: str = "dev"
    port: int = 8000
    data_dir: str = "./data"

    # ---- 安全 ----
    jwt_secret: str = Field(..., min_length=32)
    jwt_expire_hours: int = 12
    root_username: str = "root"
    root_password: str = Field(..., min_length=8)
    allow_register: bool = True

    # ---- 模型 ----
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = Field(...)
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.3

    # ---- 高德 ----
    amap_key: str = Field(...)
    amap_timeout: int = 8

    # ---- RAG ----
    rag_enabled: bool = True
    # 嵌入（把文本变成向量）有两种后端：
    #   api   —— 调 OpenAI 兼容的 POST {base_url}/embeddings（默认，只要 httpx）
    #   local —— 本地 sentence-transformers 跑 BAAI/bge-m3（需 torch + 2.3 GB 权重）
    rag_embedding_provider: Literal["api", "local"] = "api"
    rag_embedding_model: str = "BAAI/bge-m3"
    rag_embedding_base_url: str = "https://api.siliconflow.cn/v1"
    rag_embedding_api_key: str = ""
    rag_embedding_dim: int = 1024
    rag_chunk_size: int = 800
    rag_top_k: int = 5

    # ---- Agent ----
    agent_max_iterations: int = 8

    @field_validator("llm_model")
    @classmethod
    def _reject_reasoner(cls, v: str) -> str:
        """deepseek-reasoner 不支持 function calling，而本项目核心就是工具调用。"""
        if "reasoner" in v.lower():
            raise ValueError(
                "TPA_LLM_MODEL 不可使用 deepseek-reasoner：它不支持 function calling。"
                "请使用 deepseek-chat。"
            )
        return v

    @field_validator("env")
    @classmethod
    def _norm_env(cls, v: str) -> str:
        return (v or "dev").strip().lower()

    # ---- 派生路径 ----
    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        if not p.is_absolute():
            p = (BASE_DIR / p).resolve()
        return p

    @property
    def uploads_dir(self) -> Path:
        return self.data_path / "uploads"

    @property
    def chroma_dir(self) -> Path:
        return self.data_path / "chroma"

    @property
    def db_path(self) -> Path:
        return self.data_path / "app.db"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path.as_posix()}"

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    # ---- 嵌入后端 ----
    @property
    def embedding_is_api(self) -> bool:
        return self.rag_embedding_provider == "api"

    @property
    def embedding_configured(self) -> bool:
        """能不能向量化。api 模式缺 key 时**不阻止启动**，只在用到时明确报错。

        理由：缺 key 只影响知识库，不该让登录/对话这些核心功能一起起不来。
        """
        if not self.rag_enabled:
            return False
        if self.embedding_is_api:
            return bool(self.rag_embedding_api_key.strip())
        return True

    def ensure_dirs(self) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        if self.rag_enabled:
            self.chroma_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except Exception as exc:
        raise RuntimeError(
            "配置校验失败，请检查 .env（参考 .env.example）。缺项/非法项：" + _summarize(exc)
        ) from exc


def _summarize(exc: Exception) -> str:
    """把 pydantic 的长报错压成一行，方便启动时一眼看到。"""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        lines = []
        for item in errors():
            loc = ".".join(str(p) for p in item.get("loc", ())) or "?"
            lines.append(f"TPA_{loc.upper()}: {item.get('msg', '')}")
        if lines:
            return "；".join(lines)
    return str(exc).splitlines()[0] if str(exc) else "未知"


settings = get_settings()
