import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Union
from urllib.request import urlretrieve
from uuid import uuid4

from bs4 import BeautifulSoup
from discord import Embed, File, Interaction, Message
from discord.app_commands import command, default_permissions, describe, rename
from discord.ext.commands import Bot, GroupCog
from discord.utils import MISSING
from playwright.async_api import async_playwright, TimeoutError

from common.discord import respond_or_followup
from common.io import load_cog_toml
from database.gateway import DBSession
from database.models import InstagramMessagesEnabled

COG_STRINGS = load_cog_toml(__name__)

REGEX_STR = r"https\:\/\/www\.instagram\.com\/(reel|p)\/[a-zA-Z0-9]+"
INSTAGRAM_ICON = "https://images-ext-2.discordapp.net/external/C6jCIKlXguRhfmSp6USkbWsS11fnsbBgMXiclR2R4ps/https/www.instagram.com/static/images/ico/favicon-192.png/68d99ba29cc8.png"
INTERACTION_PREFIX = f"{__name__}."


@dataclass()
class IGPost:
    author_username: str
    author_display_name: str
    author_avatar_url: str
    author_profile_url: str
    post_url: str
    post_description: str
    post_timestamp: datetime
    post_like_count: int
    post_comment_count: int
    post_images: list[str] = None
    post_videos: list[str] = None


class PostUnavailableException(Exception):

    def __init__(self, url: str):
        super().__init__(f"URL is unavailable post: {url}")
        self.url = url


class InstagramInaccessibleException(Exception):

    def __init__(self, url: str):
        super().__init__(f"Instagram did not load: {url}")
        self.url = url


def make_embeds(post: IGPost) -> list[Embed]:
    if len(post.post_description) > 360:
        next_space = post.post_description.index(" ", 360)
        if next_space == -1:
            next_space = post.post_description.index(".", 360)
        description = f"{post.post_description[:next_space]}\n\n... Read more [on instagram]({post.post_url})"
    else:
        description = post.post_description
    embed = Embed(
        title=f"{post.author_display_name}'{'' if post.author_display_name.endswith('s') else 's'} Post",
        description=description,
        url=post.post_url,
        color=0xE1306C
    )

    embed.set_author(name=f"@{post.author_username}", url=post.author_profile_url, icon_url=post.author_avatar_url)
    embed.set_footer(
        text=f"Posted on {post.post_timestamp.strftime('%d/%m/%Y')} at {post.post_timestamp.strftime('%-H:%M')}",
        icon_url=INSTAGRAM_ICON
    )

    embed.add_field(inline=True, name="Like Count ❤️", value=f"{post.post_like_count:,}")
    embed.add_field(inline=True, name="Comment Count 💬", value=f"{post.post_comment_count:,}")

    if len(post.post_images) == 1:
        embed.set_image(url=post.post_images[0])
        return [embed]
    elif len(post.post_images) > 1:
        embed.set_image(url=post.post_images[0])
        embeds = [embed]
        for image in post.post_images[1:]:
            alt_embed = Embed(url=post.post_url)
            alt_embed.set_image(url=image)
            embeds.append(alt_embed)
        return embeds

    if len(post.post_videos) == 1:
        embed.set_thumbnail(url=post.post_videos[0].get("thumbnail"))
        return [embed]
    elif len(post.post_videos) > 1:
        embed.set_thumbnail(url=post.post_videos[0].get("thumbnail"))
        embeds = [embed]
        for video in post.post_videos[1:]:
            alt_embed = Embed(url=post.post_url)
            alt_embed.set_thumbnail(url=video.get("thumbnail"))
            embeds.append(alt_embed)
        return embeds


