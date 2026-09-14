"""全局配置"""
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 应用
    APP_NAME: str = "deepAStock 深度A股交易"
    APP_VERSION: str = "1.1.5"
    DEBUG: bool = False

    # 数据库 (默认 SQLite, 可切换 PostgreSQL)
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'quant.db'}"
    USE_POSTGRES: bool = False

    # 安全
    #   留空 或 默认占位 或 未设置时，首次启动自动生成随机密钥并持久化到 data/.secret_key，
    #   之后重启保持不变；生产环境可通过环境变量 SECRET_KEY 显式覆盖。
    SECRET_KEY: str = ""

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # 数据源
    PRIMARY_SOURCE: str = "sina+tencent"
    BACKUP_SOURCE: str = "tencent"
    SOURCE_TIMEOUT: float = 5.0

    # RSSHub（本地部署订阅源，仅走自建实例，不调用公网 RSSHub）
    RSSHUB_BASE: str = "http://127.0.0.1:1200"
    RSSHUB_ENABLED: bool = True
    RSSHUB_POLL_SECONDS: int = 30   # 全局最小轮询步长（单源限频见 interval_sec）
    RSSHUB_ITEM_RETENTION_DAYS: int = 30

    # 数据目录
    DATA_DIR: Path = BASE_DIR / "data"
    KLINE_CACHE_DIR: Path = BASE_DIR / "data" / "kline_cache"
    REPLAY_REPORT_DIR: Path = BASE_DIR / "data" / "replay_reports"

    # 定时任务
    REPLAY_HOUR: int = 17
    REPLAY_MINUTE: int = 30
    EVOLUTION_HOUR: int = 20
    EVOLUTION_MINUTE: int = 0


settings = Settings()

# 确保目录存在
for d in [settings.DATA_DIR, settings.KLINE_CACHE_DIR, settings.REPLAY_REPORT_DIR, BASE_DIR / "data" / "logs"]:
    d.mkdir(parents=True, exist_ok=True)

# SECRET_KEY：未显式配置时自动生成并持久化（data/.secret_key），重启保持一致
if not settings.SECRET_KEY:
    _key_file = settings.DATA_DIR / ".secret_key"
    try:
        settings.SECRET_KEY = _key_file.read_text(encoding="utf-8").strip()
    except OSError:
        settings.SECRET_KEY = ""
    if not settings.SECRET_KEY:
        settings.SECRET_KEY = secrets.token_hex(32)
        try:
            _key_file.write_text(settings.SECRET_KEY, encoding="utf-8")
        except OSError:
            pass
