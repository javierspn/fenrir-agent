"""Fail-fast configuration (FR-019/020, SC-008; research R9).

Every required secret/setting must be present and non-empty at startup, else
pydantic raises a ValidationError naming the missing variable — never an
insecure default start.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="infra/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Required secrets/settings (no defaults -> missing = fail fast) ---
    DB_PASSWORD: str = Field(min_length=1)
    GRAFANA_DB_RO_PASSWORD: str = Field(min_length=1)
    GRAFANA_PASSWORD: str = Field(min_length=1)
    ANTHROPIC_API_KEY: str = Field(min_length=1)
    OLLAMA_HOST: str = Field(min_length=1)
    OWNER_TELEGRAM_CHAT_ID: str = Field(min_length=1)

    # --- Connection details (defaults match the compose stack) ---
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "fenrir_core"
    DB_USER: str = "postgres"

    # --- Cognitive-loop knobs (002; research.md R1–R11). All operator-tunable. ---
    SMALL_MODEL: str = "qwen2.5"            # owned local solver via Ollama (R1)
    EMBED_MODEL: str = "nomic-embed-text"   # 768-dim embeddings, reused (R1)
    # Frontier teacher (R2). Provider switch: anthropic (default) or deepseek (cheap math teacher,
    # OpenAI-compatible). Constitution VIII (teacher >= learner) holds for both vs qwen2.5.
    TEACHER_PROVIDER: str = "anthropic"     # anthropic | deepseek
    TEACHER_MODEL: str = "claude-opus-4-8"  # used when TEACHER_PROVIDER=anthropic
    DEEPSEEK_API_KEY: str = ""              # required only when TEACHER_PROVIDER=deepseek
    DEEPSEEK_MODEL: str = "deepseek-chat"   # or deepseek-reasoner (stronger, pricier)
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    # Daily LLM budget hard cap in USD (Constitution IX). Written into each day's
    # budget_tracking row; operator-set via .env (DeepSeek/Anthropic bill in USD).
    DAILY_BUDGET_USD: float = 2.00
    ESCALATE_CONFIDENCE: float = 0.55       # escalate when small-model conf below this (R4)
    CRYSTALLIZE_PE: float = 0.5             # crystallize only on PE >= this + verified (R5)
    CONSOLIDATION_EVERY_N_ITERS: int = 50   # cadence floor for sleep (R7)
    HELDOUT_FRACTION: float = 0.1           # predictability-gate slice, TRAINING pool only (R8)
    RETRIEVAL_SIM_FLOOR: float = 0.80       # cosine floor for "applicable" skill (R9)
    PROXY_LOCAL_SLOTS: int = 2              # local-model concurrency (R11)
    PROXY_FRONTIER_SLOTS: int = 1           # frontier concurrency (R11)
    SANDBOX_TIMEOUT: int = 10               # per-execution wall-clock seconds (R10)
    SANDBOX_IMAGE: str = "fenrir-sandbox"   # --network none verify/skill image (R10)
    LLM_PROXY_URL: str = "http://localhost:8080"  # the one egress for model calls (X)

    # --- 003 memory-consolidation-replay tunables (data-model.md §Settings) ---
    # A — value() weights (the live reward-magnitude bookmark).
    W_FAIL: float = 0.2                     # base(FAILED) — failures persist but rarely win
    W_UNVERIFIED: float = 0.1               # base(UNVERIFIED)
    W_ESCALATED: float = 1.5               # teacher-taught win is expensive → more valuable
    W_CRYSTALLIZED: float = 2.0            # yielded a reusable skill → most valuable
    # B — read-time exponential decay (increment B).
    DECAY_HALFLIFE_DAYS: float = 7.0        # untouched everyday episode loses half its weight/week
    # C — competitive replay over clusters (increment C).
    CLUSTER_SIM_FLOOR: float = 0.85         # cosine floor to group raw episodes (tighter recall)
    REPLAY_BUDGET: int = 64                # draws spent per consolidation pass
    STRENGTH_PER_REPLAY: float = 0.1       # abstraction strength accrued per replay hit
    COHERENCE_MAX_SPREAD: float = 0.25     # over-merge guard: max internal cosine distance
    EFFECTIVE_SALIENCE_FLOOR: float = 0.05  # candidate floor below which an episode is skipped

    # --- 004 feasibility-gated curriculum tunables (research.md R2/R3/R4) ---
    # Adjacency-lane pick strength: 0 = pure feasibility filter (uniform among the adjacent
    # band), 1 = strong pull to the highest-cosine adjacent task; intermediate = cosine-sharpened.
    ADJACENCY_STRENGTH: float = 0.6
    # Adjacent band over a candidate's max cosine to the skill loadout. The floor is pinned to
    # RETRIEVAL_SIM_FLOOR so every adjacency pick is a real solve-time coverage hit (R2 floor
    # reconciliation); the ceiling rejects trivial near-duplicates (anti coverage-inflation).
    ADJACENCY_FEASIBILITY_FLOOR: float = 0.80   # = RETRIEVAL_SIM_FLOOR
    ADJACENCY_TRIVIAL_CEIL: float = 0.92
    # Forced diversity guard: >= this share of every cohort is a uniform external-benchmark draw,
    # independent of adjacency (also the cold-start + exhaustion fallback). FR-004.
    EXTERNAL_MIN_FRACTION: float = 0.30

    # --- 005 PE-gated meta-reflection tunables (contracts/reflect.md; research R1/R2/R3) ---
    REFLECT_ENABLED: bool = True            # master switch; False = pre-005 behavior (SC-008)
    REFLECT_PE_LOW: float = 0.3             # none/cheap boundary (R1, bimodal valley)
    # cheap/full boundary; defaults to CRYSTALLIZE_PE so {escalated}∪{pe>=HIGH} exactly supersets
    # today's crystallize trigger (F1/R2 — no SC-008 regression).
    REFLECT_PE_HIGH: float = 0.5
    # within full: a matched skill with PE below ⇒ edit (admit versions it); cold or PE at/above ⇒
    # create. 0.95 so the edit path is reachable on the live bimodal PE (full clusters 0.9–1.0, U3).
    # The version-vs-new-skill split is delegated to admit()'s internal _LARGE_PE; this knob governs
    # reflect's edit/create *labelling* and the future retrieval-keyed edit (P2.1).
    REFLECT_EDIT_PE_MAX: float = 0.95
    REFLECT_MODEL_ROLE: str = "reflector"  # proxy role label for the full-tier call (IX metering)

    @model_validator(mode="after")
    def _check_reflect_band(self) -> "Settings":
        if self.REFLECT_PE_LOW > self.REFLECT_PE_HIGH:
            raise ValueError("REFLECT_PE_LOW must be <= REFLECT_PE_HIGH")
        return self

    @property
    def frontier_model(self) -> str:
        """The model id actually used for escalation, per provider."""
        return self.DEEPSEEK_MODEL if self.TEACHER_PROVIDER == "deepseek" else self.TEACHER_MODEL

    @property
    def teacher_rates_per_mtok(self) -> tuple[float, float]:
        """(input, output) USD per 1M tokens for the active frontier model."""
        return {
            "claude-opus-4-8": (5.0, 25.0),
            "claude-sonnet-4-6": (3.0, 15.0),
            "claude-haiku-4-5": (1.0, 5.0),
            "deepseek-chat": (0.27, 1.10),
            "deepseek-reasoner": (0.55, 2.19),
        }.get(self.frontier_model, (5.0, 25.0))

    @property
    def db_dsn(self) -> str:
        """libpq connection string for the owning role."""
        return (
            f"host={self.DB_HOST} port={self.DB_PORT} dbname={self.DB_NAME} "
            f"user={self.DB_USER} password={self.DB_PASSWORD}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load + validate settings once. Raises ValidationError (naming the var)
    on a missing/empty required value — the fail-fast contract (SC-008)."""
    return Settings()