class RequestHandler:

    def __init__(self):
        self.last_request = time.time() - 10
        self.list_mutex = asyncio.Lock()
        self.requst_mutex = asyncio.Lock()
        self.requests_to_make = []
        self.logger = logging.getLogger(__name__)

    async def add_request(self, url: str):
        self.requests_to_make.append(url)

    async def get_post_data(self, url: str) -> tuple[str, Union[str, None]]:
        page_source = None
        filename = None

        async with async_playwright() as p:
            browser = await p.firefox.launch()
            context = await browser.new_context()
            await context.clear_cookies()

            page = await context.new_page()
            self.logger.info(f"Opening new page -> {url}")
            await page.goto(url, wait_until="networkidle")

            self.logger.info("Checking for cookies...")
            decline_button = page.get_by_text("Decline optional cookies")
            try:
                await decline_button.click(timeout=10000)
            except TimeoutError:
                raise InstagramInaccessibleException(url)

            unavailable_post = page.get_by_text("Sorry, this page isn't available.")
            if not unavailable_post:
                raise PostUnavailableException(url)

            reels_url_regex = r"https\:\/\/(www\.)?instagram\.com\/reel\/"
            if re.search(reels_url_regex, url):
                async with page.expect_response(
                    lambda response: re.search(
                        r"https\:\/\/scontent(\-[a-z0-9]+\-[0-9]+)?\.cdninstagram\.com\/v\/[a-z0-9\-\.]+\/[a-z0-9\_\.]+",
                        response.url
                    )
                ) as response:
                    self.logger.info("Downloading video file...")
                    value = await response.value
                    video_url = value.url
                    filename = os.path.join(
                        os.curdir,
                        f"{uuid4()}.mp4",
                    )
                    urlretrieve(video_url, filename=filename)

            page_source = await page.content()
            await context.close()
            await browser.close()

        return page_source, filename

    def parse_post_data(self, page_source: str) -> IGPost:
        soup = BeautifulSoup(page_source, "lxml")
        script = soup.find("script", attrs={"type": "application/ld+json"})
        script_data = json.loads(script.text)

        description = script_data.get("articleBody")
        url = script_data.get("mainEntityOfPage").get("@id").replace("\\", "")
        timestamp_str = script_data.get("dateCreated")
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S%z")

        interaction_data = script_data.get("interactionStatistic")
        like_count_schema = "http://schema.org/LikeAction"
        comment_count_schema = "https://schema.org/CommentAction"
        like_count = [
            x.get("userInteractionCount") for x in interaction_data if x.get("interactionType") == like_count_schema
        ][0]
        comment_count = [
            x.get("userInteractionCount") for x in interaction_data if x.get("interactionType") == comment_count_schema
        ][0]

        author_data = script_data.get("author")
        username = author_data.get("identifier").get("value")
        display_name = author_data.get("name")
        avatar_url = author_data.get("image").replace("\\", "")
        profile_url = author_data.get("url").replace("\\", "")

        data_images = script_data.get("image")
        data_videos = script_data.get("video")
        images = [x.get("url").replace("\\", "") for x in data_images]
        videos = [
            {
                "video": x.get("contentUrl").replace("\\",
                                                     ""),
                "thumbnail": x.get("thumbnailUrl").replace("\\",
                                                           "")
            } for x in data_videos
        ]

        post = IGPost(
            author_username=username,
            author_display_name=display_name,
            author_avatar_url=avatar_url,
            author_profile_url=profile_url,
            post_url=url,
            post_description=description,
            post_timestamp=timestamp,
            post_like_count=like_count,
            post_comment_count=comment_count,
            post_images=images,
            post_videos=videos
        )
        return post

    async def make_request(self) -> tuple[IGPost, Union[str, None]]:
        async with self.list_mutex:
            next_request = self.requests_to_make.pop(0)

        async with self.requst_mutex:
            if self.last_request - time.time() < 5:
                await asyncio.sleep(self.last_request - time.time())
            source, filename = await self.get_post_data(next_request)
            self.last_request = time.time()

        post = self.parse_post_data(source)
        return post, filename


