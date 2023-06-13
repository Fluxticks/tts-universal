import logging
import os
from random import choice
from datetime import datetime

from discord import Activity, ActivityType, Intents, Object, Status
from discord.ext.commands import Bot
from discord.ext import tasks

from common.io import load_quotes

import glob

__all__ = ["EsportsBot"]
STATUS_HOURS = os.getenv("STATUS_ROTATE_HOURS", 3)
try:
    STATUS_HOURS = int(STATUS_HOURS)
except ValueError:
    STATUS_HOURS = 3


class __EsportsBot(Bot):

    def __init__(self, command_prefix: str, all_messages_ephemeral: bool, *args, **kwargs):
        """Creates a new instance of the the private EsportsBot class.

        Args:
            command_prefix (str): The character(s) to use as the legacy command prefix.
        """
        super().__init__(command_prefix, *args, **kwargs)
        self.logger = logging.getLogger(__name__)
        self.only_ephemeral = all_messages_ephemeral
        self.quote_labels, self.quotes = load_quotes()

    def find_extensions(self):
        extensions = []

        path = os.path.join(os.path.dirname(__file__), "extensions", "*.py")
        for file_path in glob.glob(path):
            file = os.path.basename(file_path).split(".")[0]
            if file != "__init__":
                extensions.append(file)

        return extensions

    async def setup_hook(self):
        """The setup function that is called prior to the bot connecting to the Discord Gateway.
        """

        enabled_extensions = self.find_extensions()

        for extension in enabled_extensions:
            await self.load_extension(f"extensions.{extension}")

        # If in a dev environment, sync the commands to the dev guild.
        if os.getenv("DEV_GUILD_ID"):
            DEV_GUILD = Object(id=os.getenv("DEV_GUILD_ID"))
            self.logger.warning(f"Using guild with id {DEV_GUILD.id} as Development guild!")
            self.tree.copy_global_to(guild=DEV_GUILD)
        else:
            DEV_GUILD = None

        await self.tree.sync(guild=DEV_GUILD)

    async def on_ready(self):
        if not self.update_presence.is_running():
            self.update_presence.start()

    async def update_quotes(self):
        try:
            self.quote_labels, self.quotes = load_quotes()
            await self.update_status()
            return True
        except Exception as e:
            self.logger.error(e)
            return False

    async def update_status(self):
        new_quote = self.generate_quote()
        await self.change_presence(activity=Activity(type=ActivityType.playing, name=new_quote), status=Status.idle)

    def generate_quote(self):
        new_choice = choice(self.quotes)
        choice_quote = new_choice.get("quote")
        choice_author = new_choice.get("quotee")
        timestamp_float = float(new_choice.get("timestamp"))
        timestamp = datetime.fromtimestamp(timestamp_float)
        timestamp_str = timestamp.strftime("%b '%y")
        new_quote = f"\"{choice_quote}\" - {choice_author}, {timestamp_str}"
        return new_quote

    @tasks.loop(hours=STATUS_HOURS)
    async def update_presence(self):
        await self.update_status()


EsportsBot = __EsportsBot(command_prefix=os.getenv("COMMAND_PREFIX"), all_messages_ephemeral=False, intents=Intents.all())
