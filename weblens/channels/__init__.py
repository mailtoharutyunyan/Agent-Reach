"""
Channel registry — lists all supported platforms for doctor checks.
"""

# Import all channels
from .arxiv import ArxivChannel
from .base import Channel
from .bilibili import BilibiliChannel
from .boss import BossChannel
from .exa_search import ExaSearchChannel
from .facebook import FacebookChannel
from .github import GitHubChannel
from .hackernews import HackerNewsChannel
from .instagram import InstagramChannel
from .linkedin import LinkedInChannel
from .reddit import RedditChannel
from .rss import RSSChannel
from .stackoverflow import StackOverflowChannel
from .twitter import TwitterChannel
from .v2ex import V2EXChannel
from .web import WebChannel
from .wikipedia import WikipediaChannel
from .xiaohongshu import XiaoHongShuChannel
from .xiaoyuzhou import XiaoyuzhouChannel
from .xueqiu import XueqiuChannel
from .youtube import YouTubeChannel

ALL_CHANNELS: list[Channel] = [
    GitHubChannel(),
    TwitterChannel(),
    YouTubeChannel(),
    RedditChannel(),
    FacebookChannel(),
    InstagramChannel(),
    BilibiliChannel(),
    XiaoHongShuChannel(),
    LinkedInChannel(),
    BossChannel(),
    XiaoyuzhouChannel(),
    V2EXChannel(),
    HackerNewsChannel(),
    StackOverflowChannel(),
    WikipediaChannel(),
    ArxivChannel(),
    XueqiuChannel(),
    RSSChannel(),
    ExaSearchChannel(),
    WebChannel(),
]


def get_channel(name: str) -> Channel | None:
    """Get a channel by name."""
    for ch in ALL_CHANNELS:
        if ch.name == name:
            return ch
    return None


def get_all_channels() -> list[Channel]:
    """Get all registered channels."""
    return ALL_CHANNELS


__all__ = [
    "Channel",
    "ALL_CHANNELS",
    "get_channel",
    "get_all_channels",
]
