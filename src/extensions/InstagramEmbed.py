import asyncio
import logging
import os
import re

from discord import Embed, File, Interaction, Message
from discord.app_commands import command, default_permissions, describe, rename
from discord.ext.commands import Bot, GroupCog
from discord.utils import MISSING
from instagramdl.exceptions import (InstagramInaccessibleException, PostUnavailableException)
from instagramdl.get_post import get_info
from instagramdl.post_data import InstagramPost

from common.discord import respond_or_followup
from common.io import load_cog_toml, stitch_videos, MAX_FILE_BYTES
from database.gateway import DBSession
from database.models import InstagramMessagesEnabled
from common.io import reduce_video

COG_STRINGS = load_cog_toml(__name__)
REGEX_STR = r"https\:\/\/www\.instagram\.com\/(reel|p)\/[a-zA-Z0-9]+"
REQUEST_TIMER = 5
MAX_POST_DESCRIPTION_LENGTH = 360
INSTA_COLOUR = 0xE1306C
INSTA_ICON_URL = "https://images-ext-2.discordapp.net/external/C6jCIKlXguRhfmSp6USkbWsS11fnsbBgMXiclR2R4ps/https/www.instagram.com/static/images/ico/favicon-192.png/68d99ba29cc8.png"


def embeds_from_post(post: InstagramPost) -> list[Embed]:
    if len(post.post_description) > MAX_POST_DESCRIPTION_LENGTH:
        next_space = post.post_description.index(' ', MAX_POST_DESCRIPTION_LENGTH)
        if next_space == -1:
            next_space = post.post_description.index('.', MAX_POST_DESCRIPTION_LENGTH)

        description = f"{post.post_description[:next_space]}\n\n... Read more [on instagram]({post.post_url})"
    else:
        description = post.post_description

    main_embed = Embed(
        title=f"@{post.author_display_name}'{'' if post.author_display_name.endswith('s') else 's'} Post",
        description=description,
        url=post.post_url,
        color=INSTA_COLOUR
    )

    main_embed.set_author(name=f"@{post.author_username}", url=post.author_profile_url, icon_url=post.author_avatar_url)
    main_embed.set_footer(
        text=f"Post on {post.post_timestamp.strftime('%d/%m/%Y')} at {post.post_timestamp.strftime('%-H:%M')}",
        icon_url=INSTA_ICON_URL
    )

    if len(post.post_image_urls) == 1:
        main_embed.set_image(url=post.post_image_urls[0])
        return [main_embed]

    if len(post.post_image_urls) > 1:
        main_embed.set_image(url=post.post_image_urls[0])
        embeds = [main_embed]
        for image in post.post_image_urls[1:]:
            alt_embed = Embed(url=post.post_url)
            alt_embed.set_image(url=image)
            embeds.append(alt_embed)
        return embeds

    if len(post.post_video_files) == 1:
        main_embed.set_image(url=post.post_video_urls[0].get("thumbnail"))
        return [main_embed]

    if len(post.post_video_files) > 1:
        main_embed.set_image(url=post.post_video_urls[0].get("thumbnail"))
        embeds = [main_embed]
        for video in post.post_video_urls[1:]:
            alt_embed = Embed(url=post.post_url)
            alt_embed.set_image(url=video.get("thumbnail"))
            embeds.append(alt_embed)
        return embeds

    return [main_embed]


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

    @GroupCog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return

        db_item = DBSession.get(InstagramMessagesEnabled, guild_id=message.guild.id)
        if not db_item or not db_item.is_enabled:
            return

        found_urls = re.finditer(REGEX_STR, message.content, re.MULTILINE)
        for _, match in enumerate(found_urls, start=1):
            await self.post_response(url=match.string, message=message)

    async def post_response(self, url: str, message: Message = None, interaction: Interaction = None):

        try:
            post = await get_info(url)
        except InstagramInaccessibleException as e:
            if message:
                return

            await respond_or_followup(
                message=COG_STRINGS["instagram_warn_inaccessible"].format(url=e.url),
                interaction=interaction,
                delete_after=10
            )
            return
        except PostUnavailableException as e:
            if message:
                return

            await respond_or_followup(
                message=COG_STRINGS["instagram_warn_post_unavailable"].format(url=e.url),
                interaction=interaction,
                delete_after=10
            )
            return

        embeds = embeds_from_post(post)

        if post.post_video_files:
            if len(post.post_video_files) > 1:
                video = stitch_videos(post.post_video_files)
                post.post_video_files.append(video)
            else:
                video = post.post_video_files[0]

            file_size = os.path.getsize(video)
            if file_size >= MAX_FILE_BYTES:
                if interaction:
                    await interaction.edit_original_response(content=COG_STRINGS["instagram_file_too_big"])
                video = reduce_video(video)
                post.post_video_files[-1] = video

            attachments = [File(f"{video}")]
        else:
            attachments = MISSING

        if message:
            if not message.flags.suppress_embeds:
                await message.edit(suppress=True)
            await message.reply(embeds=embeds, file=attachments[0], mention_author=False)
        elif interaction:
            await interaction.edit_original_response(content="", embeds=embeds, attachments=attachments)

        for file in post.post_video_files:
            os.remove(file)

    @command(name=COG_STRINGS["instagram_embed_name"], description=COG_STRINGS["instagram_embed_description"])
    @describe(url=COG_STRINGS["instagram_embed_url_describe"])
    @rename(url=COG_STRINGS["instagram_embed_rename"])
    async def embed(self, interaction: Interaction, url: str):
        await interaction.response.defer()
        validate_url = re.search(REGEX_STR, url)
        if not validate_url:
            await respond_or_followup(message=COG_STRINGS["instagram_warn_invalid_url"], interaction=interaction)
            return

        await self.post_response(url=url, interaction=interaction)


async def setup(bot: Bot):
    import subprocess
    import sys
    subprocess.run([sys.executable, "-m", "playwright", "install"])
    subprocess.run([sys.executable, "-m", "playwright", "install-deps"])
    await bot.add_cog(InstagramEmbed(bot))
    await bot.add_cog(InstagramEmbedAdmin(bot))