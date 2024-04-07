import logging
import os
from datetime import datetime

from discord import File, Interaction, TextChannel
from discord.app_commands import (
    command,
    describe,
    rename,
    autocomplete,
    Range,
    Transform,
)
from discord.ext.commands import Bot, Cog

from common.io import load_cog_toml
from common.discord import TableTransformer
from database.gateway import DBSession
from database.models import base as TableBase
from database.models import *

COG_STRINGS = load_cog_toml(__name__)
BOTH_SIDE_PADDING = 2


def calculate_column_width(column_data: list[str | int | float]) -> int:
    longest_length = -1
    for item in column_data:
        item_str = str(item)
        length = len(item_str)
        if length > longest_length:
            longest_length = length

    return longest_length


def get_heading_padding(heading_title: str, content_width: int) -> tuple[str, int]:
    heading_length = len(heading_title)
    length_difference = content_width - heading_length
    content_width_change = 0
    if length_difference < 0:
        content_width_change = length_difference * -1
        length_difference = 0

    left_padding = "   " * (length_difference // 2 + BOTH_SIDE_PADDING)
    right_padding = "  " * (length_difference // 2 + BOTH_SIDE_PADDING)

    return (
        f"__**{left_padding}{heading_title}{right_padding}**__",
        content_width_change,
    )


def get_padded_cell_content(cell_content: str, column_width: int) -> str:
    cell_content = str(cell_content)
    column_width = column_width - len(cell_content)
    left_padding = "   " * (column_width // 2 + BOTH_SIDE_PADDING)
    right_padding = "   " * (column_width // 2 + column_width % 2 + BOTH_SIDE_PADDING)
    return f"{left_padding}{cell_content}{right_padding}"


def pretty_print_table(
    rows: (
        list[VoiceAdminParent]
        | list[VoiceAdminChild]
        | list[MusicChannels]
        | list[RedditMessagesEnabled]
        | list[InstagramMessagesEnabled]
        | list[TikTokMessagesEnabled]
    ),
):
    if not rows:
        return COG_STRINGS["db_tables_warn_empty"]

    item_type = rows[0]
    item_columns = [x for x in item_type.__dict__ if not x.startswith("_")]
    column_widths = {
        x: calculate_column_width([getattr(y, x) for y in rows]) for x in item_columns
    }
    table_titles = {
        x: get_heading_padding(x, column_widths.get(x)) for x in column_widths
    }

    output = "​__**   **__​"
    output += "**|**".join([x[0] for x in table_titles.values()])
    for item in rows:
        row_string = "\n>"
        for idx, column in enumerate(item_columns):
            column_width = column_widths.get(column)
            _, width_change = table_titles.get(column)
            column_width += width_change
            cell_content = get_padded_cell_content(getattr(item, column), column_width)
            row_string += (
                f"{cell_content}{'**|**' if idx < len(item_columns) - 1 else ''}"
            )

        output += row_string

    return output


class GenericCommands(Cog):

    def __init__(self, bot: Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    @command(
        name=COG_STRINGS["reload_quotes_name"],
        description=COG_STRINGS["reload_quotes_description"],
    )
    async def reload_quotes(self, interaction: Interaction):
        if str(interaction.user.id) != str(os.getenv("OWNER_USER_ID")):
            await interaction.response.send_message(
                COG_STRINGS["error_user_not_owner"], ephemeral=True
            )
            return

        if await self.bot.update_quotes():
            await interaction.response.send_message(
                COG_STRINGS["reload_quotes_success"], ephemeral=True, delete_after=5.0
            )
        else:
            await interaction.response.send_message(
                COG_STRINGS["reload_quotes_failed"], ephemeral=True
            )

    @command(
        name=COG_STRINGS["db_tables_name"],
        description=COG_STRINGS["db_tables_description"],
    )
    @describe(table=COG_STRINGS["db_tables_table_describe"])
    @rename(table=COG_STRINGS["db_tables_table_rename"])
    @autocomplete(table=TableTransformer.autocomplete)
    async def get_db_table(
        self, interaction: Interaction, table: Transform[TableBase, TableTransformer]
    ):
        if str(interaction.user.id) != str(os.getenv("OWNER_USER_ID")):
            await interaction.response.send_message(
                COG_STRINGS["error_user_not_owner"], ephemeral=True
            )
            return

        table_data = DBSession.list(table=table)
        await interaction.response.send_message(
            pretty_print_table(table_data), ephemeral=True
        )

    @command(
        name=COG_STRINGS["export_chat_name"],
        description=COG_STRINGS["export_chat_description"],
    )
    @describe(
        count=COG_STRINGS["export_chat_count_describe"],
        channel=COG_STRINGS["export_chat_channel_describe"],
    )
    @rename(
        count=COG_STRINGS["export_chat_count_rename"],
        channel=COG_STRINGS["export_chat_channel_rename"],
    )
    async def export_chat(
        self,
        interaction: Interaction,
        count: Range[int, 1, 100],
        channel: TextChannel = None,
    ):
        if str(interaction.user.id) != str(os.getenv("OWNER_USER_ID")):
            await interaction.response.send_message(
                COG_STRINGS["error_user_not_owner"], ephemeral=True
            )
            return

        if not channel:
            channel = interaction.channel

        channel_permissions = channel.permissions_for(interaction.guild.me)
        if (
            not channel_permissions.view_channel
            or not channel_permissions.read_messages
            or not channel_permissions.read_message_history
        ):
            await interaction.response.send_message(
                COG_STRINGS["export_channel_not_viewable_error"].format(
                    channel=channel.mention
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        date = datetime.now().strftime("%d_%m_%Y")
        file_name = f"Export of #{channel.name} on {date}.csv"

        with open(file_name, "w") as f:
            f.write("author,timestamp,message\n")
            async for message in channel.history(limit=count):
                author = message.author
                timestamp = message.created_at
                contents = message.content.replace('"', "'").replace("\n", "\\n")

                for member in message.mentions:
                    contents = contents.replace(member.mention, f"@{member!s}")
                    contents = contents.replace(f"<@!{member.id}>", f"@{member!s}")

                for role in message.role_mentions:
                    contents = contents.replace(role.mention, f"@{role.name}")
                    contents = contents.replace(f"<@&{role.id}>", f"@{role.name}")

                for channel in message.channel_mentions:
                    contents = contents.replace(channel.mention, f"#{channel.name}")

                if message.attachments:
                    contents += f" [Attachments: {','.join([x.url for x in message.attachments])}]"

                line = f'{author!s},{timestamp.timestamp()},"{contents}"\n'
                f.write(line)

        await interaction.followup.send(
            content=COG_STRINGS["export_chat_done"].format(count=count),
            ephemeral=True,
            file=File(f"{file_name}"),
        )

        os.remove(file_name)


async def setup(bot: Bot):
    await bot.add_cog(GenericCommands(bot))
