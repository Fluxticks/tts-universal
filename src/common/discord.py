import re
from datetime import datetime
from typing import Any, List, Union

from discord import (
    Colour,
    Interaction,
    Message,
    Role,
    ScheduledEvent,
    Guild,
    PartialEmoji,
)
from discord.abc import GuildChannel
from discord.app_commands import Choice, Transformer
from discord.app_commands.models import Choice
from discord.interactions import Interaction
from discord.ui import View

from database.models import RoleReactMenus
from database.gateway import DBSession


async def respond_or_followup(
    message: str,
    interaction: Interaction,
    ephemeral: bool = False,
    delete_after: float = 10,
    **kwargs,
):
    if interaction.response.is_done():
        message = await interaction.followup.send(
            content=message, ephemeral=ephemeral, **kwargs
        )
        if delete_after:
            await message.delete(delay=delete_after)
        return False
    else:
        await interaction.response.send_message(
            message, ephemeral=ephemeral, delete_after=delete_after, **kwargs
        )
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

    async def autocomplete(
        self, interaction: Interaction, current_str: str
    ) -> List[Choice[str]]:
        return [
            Choice(name=colour.replace("_", " ").capitalize(), value=colour)
            for colour in VALID_COLOUR_NAMES
            if current_str.lower() in colour.lower()
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

    async def autocomplete(
        self, interaction: Interaction, value: str
    ) -> List[Choice[str]]:
        from database.models import __all__ as table_list

        filtered_list = [x for x in table_list if value.lower() in x.lower()][:25]
        choices = [Choice(name=x, value=x) for x in filtered_list]
        return choices

    async def transform(self, interaction: Interaction, value: Any) -> Any:
        import database.models as models

        models_dict = models.__dict__
        model = models_dict.get(value)
        return model


class RoleReactMenuTransformer(Transformer):
    """The autocomplete transformer to provide a list of RoleReact menu IDs for a given guild.

    Returns:
        List[Choice[str]]: A list of exisitng menu IDs in a guild.
    """

    async def autocomplete(
        self, interaction: Interaction, value: Union[int, float, str]
    ) -> List[Choice[str]]:
        guild_role_menus = DBSession.list(RoleReactMenus, guild_id=interaction.guild.id)
        if value:
            choices = [
                Choice(name=f"Role menu ID: {x.message_id}", value=str(x.message_id))
                for x in guild_role_menus
                if value in str(x.message_id)
            ]
        else:
            choices = [
                Choice(name=f"Role menu ID: {x.message_id}", value=str(x.message_id))
                for x in guild_role_menus
            ]
        return choices[:25]


def get_roles_from_view(view: View, guild: Guild) -> list[Role]:
    """Get a list of roles from a View for a RoleReact message.

    Args:
        view (View): The view containing the Select items with role options.
        guild (Guild): The guild in which the view/message exist.

    Returns:
        list[Role]: A list of roles that are the options in the select menu(s).
    """
    if not view:
        return []

    roles = []
    guild_roles = {str(x.id): x for x in guild.roles}
    for child in view.children:
        for option in child.options:
            roles.append(guild_roles.get(option.value))
    return roles


def get_menu_id_from_args(interaction: Interaction) -> int:
    """Get the given menu ID from the already supplied arguments of an interaction.

    Args:
        interaction (Interaction): The interaction containing the already given menu ID

    Returns:
        int: The menu ID of the menu given.
    """
    interaction_options = {"options": []}
    for item in interaction.data.get("options"):
        if item.get("type") == 1:
            interaction_options = item
            break

    for argument in interaction_options.get("options"):
        if argument.get("name") == "menu-id":
            return argument.get("value")
    return 0


class RoleReactRoleTransformer(Transformer):
    """The autocomplete transformer to provide a list of Roles that are in the already provided RoleReact menu.

    Returns:
        List[Choice[str]]: A list of Roles for the RoleReact menu currently chosen.
    """

    async def autocomplete(
        self, interaction: Interaction, value: str
    ) -> List[Choice[str]]:
        menu_id = get_menu_id_from_args(interaction)
        if not DBSession.get(
            RoleReactMenus, guild_id=interaction.guild.id, message_id=menu_id
        ):
            return []

        message = await interaction.channel.fetch_message(menu_id)
        view = View.from_message(message)
        menu_roles = get_roles_from_view(view, interaction.guild)
        if value:
            choices = [
                Choice(
                    name=f"{'' if x.name.startswith('@') else '@'}{x.name}",
                    value=str(x.id),
                )
                for x in menu_roles
                if value.replace("@", "") in x.name
            ]
        else:
            choices = [
                Choice(
                    name=f"{'' if x.name.startswith('@') else '@'}{x.name}",
                    value=str(x.id),
                )
                for x in menu_roles
            ]

        return choices[:25]


class EmojiTransformer(Transformer):

    async def transform(self, interaction: Interaction, value: str) -> PartialEmoji:
        return PartialEmoji.from_str(value)


def get_events(guild: Guild, event_dict: dict, value: str) -> List[Choice[str]]:
    filtered_events = []
    guild_events = [
        event_dict.get(x) for x in event_dict if event_dict.get(x).guild_id == guild.id
    ]
    if value.isdigit():
        filtered_events = [x for x in guild_events if value in str(x.event_id)]
    else:
        filtered_events = [x for x in guild_events if value.lower() in x.name.lower()]

    choices = [
        Choice(name=f"{x.name} ({x.event_id})", value=str(x.event_id))
        for x in filtered_events
    ][:25]
    return choices
