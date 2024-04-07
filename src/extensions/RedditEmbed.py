import logging
import os
import re
from dataclasses import dataclass
from enum import IntEnum

from asyncpraw import Reddit
from asyncpraw.models import Submission
from discord import ButtonStyle, Embed, Interaction, Message
from discord.app_commands import command, default_permissions, describe, rename
from discord.ext.commands import Bot, GroupCog
from discord.ui import Button, View
import requests

from common.discord import respond_or_followup
from common.io import load_cog_toml
from database.gateway import DBSession
from database.models import RedditMessagesEnabled

COG_STRINGS = load_cog_toml(__name__)
REGEX_STR = r"https:\/\/(www\.)?reddit\.com\/r\/[\w\-]+\/(comments)\/\w+"
SHARE_REGEX = r"https:\/\/(www\.)?reddit\.com\/r\/[\w\-]+\/s\/\w+"
INTERACTION_PREFIX = f"{__name__}."


class PostType(IntEnum):
    TEXT = 0
    IMAGE = 1
    VIDEO = 2
    LINK = 3
    MULTI_MEDIA = 4

    @staticmethod
    def from_str(string: str):
        string = string.lower()
        match string:
            case "self":
                return PostType.TEXT
            case "text":
                return PostType.TEXT
            case "image":
                return PostType.IMAGE
            case "hosted:video":
                return PostType.VIDEO
            case "link":
                return PostType.LINK
            case "multi_media":
                return PostType.MULTI_MEDIA

    def to_str(self):
        return self.name.lower().replace("_", " ").capitalize()

    def __str__(self):
        return self.to_str()


@dataclass
class RedditPost:
    author_name: str
    author_avatar: str
    post_url: str
    post_type: PostType
    post_subreddit: str
    subreddit_icon: str
    post_title: str
    vote_count: int
    comment_count: int
    post_text: str = ""
    post_image: str = ""
    post_link: str = ""
    is_nsfw: bool = False
    text_overflow: bool = False


def make_post_embed(post: RedditPost) -> Embed:
    embed = Embed(title=post.post_title, color=0xFF5700, url=post.post_url)
    if (
        post.post_type == PostType.IMAGE
        or post.post_type == PostType.VIDEO
        or post.post_type == PostType.LINK
    ):
        embed.set_image(url=post.post_image)

    if post.post_type == PostType.VIDEO:
        embed.description = f"Direct video link: [link]({post.post_link})"

    if post.post_type == PostType.TEXT or post.post_type == PostType.MULTI_MEDIA:
        embed.description = post.post_text

    embed.set_footer(
        text=f"Posted on {post.post_subreddit} • {post.vote_count} votes, {post.comment_count} comments",
        icon_url=post.subreddit_icon,
    )
    embed.set_author(
        name=f"u/{post.author_name} posted [{post.post_type.to_str()}]",
        icon_url=post.author_avatar,
    )
    return embed


def make_post_buttons(post: RedditPost) -> View:
    view = View(timeout=None)
    match post.post_type:
        case PostType.VIDEO:
            button = Button(
                style=ButtonStyle.primary,
                label="Watch video",
                custom_id=f"{INTERACTION_PREFIX}video",
            )
            view.add_item(button)
        case PostType.LINK:
            button = Button(
                style=ButtonStyle.primary, label="Go to linked site", url=post.post_link
            )
            view.add_item(button)

    button = Button(
        style=ButtonStyle.secondary, label="View on reddit", url=post.post_url
    )
    view.add_item(button)
    return view


def get_post_url(share_url: str) -> str:
    redirect = requests.get(share_url)
    return redirect.url


@default_permissions(administrator=True)
class RedditEmbedAdmin(GroupCog, name=COG_STRINGS["reddit_admin_group_name"]):

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(
        name=COG_STRINGS["reddit_enable_messages_name"],
        description=COG_STRINGS["reddit_enable_messages_description"],
    )
    async def enable_on_message(self, interaction: Interaction):
        db_item = DBSession.get(RedditMessagesEnabled, guild_id=interaction.guild.id)
        if not db_item:
            db_item = RedditMessagesEnabled(
                guild_id=interaction.guild.id, is_enabled=True
            )
            DBSession.update(db_item)
        else:
            db_item.is_enabled = True
            DBSession.create(db_item)
        await respond_or_followup(
            message=COG_STRINGS["reddit_enable_messages_success"],
            interaction=interaction,
            ephemeral=True,
        )

    @command(
        name=COG_STRINGS["reddit_disable_messages_name"],
        description=COG_STRINGS["reddit_disable_messages_description"],
    )
    async def disable_on_message(self, interaction: Interaction):
        db_item = DBSession.get(RedditMessagesEnabled, guild_id=interaction.guild.id)
        if not db_item:
            db_item = RedditMessagesEnabled(
                guild_id=interaction.guild.id, is_enabled=False
            )
            DBSession.update(db_item)
        else:
            db_item.is_enabled = False
            DBSession.create(db_item)
        await respond_or_followup(
            message=COG_STRINGS["reddit_disable_messages_success"],
            interaction=interaction,
            ephemeral=True,
        )


