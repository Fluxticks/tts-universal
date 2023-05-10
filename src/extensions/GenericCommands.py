from discord.ext.commands import Bot, Cog
from discord import Interaction
import logging
from common.io import load_cog_toml
from discord.app_commands import default_permissions, command

COG_STRINGS = load_cog_toml(__name__)


class GenericCommands(Cog):

    def __init__(self, bot: Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    @command(name=COG_STRINGS["reload_quotes_name"], description=COG_STRINGS["relaod_quotes_description"])
    @default_permissions(administrator=True)
    async def reload_quotes(self, interaction: Interaction):
        if await self.bot.update_quotes():
            await interaction.response.send_message(COG_STRINGS["reload_quotes_success"], ephemeral=True, delete_after=5.0)
        else:
            await interaction.response.send_message(COG_STRINGS["reload_quotes_failed"], ephemeral=True)


async def setup(bot: Bot):
    await bot.add_cog(GenericCommands(bot))