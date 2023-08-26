import logging
import os
import re
from urllib.parse import parse_qs, urlparse

from discord import Embed, File, Interaction, Message, RawReactionActionEvent, PartialEmoji
from discord.abc import MISSING
from discord.app_commands import command, default_permissions, describe, rename
from discord.ext.commands import Bot, GroupCog
from instagramdl.exceptions import PostUnavailableException
from instagramdl.get_post import get_info
from instagramdl.post_data import InstagramPost

from common.discord import respond_or_followup
from common.io import load_cog_toml, reduce_video
from database.gateway import DBSession
from database.models import InstagramMessagesEnabled

COG_STRINGS = load_cog_toml(__name__)
REGEX_STR = r"https\:\/\/www\.instagram\.com\/(reel|p)\/[a-zA-Z0-9]+"
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
            remaining = remaining[next_index + 1:]
        output.append(remaining)
        return output
    return [videos]


def reduce_url_length(url: str):
    needed_params = ["_nc_ht", "_nc_ohc", "edm", "oh", "oe"]
    params = parse_qs(urlparse(url).query)
    params_string = "&".join([f"{k}={v[0]}" for k, v in params.items() if k in needed_params])
    base_string = url.split("?")[0]
    return f"{base_string}?{params_string}"


def parse_description(description: str):
    tag_regex = r"(?<!\[)\#([0-9a-zA-Z])+(?!\])"
    out_description = description
    match = re.search(tag_regex, out_description, re.MULTILINE)
    for _ in range(out_description.count("#")):
        before = out_description[:match.start()]
        after = out_description[match.end():]
        string = out_description[match.start():match.end()]
        replace_string = f"[{string}](https://www.instagram.com/explore/tags/{string.replace('#','')})"
        out_description = before + replace_string + after
        match = re.search(tag_regex, out_description, re.MULTILINE)
    return out_description


def make_embeds(post: InstagramPost):
    if len(post.post_description) > MAX_POST_DESCRIPTION_LENGTH:
        next_space = post.post_description.index(' ', MAX_POST_DESCRIPTION_LENGTH)
        if next_space == -1:
            next_space = post.post_description.index('.', MAX_POST_DESCRIPTION_LENGTH)

        description = f"{post.post_description[:next_space]}\n\n... Read more [on instagram]({post.post_url})"
    else:
        description = post.post_description

    embed = Embed(
        color=INSTA_COLOUR,
        title=f"{'<a:verified:1143572299304407141> ' if post.author_is_verified else''}{post.author_display_name}'s Post",
        description=parse_description(description),
        url=post.post_url
    )

    embed.set_author(name=f"@{post.author_username}", url=post.author_profile_url, icon_url=post.author_avatar_url)
    embed.set_footer(
        text=f"Post on {post.post_timestamp.strftime('%d/%m/%Y')} at {post.post_timestamp.strftime('%-H:%M')}",
        icon_url=INSTA_ICON_URL
    )

    embeds = [embed]

    if not post.post_image_urls:
        return embeds

    embed.set_image(url=post.post_image_urls[0])
    if len(post.post_image_urls) > 1:
        for image in post.post_image_urls[1:]:
            sub_embed = Embed(url=post.post_url)
            sub_embed.set_image(url=image)
            embeds.append(sub_embed)

    return embeds


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
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"{__name__} has been added as a Cog")

    async def request_reply(self, url: str, interaction: Interaction = None, message: Message = None):

        try:
            post_data = await get_info(url, download_videos=True)
        except PostUnavailableException:
            if interaction:
                await respond_or_followup(COG_STRINGS["instagram_warn_inaccessible"], interaction=interaction)
            return False

        embeds = make_embeds(post_data)
        if post_data.post_video_files:
            files = [File(reduce_video(x)) for x in post_data.post_video_files]
            if not files:
                files = MISSING
        else:
            files = MISSING

        if message:
            await message.reply(embeds=embeds, mention_author=False, files=files)
        elif interaction:
            await respond_or_followup(message="", embeds=embeds, interaction=interaction, delete_after=None, files=files)

        for file in post_data.post_video_files:
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
            should_suppress = await self.request_reply(url=match.string, message=message) or should_suppress

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

        if re.search(REGEX_STR, message.content, re.MULTILINE) is None:
            return

        await message.add_reaction(CONFIRM_EMOJI)

        found_urls = re.finditer(REGEX_STR, message.content, re.MULTILINE)
        for _, match in enumerate(found_urls, start=1):
            await self.request_reply(url=match.string, message=message)

        await message.remove_reaction(payload.emoji, payload.member)
        await message.remove_reaction(CONFIRM_EMOJI, guild.me)

    @command(name=COG_STRINGS["instagram_embed_name"], description=COG_STRINGS["instagram_embed_description"])
    @describe(url=COG_STRINGS["instagram_embed_url_describe"])
    @rename(url=COG_STRINGS["instagram_embed_rename"])
    async def embed(self, interaction: Interaction, url: str):
        await interaction.response.defer()
        validate_url = re.search(REGEX_STR, url)
        if not validate_url:
            await respond_or_followup(message=COG_STRINGS["instagram_warn_invalid_url"], interaction=interaction)
            return

        await self.request_reply(url=url, interaction=interaction)


async def setup(bot: Bot):
    import subprocess
    import sys
    subprocess.run([sys.executable, "-m", "playwright", "install"])
    subprocess.run([sys.executable, "-m", "playwright", "install-deps"])
    await bot.add_cog(InstagramEmbed(bot))
    await bot.add_cog(InstagramEmbedAdmin(bot))