@default_permissions(administrator=True)
class InstagramEmbedAdmin(GroupCog, name=COG_STRINGS["instagram_admin_group_name"]):

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(
        name=COG_STRINGS["instagram_enable_messages_name"],
        description=COG_STRINGS["instagram_enable_messages_description"]
    )
    async def enable_on_message(self, interaction: Interaction):
        db_item = DBSession.get(InstagramMessagesEnabled, guild_id=interaction.guild.id)
        if not db_item:
            db_item = InstagramMessagesEnabled(guild_id=interaction.guild.id, is_enabled=True)
            DBSession.update(db_item)
        else:
            db_item.is_enabled = True
            DBSession.create(db_item)
        await respond_or_followup(
            message=COG_STRINGS["instagram_enable_messages_success"],
            interaction=interaction,
            ephemeral=True
        )

    @command(
        name=COG_STRINGS["instagram_disable_messages_name"],
        description=COG_STRINGS["instagram_disable_messages_description"]
    )
    async def disable_on_message(self, interaction: Interaction):
        db_item = DBSession.get(InstagramMessagesEnabled, guild_id=interaction.guild.id)
        if not db_item:
            db_item = InstagramMessagesEnabled(guild_id=interaction.guild.id, is_enabled=False)
            DBSession.update(db_item)
        else:
            db_item.is_enabled = False
            DBSession.create(db_item)
        await respond_or_followup(
            message=COG_STRINGS["instagram_disable_messages_success"],
            interaction=interaction,
            ephemeral=True
        )


class InstagramEmbed(GroupCog, name=COG_STRINGS["instagram_group_name"]):

    def __init__(self, bot: Bot):
        self.bot = bot
        self.request_handler = RequestHandler()
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"{__name__} has been added as a Cog")
        self.tasks = set()

    async def request_and_respond(self, url: str, message: Message = None, interaction: Interaction = None):
        await self.request_handler.add_request(url)
        try:
            post_data, filename = await self.request_handler.make_request()
            embeds = make_embeds(post_data)
            if filename:
                file = File(f"{filename}")
            else:
                file = MISSING

            if message:
                if not message.flags.suppress_embeds:
                    await message.edit(suppress=True)
                await message.reply(embeds=embeds, file=file, mention_author=False)
            elif interaction:
                await respond_or_followup(message="", interaction=interaction, embeds=embeds, file=file, delete_after=None)

            if filename:
                os.remove(filename)

        except InstagramInaccessibleException as e:
            if message:
                await message.reply(content=COG_STRINGS["warn_instagram_inaccessible"].format(url=e.url), mention_author=False)
            elif interaction:
                await respond_or_followup(
                    message=COG_STRINGS["warn_instagram_inaccessible"].format(url=e.url),
                    interaction=interaction,
                    delete_after=10
                )
        except PostUnavailableException as e:
            if message:
                await message.reply(content=COG_STRINGS["warn_post_unavailable"].format(url=e.url), mention_author=False)
            elif interaction:
                await respond_or_followup(
                    message=COG_STRINGS["warn_post_unavailable"].format(url=e.url),
                    interaction=interaction,
                    delete_after=10
                )

    @GroupCog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return

        db_item = DBSession.get(InstagramMessagesEnabled, guild_id=message.guild.id)
        if not db_item or not db_item.is_enabled:
            return

        found_urls = re.finditer(REGEX_STR, message.content, re.MULTILINE)
        for _, match in enumerate(found_urls, start=1):
            task = asyncio.create_task(self.request_and_respond(match.string, message=message))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    @command(name=COG_STRINGS["instagram_embed_name"], description=COG_STRINGS["instagram_embed_description"])
    @describe(url=COG_STRINGS["instagram_embed_url_describe"])
    @rename(url=COG_STRINGS["instagram_embed_rename"])
    async def embed(self, interaction: Interaction, url: str):
        await interaction.response.defer()

        found_urls = re.finditer(REGEX_STR, url, re.MULTILINE)
        if not found_urls:
            await respond_or_followup(message=COG_STRINGS["warn_invalid_url"], interaction=interaction)
            return

        task = asyncio.create_task(self.request_and_respond(url, interaction=interaction))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)


async def setup(bot: Bot):
    import subprocess
    import sys
    subprocess.run([sys.executable, "-m", "playwright", "install"])
    subprocess.run([sys.executable, "-m", "playwright", "install-deps"])
    await bot.add_cog(InstagramEmbed(bot))
    await bot.add_cog(InstagramEmbedAdmin(bot))