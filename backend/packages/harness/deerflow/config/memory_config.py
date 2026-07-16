"""Configuration for memory mechanism."""

from pydantic import BaseModel, Field


class MemoryConfig(BaseModel):
    """Configuration for global memory mechanism."""

    enabled: bool = Field(
        default=True,
        description="Whether to enable memory mechanism",
    )
    storage_path: str = Field(
        default="",
        description=(
            "Path to store memory data. "
            "If empty, defaults to per-user memory at `{base_dir}/users/{user_id}/memory.json`. "
            "Absolute paths are used as-is and opt out of per-user isolation "
            "(all users share the same file). "
            "Relative paths are resolved against `Paths.base_dir` "
            "(not the backend working directory). "
            "Note: if you previously set this to `.deer-flow/memory.json`, "
            "the file will now be resolved as `{base_dir}/.deer-flow/memory.json`; "
            "migrate existing data or use an absolute path to preserve the old location."
        ),
    )
    storage_class: str = Field(
        default="deerflow.agents.memory.storage.FileMemoryStorage",
        description="The class path for memory storage provider",
    )
    debounce_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Seconds to wait before processing queued updates (debounce)",
    )
    model_name: str | None = Field(
        default=None,
        description="Model name to use for memory updates (None = use default model)",
    )
    max_facts: int = Field(
        default=100,
        ge=10,
        le=500,
        description="Maximum number of facts to store",
    )
    fact_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for storing facts",
    )
    injection_enabled: bool = Field(
        default=True,
        description="Whether to inject memory into system prompt",
    )
    max_injection_tokens: int = Field(
        default=2000,
        ge=100,
        le=8000,
        description="Maximum tokens to use for memory injection",
    )
    shutdown_flush_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Bounded graceful-shutdown drain of the in-memory update queue (seconds). "
        "On shutdown the gateway drains pending memory updates within this budget so they "
        "are not lost on restart / rolling deploy / SIGTERM (upstream #4181). Must fit inside "
        "the pod termination grace period when deployed under Kubernetes.",
    )
    # ── Staleness review (upstream #3860) ───────────────────────────────
    staleness_review_enabled: bool = Field(
        default=True,
        description="Enable staleness review for aged facts. Facts older than staleness_age_days are surfaced in the "
        "memory-update prompt so the LLM can semantically judge whether each is still valid or should be removed. "
        "Solves 'silent staleness' where outdated facts persist because no future conversation explicitly contradicts them.",
    )
    staleness_age_days: int = Field(
        default=90,
        ge=30,
        le=365,
        description="Facts older than this many days become staleness-review candidates. 90 (~one quarter) balances catching genuine changes vs noise on stable facts.",
    )
    staleness_min_candidates: int = Field(
        default=3,
        ge=1,
        le=50,
        description="Minimum stale facts required to trigger a review cycle (below this the prompt overhead is not justified).",
    )
    staleness_max_removals_per_cycle: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum facts the staleness review can remove in one update cycle. Prevents over-pruning a large backlog.",
    )
    staleness_protected_categories: list[str] = Field(
        default_factory=lambda: ["correction"],
        description="Fact categories exempt from staleness review (e.g. correction = explicit user feedback, not auto-pruned by age).",
    )


# Global configuration instance
_memory_config: MemoryConfig = MemoryConfig()


def get_memory_config() -> MemoryConfig:
    """Get the current memory configuration."""
    return _memory_config


def set_memory_config(config: MemoryConfig) -> None:
    """Set the memory configuration."""
    global _memory_config
    _memory_config = config


def load_memory_config_from_dict(config_dict: dict) -> None:
    """Load memory configuration from a dictionary."""
    global _memory_config
    _memory_config = MemoryConfig(**config_dict)
