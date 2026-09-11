"""RSSHub 订阅源与已推送条目（本地数据库持久化）"""
from datetime import datetime
from sqlalchemy import (String, Integer, Text, DateTime, Boolean, JSON,
                        ForeignKey, UniqueConstraint, Index)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class RssSource(Base):
    __tablename__ = "rss_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default="generic")  # weibo/wechat/guba/generic
    route: Mapped[str] = mapped_column(String(300), nullable=True)        # RSSHub 路径（带前导斜杠）
    url: Mapped[str] = mapped_column(String(600), nullable=True)          # 完整 RSS URL（优先于 route）
    tags = mapped_column(JSON, default=list)                              # 关注标签（个股名/代码/关键词）
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_sec: Mapped[int] = mapped_column(Integer, default=30)        # 轮询间隔（秒），限频
    filter_st: Mapped[bool] = mapped_column(Boolean, default=True)        # 过滤 ST/*ST 相关消息
    last_poll: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(300), nullable=True)
    last_item_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow)


class RssItem(Base):
    """已推送/已抓取的消息条目（按 source+guid 去重）"""
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