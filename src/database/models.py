from sqlalchemy import BigInteger, Boolean, Column, String, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base

base = declarative_base()

__all__ = [
    "VoiceAdminParent",
    "VoiceAdminChild",
    "MusicChannels",
    "RedditMessagesEnabled",
    "InstagramMessagesEnabled",
    "TikTokMessagesEnabled",
    "RoleReactMenus",
]


class VoiceAdminParent(base):
    __tablename__ = "voiceadmin_parents"
    primary_key = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    guild_id = Column(BigInteger, nullable=False)
    channel_id = Column(BigInteger, nullable=False)


class VoiceAdminChild(base):
    __tablename__ = "voiceadmin_children"
    primary_key = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    guild_id = Column(BigInteger, nullable=False)
    channel_id = Column(BigInteger, nullable=False)
    owner_id = Column(BigInteger, nullable=False)
    is_locked = Column(Boolean, nullable=False)
    is_limited = Column(Boolean, nullable=False)
    has_custom_name = Column(Boolean, nullable=False)


class MusicChannels(base):
    __tablename__ = "music_channels"
    guild_id = Column(BigInteger, primary_key=True, nullable=False)
    channel_id = Column(BigInteger, nullable=False)
    message_id = Column(BigInteger, nullable=False)


class RedditMessagesEnabled(base):
    __tablename__ = "reddit_messages_enabled"
    guild_id = Column(BigInteger, primary_key=True, nullable=False)
    is_enabled = Column(Boolean, default=False)


class InstagramMessagesEnabled(base):
    __tablename__ = "instagram_messages_enabled"
    guild_id = Column(BigInteger, primary_key=True, nullable=False)
    is_enabled = Column(Boolean, default=False)


class TikTokMessagesEnabled(base):
    __tablename__ = "tiktok_messages_enabled"
    guild_id = Column(BigInteger, primary_key=True, nullable=False)
    is_enabled = Column(Boolean, default=False)

class RoleReactMenus(base):
    __tablename__ = "rolereact_menus"
    primary_key = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, nullable=False)
    guild_id = Column(BigInteger, nullable=False)
    message_id = Column(BigInteger, nullable=False)