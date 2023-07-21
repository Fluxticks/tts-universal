import logging
import os
import re

from discord import Embed, File, Interaction, Message
from discord.app_commands import command, default_permissions, describe, rename
from discord.ext.commands import Bot, GroupCog
from tiktokdl.download_video import get_video
from tiktokdl.exceptions import CaptchaFailedException, DownloadFailedException, ResponseParseException
from tiktokdl.video_data import TikTokVideo

from common.discord import respond_or_followup
from common.io import load_cog_toml, reduce_video, MAX_FILE_BYTES
from database.gateway import DBSession
from database.models import TikTokMessagesEnabled

COG_STRINGS = load_cog_toml(__name__)
# MOBILE = r"https\:\/\/vm\.tiktok\.com\/[a-zA-Z0-9]+"
# DESKTOP_REGEX = r"https\:\/\/www\.tiktok\.com\/\@[a-zA-Z0-9]+\/video\/[0-9]+"
REGEX_STR = r"(https\:\/\/vm\.tiktok\.com\/[a-zA-Z0-9]+)|(https\:\/\/www\.tiktok\.com\/\@[a-zA-Z0-9\.\_]+\/video\/[0-9]+)"
TIKTOK_ICON = "https://cdn.pixabay.com/photo/2021/06/15/12/28/tiktok-6338430_1280.png"
INTERACTION_PREFIX = f"{__name__}."


def embed_from_video(video_info: TikTokVideo) -> Embed:
    title = video_info.video_description.split("#")[0]
    description = "#" + "#".join(video_info.video_description.split("#")[1:])
    embed = Embed(color=0xff0050, title=title, description=description, url=video_info.url)

    embed.set_thumbnail(url=video_info.video_thumbnail)
    embed.set_author(name=f"{video_info.author_display_name}", url=video_info.author_url, icon_url=video_info.author_avatar)
    embed.set_footer(
        text=f"Posted on {video_info.timestamp.strftime('%d/%m/%Y')} at {video_info.timestamp.strftime('%-H:%M')}",
        icon_url=TIKTOK_ICON
    )

    embed.add_field(inline=True, name="View Count 👀", value=f"{video_info.view_count:,}")
    embed.add_field(inline=True, name="Like Count ❤️", value=f"{video_info.like_count:,}")
    embed.add_field(inline=True, name="Comment Count 💬", value=f"{video_info.comment_count:,}")
    embed.add_field(inline=True, name="Share Count 🚀", value=f"{video_info.share_count:,}")

    return embed


@default_permissions(administrator=True)
class TikTokEmbedAdmin(GroupCog, name=COG_STRINGS["tiktok_admin_group_name"]):

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name=COG_STRINGS["tiktok_enable_messages_name"], description=COG_STRINGS["tiktok_enable_messages_description"])
    async def enable_on_message(self, interaction: Interaction):
        db_item = DBSession.get(TikTokMessagesEnabled, guild_id=interaction.guild.id)
        if not db_item:
            db_item = TikTokMessagesEnabled(guild_id=interaction.guild.id, is_enabled=True)
            DBSession.update(db_item)
        else:
            db_item.is_enabled = True
            DBSession.create(db_item)
        await respond_or_followup(
            message=COG_STRINGS["tiktok_enable_messages_success"],
            interaction=interaction,
            ephemeral=True
        )

    @command(name=COG_STRINGS["tiktok_disable_messages_name"], description=COG_STRINGS["tiktok_disable_messages_description"])
    async def disable_on_message(self, interaction: Interaction):
        db_item = DBSession.get(TikTokMessagesEnabled, guild_id=interaction.guild.id)
        if not db_item:
            db_item = TikTokMessagesEnabled(guild_id=interaction.guild.id, is_enabled=False)
            DBSession.update(db_item)
        else:
            db_item.is_enabled = False
            DBSession.create(db_item)
        await respond_or_followup(
            message=COG_STRINGS["tiktok_disable_messages_success"],
            interaction=interaction,
            ephemeral=True
        )


class TikTokEmbed(GroupCog, name=COG_STRINGS["tiktok_group_name"]):

    def __init__(self, bot: Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"{__name__} has been added as a Cog")

    @GroupCog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return

        db_item = DBSession.get(TikTokMessagesEnabled, guild_id=message.guild.id)
        if not db_item or not db_item.is_enabled:
            return

        found_urls = re.finditer(REGEX_STR, message.content, re.MULTILINE)
        should_suppress = False

        for _, match in enumerate(found_urls, start=1):
            try:
                video_info = await get_video(match.string)
                file = video_info.file_path
                if os.path.getsize(file) >= MAX_FILE_BYTES:
                    file = reduce_video(file)
                embed = embed_from_video(video_info)
                await message.reply(embed=embed, file=File(f"{file}"), mention_author=False)
                os.remove(file)
                should_suppress = True
            except CaptchaFailedException:
                await message.reply(COG_STRINGS["tiktok_warn_captcha_failed"], mention_author=False)
            except DownloadFailedException:
                await message.reply(COG_STRINGS["tiktok_warn_download_failed"], mention_author=False)

        if should_suppress:
            await message.edit(suppress=True)

    @command(name=COG_STRINGS["tiktok_embed_name"], description=COG_STRINGS["tiktok_embed_description"])
    @describe(url=COG_STRINGS["tiktok_embed_url_describe"])
    @rename(url=COG_STRINGS["tiktok_embed_rename"])
    async def embed(self, interaction: Interaction, url: str):
        await interaction.response.defer()

        found_urls = re.finditer(REGEX_STR, url, re.MULTILINE)
        if not found_urls:
            await respond_or_followup(message=COG_STRINGS["tiktok_warn_invalid_url"], interaction=interaction)
            return

        try:
            video_info = await get_video(url)
            if os.path.getsize(video_info.file_path) >= MAX_FILE_BYTES:
                await interaction.edit_original_response(content=COG_STRINGS["tiktok_file_too_big"])
                file = reduce_video(video_info.file_path)
            else:
                file = video_info.file_path

            embed = embed_from_video(video_info)
            await interaction.edit_original_response(content="", embed=embed, attachments=[File(f"{file}")])
            os.remove(file)
        except CaptchaFailedException:
            await respond_or_followup(COG_STRINGS["tiktok_warn_captcha_failed"], interaction=interaction, delete_after=30)
        except DownloadFailedException:
            await respond_or_followup(COG_STRINGS["tiktok_warn_download_failed"], interaction=interaction, delete_after=30)
        except ResponseParseException:
            await respond_or_followup(COG_STRINGS["tiktok_warn_parse_error"], interaction, delete_after=30)


async def setup(bot: Bot):
    import subprocess
    import sys
    subprocess.run([sys.executable, "-m", "playwright", "install"])
    subprocess.run([sys.executable, "-m", "playwright", "install-deps"])

    await bot.add_cog(TikTokEmbed(bot))
    await bot.add_cog(TikTokEmbedAdmin(bot))
    return