class RedditEmbed(GroupCog, name=COG_STRINGS["reddit_group_name"]):

    def __init__(self, bot: Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"{__name__} has been added as a Cog")
        self.reddit_api = Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            redirect_uri=os.getenv("REDDIT_REDIRECT_URI"),
            user_agent=f"BetterDiscordEmbedder (by u/{os.getenv('REDDIT_USERNAME')})",
        )
        self.logger.debug(
            self.reddit_api.auth.url(
                scopes=["identity"], state="...", duration="permanent"
            )
        )

    @GroupCog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return

        db_item = DBSession.get(RedditMessagesEnabled, guild_id=message.guild.id)
        if not db_item or not db_item.is_enabled:
            return

        found_urls = re.finditer(
            f"({REGEX_STR})|({SHARE_REGEX})", message.content, re.MULTILINE
        )
        should_suppress = False

        for _, match in enumerate(found_urls, start=1):
            share_search = re.search(SHARE_REGEX, match.group())
            if share_search:
                match = get_post_url(match.group())
            else:
                match = match.group()
            reddit_post = await self.get_post(match)
            embed = make_post_embed(reddit_post)
            view = make_post_buttons(reddit_post)
            await message.reply(embed=embed, view=view, mention_author=False)
            should_suppress = True

        if should_suppress:
            await message.edit(suppress=True)

    @GroupCog.listener()
    async def on_interaction(self, interaction: Interaction):
        if not interaction.data or not interaction.data.get("custom_id"):
            return

        if not interaction.data.get("custom_id").startswith(INTERACTION_PREFIX):
            return

        custom_id = interaction.data.get("custom_id").replace(INTERACTION_PREFIX, "")

        if custom_id.startswith("video"):
            message_embed = interaction.message.embeds[0]
            description_data = message_embed.description
            url = re.search("\((.*)\)", description_data).group(1)
            await interaction.response.send_message(content=url, ephemeral=True)

    async def get_post(self, url: str):
        submission: Submission = await self.reddit_api.submission(url=url)
        await submission.load()

        if submission.is_self:
            post_type = PostType.TEXT
        else:
            post_type = PostType.from_str(submission.post_hint)
        if post_type == PostType.TEXT:
            if submission.link_flair_type == "richtext":
                post_type = PostType.MULTI_MEDIA

        post_text = ""
        post_image = ""
        post_link = ""

        if post_type == PostType.IMAGE:
            post_image = submission.url
        elif post_type == PostType.LINK:
            post_link = submission.url
            post_image = submission.preview.get("images")[0].get("source").get("url")
        elif post_type == PostType.TEXT or post_type == PostType.MULTI_MEDIA:
            post_text = submission.selftext
        elif post_type == PostType.VIDEO:
            if submission.media.get("reddit_video").get("is_gif"):
                post_image = submission.media.get("reddit_video").get("fallback_url")
            else:
                post_image = (
                    submission.preview.get("images")[0].get("source").get("url")
                )
                post_link = submission.media.get("reddit_video").get("fallback_url")

        text_overflow = False
        if len(post_text) > 500:
            post_text = post_text[:500]
            post_text += "\n\nRead more on reddit..."
            text_overflow = True

        await submission.subreddit.load()
        subreddit = submission.subreddit
        subreddit_icon = (
            subreddit.icon_img if subreddit.icon_img else subreddit.community_icon
        )

        await submission.author.load()
        reddit_post = RedditPost(
            author_name=submission.author.name,
            author_avatar=submission.author.icon_img,
            post_url=f"https://www.reddit.com{submission.permalink}",
            post_type=post_type,
            post_subreddit=submission.subreddit_name_prefixed,
            subreddit_icon=subreddit_icon,
            post_title=submission.title,
            vote_count=submission.score,
            comment_count=submission.num_comments,
            is_nsfw=submission.over_18,
            post_text=post_text,
            post_image=post_image,
            post_link=post_link,
            text_overflow=text_overflow,
        )

        return reddit_post

    @command(
        name=COG_STRINGS["reddit_embed_name"],
        description=COG_STRINGS["reddit_embed_description"],
    )
    @describe(url=COG_STRINGS["reddit_embed_url_describe"])
    @rename(url=COG_STRINGS["reddit_embed_rename"])
    async def embed(self, interaction: Interaction, url: str):
        await interaction.response.defer()

        matches = re.search(SHARE_REGEX, url)
        found_url = None
        if matches:
            found_url = get_post_url(matches.group())
        else:
            matches = re.search(REGEX_STR, url)
            if matches:
                found_url = matches.group()

        if not found_url:
            await respond_or_followup(
                message=COG_STRINGS["warn_invalid_url"], interaction=interaction
            )
            return

        reddit_post = await self.get_post(found_url)
        embed = make_post_embed(reddit_post)
        view = make_post_buttons(reddit_post)

        await respond_or_followup(
            message="",
            interaction=interaction,
            embed=embed,
            view=view,
            delete_after=None,
        )


async def setup(bot: Bot):
    await bot.add_cog(RedditEmbed(bot))
    await bot.add_cog(RedditEmbedAdmin(bot))
