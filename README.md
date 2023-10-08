# <div align="center">ListenTUI</div>

<div align="center">A LISTEN.moe TUI application</div>

![image of application](.assets/main.png)

---

# Glossary

- [Installation](#installation)
- [Usage Options](#usage-options)
- [Configuration](#configuration)
  - [System](#system)
  - [Keybind](#keybind)
  - [Display](#display)
  - [Rich Presence](#rich-presence)
  - [Player](#player)
- [Terminal](#terminal)
- [Additional Features](#additional-features)
- [Building](#build)

---

# Installation

## Requirements

- `libmpv`

The program uses mpv to playback audio and as such requires `libmpv` to be installed on your system.

For Linux user. Install `libmpv` through your favorite package manager. You may also want to try `mpv-devel` or `mpv-libs` if the program can't find `libmpv`.

**If you're using the non-portable version.**

For Windows user, regular mpv player binaries do not contain `libmpv`.

1. Download `libmpv` at [libmpv](https://sourceforge.net/projects/mpv-player-windows/files/libmpv/)
2. Find `libmpv.dll` and rename it to `mpv-2.dll`
3. Add `mpv-2.dll into %PATH%`

- `A nerd font`

For the icons, a nerd font font pack is required, get them at [Nerd Font](https://www.nerdfonts.com/), remember to set your terminal font aswell.

## How to run

#### Linux

1. Download the latest binary from releases `listentui`
2. Move file to $PATH
3. Run `listentui`

#### Windows

1. Download the latest executable from releases `listentui.exe` or `listentui_portable.exe`
2. Move file to %PATH%
3. Run `listentui` in any terminal

Alternatively, double clicking the executable works too (although some icons might be missing)

#### Universal

1. Have python version greater than or equal to `3.11.1`
2. Download the `listentui*.whl` file
3. In a terminal, run `pip install` on the whl file
4. Run `listentui`

# Usage Options

```sh
listentui [OPTIONS]
```

## General Options

```txt
-h, --help        Print this help text and exit
-c, --config      Path to config file
-l, --log         Enable logging to file
--bypass          Bypass and clears the instance lock
```

# Configuration

Configuration is done through `config.toml`. You can find the default configuration here at [config.toml](https://github.com/kwevin/Listen.TUI/blob/main/config.toml)

Base on your distro, this is located at:

- Linux: `$XDG_CONFIG_HOME/listentui/config.toml` or `$HOME/.config/listentui/config.toml`
- Windows: `%APPDATA%\listentui\config.toml`

#### System

- `username`: username used to log into LISTEN.moe
- `password`: password used to log into LISTEN.moe
- `instance_lock`: limit the running instance to one

#### Keybind

Tip: You can use identifiers such as `${SPACE}`, more at [Window](https://github.com/magmax/python-readchar/blob/master/readchar/_win_key.py), [Linux](https://github.com/magmax/python-readchar/blob/master/readchar/_posix_key.py)

- `play_pause`: toggle play/pause
- `lower_volume`: lower the volume of the player
- `raise_volume`: raise the volume of the player
- `lower_volume_fine`: lower the volume by 1
- `raise_volume_fine`: raise the volume by 1
- `favourite_song`: favourite the current playing song (only when logged in)
- `restart_player`: restart the player
- `open_terminal`: open the integrated terminal

#### Display

- `romaji_first`: use romaji (if any) before original
- `separator`: separator between artists

#### Rich Presence

- `enable_rpc`: enable rich presence integration
- `default_placeholder`: placeholder for when text field falls below the two character limit specified by discord
- `use_fallback`: use a fallback image if there isnt one
- `fallback`: the fallback image, has to be a link that discord can access (alternatively, use "fallback2" for [LISTEN.moe](https://listen.moe/_nuxt/img/logo-square-64.248c1f3.png) icon)
- `use_artist`: use the artist image instead if no album image is found
- `detail`: the title of the presence, can take in `${keys}`
- `state`: the subtitle of the presence, can take in `${keys}`
- `large_text`: the text that is shown when hovering over the large image, can take in `${keys}`
- `small_text`: the text that is shown when hovering over the small image, can take in `${keys}`
- `show_time_left`: show the remaining time (if applicable) for the current playing song
- `show_small_image`: show the artist as a small image (if applicable)

Available `${keys}` includes:

- `id`: id of the current song
- `title`: title of the current song
- `source`: source of the current song, note: this is wrapped in brackets `"[source]"`
- `source_image`: name of the source image
- `artist`: artists of the current song
- `artist_image`: name of the first artist image
- `album`: album name of the current song
- `album_image`: name of the album image

#### Player

- `volume_step`: the volume used by `raise/lower_volume`
- `restart_timeout`: the timeout (secs) to restart the player when there is no playback
- `[player.mpv_options]`: additional options that can be passed into mpv (the default is recommended), see [mvp options](https://mpv.io/manual/master/#options) for more info

# Terminal

![image of terminal](.assets/terminal.png)

The terminal allows user to query different information through LISTEN.moe

## Usage

```txt
{help,clear,reset,eval,search,history,album,artist,song,preview,pv,user,character,source,download,check_favorite,cf,check,favorite,f}

help                        Print help for given command
clear                       Clear the console output
reset                       Reset console history, useful when there's too much lag, see issues#1
eval                        Evaluate a python expression
search                      Search for a song
history                     Show previously played history
album                       Fetch info on an album
artist                      Fetch info on an artist
song                        Fetch info on a song
preview (pv)                Preview a portion of the song audio
user                        Fetch info on an user
character                   Fetch info on a character
source                      Fetch info on a source
check_favorite (cf, check)  Check if the song has been favorited
favorite (f)                Favorite a song
(WIP)download               Download a song
```

If you're unsure, run `help {command}` for more information about the command

# Additional features

### `Dynamic Range Compression`

Mpv supports dynamic range compression (lower the sounds at higher volume and raise the sound at lower volume), if you want to use drc, add this to `mpv_options` in config.

```toml
af = "acompressor=ratio=4,loudnorm=I=-16:LRA=11:TP=-1.5" 
```

# Build

Requires:

- `python3.11.1^`
- `poetry`
- `mpv-2.dll` in the root directory

```sh
poetry shell
poetry install
poetry build
poetry run python 'utils/build.py'
```

#### Install

This is to install the project as a pip library, allowing the program to be called from any terminal with `listentui`

```sh
poetry -vvv install --only-root --compile
```

build files are located in `dist`

# Credits

- `yt-dlp`: For their pyinstaller build
