import logging
import os
import re
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse
from time import time

from discord import (
    Embed,
    File,
    Interaction,
    Message,
    RawReactionActionEvent,
    PartialEmoji,
)
from discord.abc import MISSING
from discord.app_commands import command, default_permissions, describe, rename
from discord.ext.commands import Bot, GroupCog
from instagramdl.api import get_post_data
from instagramdl.models import *
from instagramdl.parser import parse_api_response

from common.discord import respond_or_followup
from common.io import load_cog_toml, reduce_video
from database.gateway import DBSession
from database.models import InstagramMessagesEnabled

COG_STRINGS = load_cog_toml(__name__)
REGEX_STR = r"https\:\/\/(www\.)?instagram\.com\/(reel|p)\/[a-zA-Z0-9]+"
REQUEST_TIMER = 5
MAX_POST_DESCRIPTION_LENGTH = 360
INSTA_COLOUR = 0xE1306C
INSTA_ICON_URL = "https://images-ext-2.discordapp.net/external/C6jCIKlXguRhfmSp6USkbWsS11fnsbBgMXiclR2R4ps/https/www.instagram.com/static/images/ico/favicon-192.png/68d99ba29cc8.png"
RETRY_EMOJI = PartialEmoji.from_str(os.getenv("INSTA_RETRY_EMOJI"))
CONFIRM_EMOJI = PartialEmoji.from_str(os.getenv("INSTA_RESPONSE_EMOJI"))


def paginate_video_text(videos):
    if len(videos) > 2000:
        remaining = videos
        output = []
        while len(remaining) > 2000:
            next_index = remaining.rfind(" [", 0, 2000)
            output.append(remaining[:next_index])
            remaining = remaining[next_index + 1 :]
        output.append(remaining)
        return output
    return [videos]


def reduce_url_length(url: str):
    needed_params = ["_nc_ht", "_nc_ohc", "edm", "oh", "oe"]
    params = parse_qs(urlparse(url).query)
    params_string = "&".join(
        [f"{k}={v[0]}" for k, v in params.items() if k in needed_params]
    )
    base_string = url.split("?")[0]
    return f"{base_string}?{params_string}"


def parse_description(description: str):
    tag_regex = r"(?<!\[)\#([0-9a-zA-Z])+(?!\])"
    out_description = description
    match = re.search(tag_regex, out_description, re.MULTILINE)
    for _ in range(out_description.count("#")):
        before = out_description[: match.start()]
        after = out_description[match.end() :]
        string = out_description[match.start() : match.end()]
        replace_string = f"[{string}](https://www.instagram.com/explore/tags/{string.replace('#','')})"
        out_description = before + replace_string + after
        match = re.search(tag_regex, out_description, re.MULTILINE)
    return out_description


def make_embeds(post: ImagePost | MultiPost | VideoPost):
    if len(post.caption) > MAX_POST_DESCRIPTION_LENGTH:
        next_space = post.caption.index(" ", MAX_POST_DESCRIPTION_LENGTH)
        if next_space == -1:
            next_space = post.caption.index(".", MAX_POST_DESCRIPTION_LENGTH)

        description = (
            f"{post.caption[:next_space]}\n\n... Read more [on instagram]({post.url})"
        )
    else:
        description = post.caption

    embed = Embed(
        color=INSTA_COLOUR,
        title=f"{'<a:verified:1143572299304407141> ' if post.user.is_verified else''}{post.user.full_name}'s Post",
        description=parse_description(description),
        url=post.url,
    )

    embed.set_author(
        name=f"@{post.user.username}",
        url=post.user.url,
        icon_url=post.user.profile_pic_url,
    )

    timestamp = datetime.fromtimestamp(post.timestamp)

    embed.set_footer(
        text=f"Post on {timestamp.strftime('%d/%m/%Y')} at {timestamp.strftime('%-H:%M')}",
        icon_url=INSTA_ICON_URL,
    )

    if isinstance(post, VideoPost):
        return [embed]

    if isinstance(post, ImagePost):
        embed.set_image(url=post.image_url)
        return [embed]

    embeds = [embed]
    # TODO: Allow posts with more items.
    for item in post.items[:9]:
        if isinstance(item, ImagePost):
            sub_embed = Embed(url=post.url, color=INSTA_COLOUR)
            sub_embed.set_image(url=item.image_url)
            embeds.append(sub_embed)

    return embeds


