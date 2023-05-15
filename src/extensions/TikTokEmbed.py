import logging
import os
import random
import re
from datetime import datetime
from uuid import uuid4

from discord import Embed, File, Interaction, Message
from discord.app_commands import command, default_permissions, describe, rename
from discord.ext.commands import Bot, GroupCog
from TikTokApi import TikTokApi
from TikTokApi.helpers import extract_video_id_from_url

from common.discord import respond_or_followup
from common.io import load_cog_toml
from database.gateway import DBSession
from database.models import TikTokMessagesEnabled

COG_STRINGS = load_cog_toml(__name__)
# MOBILE = r"https\:\/\/vm\.tiktok\.com\/[a-zA-Z0-9]+"
# DESKTOP_REGEX = r"https\:\/\/www\.tiktok\.com\/\@[a-zA-Z0-9]+\/video\/[0-9]+"
REGEX_STR = r"(https\:\/\/vm\.tiktok\.com\/[a-zA-Z0-9]+)|(https\:\/\/www\.tiktok\.com\/\@[a-zA-Z0-9\.\_]+\/video\/[0-9]+)"
TIKTOK_ICON = "https://cdn4.iconfinder.com/data/icons/social-media-flat-7/64/Social-media_Tiktok-1024.png"
INTERACTION_PREFIX = f"{__name__}."


def get_video(url: str):
    video_id = extract_video_id_from_url(url)
    did = str(random.randint(10000, 999999999))
    with TikTokApi(use_test_endpoints=True, custom_device_id=did) as api:
        video = api.video(id=video_id)
        video_info = video.as_dict
        video_data = video.bytes()
    file = f"{uuid4()}.mp4"
    with open(f"{file}", "wb") as f:
        f.write(video_data)
    video_info["localfile"] = file
    return video_info


def video_info_embed(video_data: dict):
    author = video_data.get("author")
    author_url = f"https://www.tiktok.com/@{author.get('uniqueId')}/"
    video_url = f"{author_url}video/{video_data.get('id')}"
    desc = video_data.get("desc")
    hash_index = desc.index("#")
    title = desc[:hash_index]
    description = desc[hash_index - 1:]

    embed = Embed(title=title, description=description, url=video_url, color=0xff0050)
    embed.set_author(name=author.get("nickname"), icon_url=author.get("avatarThumb"), url=author_url)
    timestamp = video_data.get("createTime")
    timestamp_obj = datetime.fromtimestamp(timestamp)
    embed.set_footer(icon_url=TIKTOK_ICON, text=f"Posted on {timestamp_obj.strftime('%d/%m/%Y')}")
    embed.set_thumbnail(url=video_data.get("video").get("originCover"))

    statistics = video_data.get("stats")
    embed.add_field(inline=True, name="View Count 👀", value=f"{statistics.get('playCount'):,}")
    embed.add_field(inline=True, name="Like Count ❤️", value=f"{statistics.get('diggCount'):,}")
    embed.add_field(inline=True, name="Comment Count 💬", value=f"{statistics.get('commentCount'):,}")
    embed.add_field(inline=True, name="Share Count 🚀", value=f"{statistics.get('shareCount'):,}")

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
            video_info = get_video(match.string)
            file = video_info.get("localfile")
            embed = video_info_embed(video_info)
            await message.reply(embed=embed, file=File(f"{file}"), mention_author=False)
            os.remove(file)
            should_suppress = True

        if should_suppress:
            await message.edit(suppress=True)

    @command(name=COG_STRINGS["tiktok_embed_name"], description=COG_STRINGS["tiktok_embed_description"])
    @describe(url=COG_STRINGS["tiktok_embed_url_describe"])
    @rename(url=COG_STRINGS["tiktok_embed_rename"])
    async def embed(self, interaction: Interaction, url: str):
        await interaction.response.defer()

        found_urls = re.finditer(REGEX_STR, url, re.MULTILINE)
        if not found_urls:
            await respond_or_followup(message=COG_STRINGS["warn_invalid_url"], interaction=interaction)
            return

        video_info = get_video(url)
        file = video_info.get("localfile")
        embed = video_info_embed(video_info)

        await respond_or_followup(message="", interaction=interaction, embed=embed, file=File(f"{file}"), delete_after=None)
        os.remove(file)


async def setup(bot: Bot):
    import nest_asyncio
    nest_asyncio.apply()
    import subprocess
    subprocess.run(["python3", "-m", "playwright", "install"])
    subprocess.run(["python3", "-m", "playwright", "install-deps"])

    await bot.add_cog(TikTokEmbed(bot))
    await bot.add_cog(TikTokEmbedAdmin(bot))
