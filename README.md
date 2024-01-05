# TTS Universal Discord Bot

Dependency Versions:

<div align=left>
    <img src="https://img.shields.io/badge/min%20python%20version-3.9.0-green?style=flat-square" />
    <img src="https://img.shields.io/badge/min%20postgres%20version-11-lightgrey?style=flat-square" />
</div>

This discord bot was written mostly to improve the generated embeds of the common social media links posted.
It also serves as a bot to incorporate other useful features to avoid needing multiple bots that are not FOSS.
This bot is maintained by myself in my freetime and it's features are heavily influenced by the needs of my friends and I 🙂.

# Current Functions

The list below are the current features of the bot and the associated commands for them.

<details>
<summary>GenericCommands</summary>

## GenericCommands

This extension is used for any commands that don't fit into an existing extension.

### Current Commands:

#### /reload-quotes

- Refresh the current list of quotes and change to a new random one in the list.

#### /get-table \<table\>

- Get a simpe view of a given database table.

#### /export-chat \<message-count\> [optional: channel]

- Get a csv of the messages in a given channel. If no channel provided, uses the current one.

</details>

<details>
<summary>VCMusic</summary>

## VCMusic

Provides the ability to play music / YouTube videos in a Voice Channel.
The bot can be controlled either with commands or using the buttons in the designated "music channel".

### Current Commands:

#### /music-admin set-channel \<channel\> [optional: color] [optional: clear-channel] [optional: read-only]

- Sets the channel to define as the music channel.

#### /music play

- Resumes or starts playback.

#### /music pause

- Pauses playback.

#### /music skip-song

- Skips the current song. Stops playback if the last song in the queue.

#### /music shuffle-queue

- Shuffles the current queue.

#### /music add-music

- Opens the dialogue to add one or many songs to the queue.

#### /music view-queue

- Shows the current queue.

#### /music stop

- Stop the current playback.

#### /music volume \<volume\>

- Sets the volume percentage between 0-100

</details>

<details>
<summary>VoiceAdmin</summary>

## VoiceAdmin

VoiceAdmin extension is used to dynamically create and manage Voice Channels, by assigning specific channels to act as parent channels.
When users join parent Voice Channels, a new chil Voice Channel is created, and the user moved to it.
The user has control over the child Voice Channel name, and can limit how many/who can join.

### Current Commands:

#### /vc-admin set-parent \<voice-channel\>

- Set a Voice Channel to be a parent Voice Channel.

#### /vc-admin remove-parent \<voice-channel\>

- Remove a Voice Channel from being a parent Voice Channel.

#### /vc get-parents

- Get the list of current parent Voice Channels.

#### /vc rename \<new-name\>

- Rename your current Voice Channel

#### /vc lock

- Only allow current members to (re)join your Voice Channel.

#### /vc unlock

- Allow anyone to join your Voice Channel again.

#### /vc limit

- Set the member count limit of your Voice Channel.

#### /vc remove-limit

- Remove the member count limit of your Voice Channel.

</details>

<details>
<summary>RedditEmbed</summary>

## RedditEmbed

Improves the content of the embed for a given Reddit link.
By default, message contents will not be checked for a Reddit link and the improved embeds will onl be made for links sent using the command.
This behaviour can be changed using the `reddit-admin` commands to toggle message scanning.

#### /reddit-admin enable-auto-convert

- Enables checking message for the presence of Reddit links.

#### /reddit-admin disable-auto-convert

- Disables checking messages for the presence of Reddit links.

#### /reddit embed \<url\>

- Get a better embed for the given Reddit url.

</details>

<details>
<summary>InstagramEmbed</summary>

## InstagramEmbed

Improves the content of the embed for a given Instagram link.
By default, message contents will not be checked for a Instagram link and the improved embeds will onl be made for links sent using the command.
This behaviour can be changed using the `insta-admin` commands to toggle message scanning.

#### /insta-admin enable-auto-convert

- Enables checking message for the presence of Instagram links.

#### /insta-admin disable-auto-convert

- Disables checking messages for the presence of Instagram links.

#### /insta embed \<url\>

- Get a better embed for the given Instagram url.

</details>

<details>
<summary>TikTokEmbed</summary>

## TikTokEmbed

Improves the content of the embed for a given TikTok link.
By default, message contents will not be checked for a TikTok link and the improved embeds will onl be made for links sent using the command.
This behaviour can be changed using the `tiktok-admin` commands to toggle message scanning.

#### /tiktok-admin enable-auto-convert

- Enables checking message for the presence of TikTok links.

#### /tiktok-admin disable-auto-convert

- Disables checking messages for the presence of TikTok links.

#### /tiktok embed \<url\>

- Get a better embed for the given TikTok url.

</details>

<details>
<summary>RoleReact</summary>

## RoleReact

Implements Role Reaction menus that are easy to create, setup and manage.

#### /rolereact create

- Creates a new empty RoleReact menu.

#### /rolereact add-role \<menu-id\> \<role\> [optional: emoji] [optional: description]

- Add a role to a given menu and optionally assign an emoji and description to the role.

#### /rolereact remove-role \<menu-id\> \<role\>

- Remove a role from a given menu.

#### /rolereact /delete \<menu-id\>

- Delete a given RoleReact menu.

</details>

# Quick Setup Guide

Requirements needed to run:

- Python 3.8
- Pip
- [A postgres 11 database](https://www.postgresql.org/docs/current/admin.html)
  - If using the `DB_OVERRIDE` environment variable, any valid DB schema for SQLAlchemy can be used by providing the correct schema URI. These can be [found here](https://docs.sqlalchemy.org/en/14/dialects/).
- To use the `RedditEmbed` extension, you need to create a Reddit "Personal Use Script" [application](https://www.reddit.com/prefs/apps). If you are unsure, use `http://localhost:8080` for your redirect_uri.
- ffmpeg for Music and Instagram features

1. Clone this repository:

```console
$ git clone https://github.com/Fluxticks/tts-universal.git
```

2. Change into the repo directory:

```console
$ cd tts-universal
```

3. Rename the `secrets.template` to `secrets.env` and set all the variables.

```console
$ nano secrets.env
$ source secrets.env
```

4. Install all the requirements for python:

```bash
pip install -r requirements.txt
```

5. Run the bot:

```bash
python3 src/main.py
```

# Contributing Guide

If you wish to contribute you should also install the requirements in `dev-requirements.txt`.
If you make any changes to this bot please use the following paradigms:

- Ensure that yapf is configured with the configuration defined in `setup.cfg`
  - Optionally also configure flake8 to help with linting
  - This project uses match/case statements, consider using [char101's fork](https://github.com/char101/yapf/releases/tag/v0.31.0) of YAPF until the official fork addresses [the issue](https://github.com/google/yapf/issues/983)
- When adding a new extension consider the following:
  - Create user-facing strings inside of `src/locale/` using the same name as the extension of the filename (eg. for VoiceAdmin.py extension, there exists VoiceAdmin.toml). The strings can then be loaded with `load_cog_strings(__name__)` from `common.io`
  - Extensions should be modular, meaning that they should be able to be enabled/disabled with hindering the function of other extensions
- Any file loading or IO operations should be defined in `src/common/io.py`