@default_permissions(administrator=True)
class InstagramEmbedAdmin(GroupCog, name=COG_STRINGS["instagram_admin_group_name"]):

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(
        name=COG_STRINGS["instagram_enable_messages_name"],
        description=COG_STRINGS["instagram_enable_messages_description"],
    )
    async def enable_on_message(self, interaction: Interaction):
        db_item = DBSession.get(InstagramMessagesEnabled, guild_id=interaction.guild.id)
        if not db_item:
            db_item = InstagramMessagesEnabled(
                guild_id=interaction.guild.id, is_enabled=True
            )
            DBSession.update(db_item)
        else:
            db_item.is_enabled = True
            DBSession.create(db_item)
        await respond_or_followup(
            message=COG_STRINGS["instagram_enable_messages_success"],
            interaction=interaction,
            ephemeral=True,
        )

    @command(
        name=COG_STRINGS["instagram_disable_messages_name"],
        description=COG_STRINGS["instagram_disable_messages_description"],
    )
    async def disable_on_message(self, interaction: Interaction):
        db_item = DBSession.get(InstagramMessagesEnabled, guild_id=interaction.guild.id)
        if not db_item:
            db_item = InstagramMessagesEnabled(
                guild_id=interaction.guild.id, is_enabled=False
            )
            DBSession.update(db_item)
        else:
            db_item.is_enabled = False
            DBSession.create(db_item)
        await respond_or_followup(
            message=COG_STRINGS["instagram_disable_messages_success"],
            interaction=interaction,
            ephemeral=True,
        )


class InstagramEmbed(GroupCog, name=COG_STRINGS["instagram_group_name"]):

    def __init__(self, bot: Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"{__name__} has been added as a Cog")

    async def request_reply(
        self, url: str, interaction: Interaction = None, message: Message = None
    ):
        raw_sanitised_url = urlparse(url)
        sanitised_url = f"{raw_sanitised_url.scheme}://{raw_sanitised_url.netloc}{raw_sanitised_url.path}"
        raw_data = get_post_data(sanitised_url)
        post_data = parse_api_response(raw_data)

        embeds = make_embeds(post_data)
        paths = []
        if isinstance(post_data, VideoPost):
            paths = [reduce_video(post_data.download("./"))]
        elif isinstance(post_data, MultiPost):
            for item in post_data.items:
                if isinstance(item, VideoPost):
                    paths.append(reduce_video(item.download("./")))

        if not paths:
            files = MISSING
        else:
            files = [File(x) for x in paths]

        if message:
            await message.reply(embeds=embeds, mention_author=False, files=files)
        elif interaction:
            await respond_or_followup(
                message="",
                embeds=embeds,
                interaction=interaction,
                delete_after=None,
                files=files,
            )

        if paths:
            for file in paths:
                os.remove(file)

        return True

    @GroupCog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return

        db_item = DBSession.get(InstagramMessagesEnabled, guild_id=message.guild.id)
        if not db_item or not db_item.is_enabled:
            return

        should_suppress = False
        found_urls = re.finditer(REGEX_STR, message.content, re.MULTILINE)
        for _, match in enumerate(found_urls, start=1):
            should_suppress = (
                await self.request_reply(url=match.group(0), message=message)
                or should_suppress
            )

        if should_suppress:
            await message.edit(suppress=True)

    @GroupCog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        if payload.member.id == self.bot.user.id:
            return

        if payload.emoji != RETRY_EMOJI:
            return

        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if not message:
            return

        cutoff = datetime.fromtimestamp(time()) - timedelta(
            hours=float(os.getenv("SOCIAL_RETRY_TIMEOUT"))
        )
        jump_url = None
        async for message_item in message.channel.history(after=cutoff):

            if not message_item.author == self.bot.user:
                continue

            if not message_item.reference:
                continue

            if message_item.reference.message_id != message.id:
                continue

            jump_url = message_item.jump_url
            break

        if jump_url is not None:
            await message.reply(
                f"This post has already been embeded: [jump to message]({jump_url})",
                silent=True,
                delete_after=30,
                mention_author=False,
            )
        else:
            if re.search(REGEX_STR, message.content, re.MULTILINE) is None:
                return

            await message.add_reaction(CONFIRM_EMOJI)

            found_urls = re.finditer(REGEX_STR, message.content, re.MULTILINE)
            should_suppress = False

            for _, match in enumerate(found_urls, start=1):
                should_suppress = should_suppress or await self.request_reply(
                    url=match.group(0), message=message
                )

            if should_suppress:
                await message.edit(suppress=True)

        await message.remove_reaction(payload.emoji, payload.member)
        await message.remove_reaction(CONFIRM_EMOJI, guild.me)

    @command(
        name=COG_STRINGS["instagram_embed_name"],
        description=COG_STRINGS["instagram_embed_description"],
    )
    @describe(url=COG_STRINGS["instagram_embed_url_describe"])
    @rename(url=COG_STRINGS["instagram_embed_rename"])
    async def embed(self, interaction: Interaction, url: str):
        await interaction.response.defer()
        validate_url = re.search(REGEX_STR, url)
        if not validate_url:
            await respond_or_followup(
                message=COG_STRINGS["instagram_warn_invalid_url"],
                interaction=interaction,
            )
            return

        await self.request_reply(url=url, interaction=interaction)


async def setup(bot: Bot):
    await bot.add_cog(InstagramEmbed(bot))
    await bot.add_cog(InstagramEmbedAdmin(bot))
