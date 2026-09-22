"""工具函数"""
from datetime import datetime, timezone, timedelta

# 上海时区 UTC+8
SHANGHAI_TZ = timezone(timedelta(hours=8))


def shanghai_now() -> datetime:
    """获取当前上海时间（UTC+8）"""
    return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
