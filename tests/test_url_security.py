"""Credential-bearing channels must reject lookalike or disguised hosts."""

import pytest

from weblens.channels.arxiv import ArxivChannel
from weblens.channels.bilibili import BilibiliChannel
from weblens.channels.facebook import FacebookChannel
from weblens.channels.github import GitHubChannel
from weblens.channels.hackernews import HackerNewsChannel
from weblens.channels.instagram import InstagramChannel
from weblens.channels.linkedin import LinkedInChannel
from weblens.channels.reddit import RedditChannel
from weblens.channels.stackoverflow import StackOverflowChannel
from weblens.channels.twitter import TwitterChannel
from weblens.channels.v2ex import V2EXChannel
from weblens.channels.wikipedia import WikipediaChannel
from weblens.channels.xiaohongshu import XiaoHongShuChannel
from weblens.channels.xiaoyuzhou import XiaoyuzhouChannel
from weblens.channels.xueqiu import XueqiuChannel
from weblens.channels.youtube import YouTubeChannel
from weblens.utils.url import host_matches


@pytest.mark.parametrize(
    ("channel", "valid_url"),
    [
        (TwitterChannel(), "https://mobile.twitter.com/user/status/1"),
        (TwitterChannel(), "https://X.COM./user/status/1"),
        (XiaoHongShuChannel(), "https://www.xiaohongshu.com/explore/1"),
        (XiaoHongShuChannel(), "https://xhslink.com/a/1"),
        (BilibiliChannel(), "https://www.bilibili.com/video/BV1"),
        (BilibiliChannel(), "https://b23.tv/abc"),
        (XueqiuChannel(), "https://stock.xueqiu.com/v5/stock/quote"),
    ],
)
def test_credential_channels_accept_exact_hosts_and_subdomains(channel, valid_url):
    assert channel.can_handle(valid_url)


@pytest.mark.parametrize(
    ("channel", "malicious_url"),
    [
        (TwitterChannel(), "https://x.com.evil.test/user/status/1"),
        (TwitterChannel(), "https://notx.com/user/status/1"),
        (TwitterChannel(), "https://x.com@evil.test/user/status/1"),
        (TwitterChannel(), "https://user:pass@x.com/user/status/1"),
        (TwitterChannel(), "ftp://x.com/user/status/1"),
        (XiaoHongShuChannel(), "https://xiaohongshu.com.evil.test/explore/1"),
        (XiaoHongShuChannel(), "https://xiaohongshu.com@evil.test/explore/1"),
        (BilibiliChannel(), "https://bilibili.com.evil.test/video/BV1"),
        (BilibiliChannel(), "https://b23.tv@evil.test/abc"),
        (XueqiuChannel(), "https://xueqiu.com.evil.test/S/SH600519"),
        (XueqiuChannel(), "https://xueqiu.com@evil.test/S/SH600519"),
    ],
)
def test_credential_channels_reject_lookalikes_and_userinfo(channel, malicious_url):
    assert not channel.can_handle(malicious_url)


@pytest.mark.parametrize(
    ("channel", "subdomain_url", "port_url"),
    [
        (
            GitHubChannel(),
            "https://api.github.com/repos/openai/openai-python",
            "https://github.com:443/openai/openai-python",
        ),
        (
            YouTubeChannel(),
            "https://m.youtube.com/watch?v=abc",
            "https://youtu.be:443/abc",
        ),
        (
            RedditChannel(),
            "https://old.reddit.com/r/python",
            "https://reddit.com:443/r/python",
        ),
        (
            LinkedInChannel(),
            "https://www.linkedin.com/in/example",
            "https://linkedin.com:443/in/example",
        ),
        (
            V2EXChannel(),
            "https://www.v2ex.com/t/1",
            "https://v2ex.com:443/t/1",
        ),
        (
            XiaoyuzhouChannel(),
            "https://www.xiaoyuzhoufm.com/episode/1",
            "https://xiaoyuzhoufm.com:443/episode/1",
        ),
        (
            FacebookChannel(),
            "https://m.facebook.com/groups/1",
            "https://facebook.com:443/groups/1",
        ),
        (
            InstagramChannel(),
            "https://www.instagram.com/example",
            "https://instagram.com:443/example",
        ),
        (
            HackerNewsChannel(),
            "https://news.ycombinator.com/item?id=1",
            "https://news.ycombinator.com:443/item?id=1",
        ),
        (
            StackOverflowChannel(),
            "https://unix.stackexchange.com/q/1",
            "https://stackoverflow.com:443/questions/1",
        ),
        (
            WikipediaChannel(),
            "https://en.m.wikipedia.org/wiki/X",
            "https://en.wikipedia.org:443/wiki/X",
        ),
        (
            ArxivChannel(),
            "https://export.arxiv.org/abs/1706.03762",
            "https://arxiv.org:443/abs/1706.03762",
        ),
    ],
)
def test_fixed_domain_channels_accept_subdomains_and_explicit_ports(
    channel, subdomain_url, port_url
):
    assert channel.can_handle(subdomain_url)
    assert channel.can_handle(port_url)


@pytest.mark.parametrize(
    ("channel", "official_domain"),
    [
        (GitHubChannel(), "github.com"),
        (YouTubeChannel(), "youtube.com"),
        (RedditChannel(), "reddit.com"),
        (LinkedInChannel(), "linkedin.com"),
        (V2EXChannel(), "v2ex.com"),
        (XiaoyuzhouChannel(), "xiaoyuzhoufm.com"),
        (FacebookChannel(), "facebook.com"),
        (InstagramChannel(), "instagram.com"),
        (HackerNewsChannel(), "news.ycombinator.com"),
        (StackOverflowChannel(), "stackoverflow.com"),
        (WikipediaChannel(), "wikipedia.org"),
        (ArxivChannel(), "arxiv.org"),
    ],
)
def test_fixed_domain_channels_reject_suffix_lookalikes_and_userinfo(
    channel, official_domain
):
    assert not channel.can_handle(f"https://{official_domain}.evil.test/path")
    assert not channel.can_handle(f"https://{official_domain}@evil.test/path")
    assert not channel.can_handle(f"https://user:pass@{official_domain}/path")


@pytest.mark.parametrize(
    "malicious_url",
    [
        "https://x.com:not-a-port/path",
        "https://x.com:65536/path",
        "https://x.com:-1/path",
        "https://x.com:999999999999/path",
    ],
)
def test_host_matches_rejects_invalid_ports(malicious_url):
    assert not host_matches(malicious_url, "x.com")
