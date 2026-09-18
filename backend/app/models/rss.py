"""RSSHub 订阅源与已推送条目（本地数据库持久化）"""
from datetime import datetime
from sqlalchemy import (String, Integer, Text, DateTime, Boolean, JSON,
                        UniqueConstraint, Index)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class RssSource(Base):
    """订阅源
    rss_type: http（直接 RSS/Atom/JSON）| rsshub_local（RSSHub 本地 Docker）
    """
    __tablename__ = "rss_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    tags = mapped_column(JSON, default=list)                # 自定义标签（数组）
    remark: Mapped[str] = mapped_column(String(300), nullable=True, default="")  # 备注
    rss_type: Mapped[str] = mapped_column(String(20), default="rsshub_local")    # http / rsshub_local
    url: Mapped[str] = mapped_column(String(600), nullable=True)                 # 订阅地址（完整 URL，不做校验）
    base: Mapped[str] = mapped_column(String(300), nullable=True, default="")    # RSSHub 前缀地址（rsshub_local 时存储 Docker/镜像地址）
    interval_min: Mapped[int] = mapped_column(Integer, default=5)               # 轮询间隔（分钟）
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    net_status: Mapped[str] = mapped_column(String(300), nullable=True)         # 网络状态 untested/ok/err:xxx
    last_poll: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(300), nullable=True)
    last_item_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow)


class RssItem(Base):
    """已抓取的消息条目（按 source+guid 去重）"""
    __tablename__ = "rss_items"
    __table_args__ = (
        UniqueConstraint("source_id", "guid", name="uq_rss_source_guid"),
        Index("ix_rss_item_pub", "pub_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=True)
    guid: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    link: Mapped[str] = mapped_column(String(600), nullable=True)
    author: Mapped[str] = mapped_column(String(100), nullable=True)
    pub_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    platform: Mapped[str] = mapped_column(String(20), default="generic")
    tags = mapped_column(JSON, default=list)
    is_st: Mapped[bool] = mapped_column(Boolean, default=False)
    importance: Mapped[int] = mapped_column(Integer, default=3)  # 1高 2中 3一般
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow)