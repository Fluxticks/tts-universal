import re
from datetime import datetime
from typing import Any, List, Union

from discord import Colour, Interaction, Message, Role, ScheduledEvent
from discord.abc import GuildChannel
from discord.app_commands import Choice, Transformer
from discord.app_commands.models import Choice
from discord.interactions import Interaction


async def respond_or_followup(
    message: str,
    interaction: Interaction,
    ephemeral: bool = False,
    delete_after: float = 10,
    **kwargs
):
    if interaction.response.is_done():
        message = await interaction.followup.send(content=message, ephemeral=ephemeral, **kwargs)
        if delete_after:
            await message.delete(delay=delete_after)
        return False
    else:
        await interaction.response.send_message(message, ephemeral=ephemeral, delete_after=delete_after, **kwargs)
        return True


def make_colour_list():
    all_vars = dir(Colour)
    colour_vars = dir(Colour)

    def valid_key(string: str):
        starts_with = ["_", "from_", "to_"]
        ends_with = ["_gray"]
        start_end_with = [{"start": "__", "end": "__"}]

        for req in start_end_with:
            if string.startswith(req["start"]) and string.endswith(req["end"]):
                return False

        for req in starts_with:
            if string.startswith(req):
                return False

        for req in ends_with:
            if string.endswith(req):
                return False

        return True

    for key in all_vars:
        if not valid_key(key) or key in ["value", "r", "g", "b"]:
            colour_vars.remove(key)
    return colour_vars


VALID_COLOUR_NAMES = make_colour_list()


def primary_key_from_object(object: Union[Role, GuildChannel, ScheduledEvent, Message]):
    return int(f"{object.guild.id % 1000}{object.id % 1000}")


class ColourTransformer(Transformer):
    """The transformer that provides named colour autocompletion and converts the corresponding Color object.
    Also provides the ability to convert a hex colour string to a Color object from the given string.

    Returns:
        Color: The Color object of the colour string or hex string given.
    """

    async def autocomplete(self, interaction: Interaction, current_str: str) -> List[Choice[str]]:
        return [
            Choice(name=colour.replace("_",
                                       " ").capitalize(),
                   value=colour) for colour in VALID_COLOUR_NAMES if current_str.lower() in colour.lower()
        ][:25]

    async def transform(self, interaction: Interaction, input_string: str) -> Colour:
        if input_string.startswith("#"):
            try:
                return Colour.from_str(input_string)
            except ValueError:
                return Colour.default()
        elif input_string in VALID_COLOUR_NAMES:
            return getattr(Colour, input_string)()
        else:
            try:
                manual_name = input_string.replace(" ", "_").strip().lower()
                colour = getattr(Colour, manual_name)
                return colour()
            except AttributeError:
                return Colour.default()


class TableTransformer(Transformer):

    async def autocomplete(self, interaction: Interaction, value: str) -> List[Choice[str]]:
        from database.models import __all__ as table_list

        filtered_list = [x for x in table_list if value.lower() in x.lower()][:25]
        choices = [Choice(name=x, value=x) for x in filtered_list]
        return choices

    async def transform(self, interaction: Interaction, value: Any) -> Any:
        import database.models as models
        models_dict = models.__dict__
        model = models_dict.get(value)
        return model