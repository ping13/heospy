# Control an HEOS player with a Python script

## Requirements

You have an [HEOS][] speaker in your local network and Python 2.7 or
Python 3.

## Usage

0. Install the package with 

```
python setup.py install
```

1. Create a `config.json` file, which may reside in the current directory, in
   `$HOME/.heospy` or in a directory wich is specified by the environment
   variable `$HEOSPY_CONF`. The config file contains the name of the lead
   [HEOS][] player you want to control and the username and password of your
   [HEOS account][]. See `example-config.json` for an example.

2. Run the script for the first time to see how this works:

        $ heos_player
        2017-02-12 20:32:29,880 INFO Starting to discover your HEOS player 'Living room' in your local network
        2017-02-12 20:32:36,824 INFO Found 'Living room' in your local network
        $
        
3. Now you can call any command from the [CLI specs][specs], see also `docs/`
   folder. Additional arguments are given with `-p`. The player id will be
   automatically submitted. Some examples:

        heos_player player/toggle_mute
        heos_player player/set_volume -p level=19
        heos_player player/play_preset -p preset=3
        heos_player player/set_play_state -p state=stop
        heos_player group/toggle_mute
        heos_player group/toggle_mute -p gid=-1352658342

    Use the flag `--help` for a detailed help.

[specs]: http://rn.dmglobal.com/euheos/HEOS_CLI_ProtocolSpecification.pdf
[HEOS]: http://heoslink.denon.com
[HEOS account]: http://denon.custhelp.com/app/answers/detail/a_id/1968

## Parsing the response from HEOS

A `heos_player` returns a JSON object which directly comes from the HEOS
player, like:

    python heospy/heos_player.py player/get_volume
    
which gives something like

    {
        "heos": {
            "message": "pid=-1352658342&level=13", 
            "command": "player/get_volume", 
            "result": "success"
        }
    }

Unfortunately, HEOS hides some of the results in the `message` property (here:
the volume level of the main player). `heospy` parses the message string and
puts the contained attributes in a seperate property `heos_message_parsed`:

     {
       "heos_message_parsed": {
         "pid": "-1352658342", 
         "level": "13"
       }, 
       "heos": {
         "message": "pid=-1352658342&level=13", 
         "command": "player/get_volume", 
         "result": "success"
       }
     }

With [`jq`](https://stedolan.github.io/jq/), you can directly parse the result
in the command line:

     $ python heospy/heos_player.py player/get_volume | jq .heos_message_parsed.level
     "13"

## Main player setting and referencing other players by name

The class `HeosPlayer` assumes a main HEOS player, stored in the config
file. For commands starting with `player/`, we assume that this player should
be used, otherwise you need to specify the player id explicitly as a parameter
`pid`. 

You may also specify a player by name by using the fake parameter `pname`: the
class `HeosPlayer` will search for a player with the given name and will try to
translate it to a player id, e.g. with:

    $ python heospy/heos_player.py -l DEBUG player/clear_queue -p pname=Küche
    [...]
    2019-01-02 20:47:35,314 INFO Issue command 'player/get_queue' with arguments {"pname": "Küche"}
    2019-01-02 20:47:35,314 DEBUG translated player name 'Kitchen' to pid=-2122099729
    2019-01-02 20:47:35,314 DEBUG telnet request heos://player/get_queue?dummy=1&pid=-2122099729
    [...]
    {
      "payload": [], 
      "heos": {
        "message": "dummy=1&pid=-2122099729&returned=0&count=0", 
        "command": "player/get_queue", 
        "result": "success"
      }
    }

If the main player is a lead player in a group, this group is also the main
group for commands starting with `group/`. Again, you can override this setting
be explicitly mention the group id as a parameter. You may also specify the
group by name with a fake parameter `gname`.

## Rudimentary scripting of HEOS commands

You can also execute a sequence of commands at once. The sequence can be given
in a text file:

    heos_player -i cmds.txt

An example for `cmds.txt` is:

    system/heart_beat
    # let's set a volume
    player/set_volume level=10
    # let's check if the volume is correct
    player/get_volume

Note that comments are possible and start with a `#`. There is also a special
command `wait`, which waits a number of seconds until the next command is
played.

    # play an MP3 file, wait 360 seconds and then turn the mute button on
    player/play_stream pname=Küche url=http://example.com/example.mp3
    wait 360 
    player/set_mute -p state=on
    
You can also get the sequence of commands from `stdin`:

    printf "system/heart_beat\nplayer/set_volume level=10\nplayer/get_volume" | heos_player -i -

## Usage with Raspberry Pi and Kodi

If you have [OSMC][] or any other [Kodi Media center][Kodi] implementation on
your [Raspberry Pi][raspi], you can map certain actions for your HEOS on a
[keymap][].

[OSMC]: https://osmc.tv
[raspi]: https://www.raspberrypi.org
[Kodi]: http://kodi.wiki/view/Kodi
[keymap]: http://kodi.wiki/view/Keymaps

Example `keyboard.xml`-file:

```xml
<keymap>
<global>
<keyboard>
<F1>RunScript(heos_player, player/play_preset, -p, preset=1)</F1>
<F2>RunScript(heos_player, player/play_preset, -p, preset=2)</F2>
<F3>RunScript(heos_player, player/play_preset, -p, preset=3)</F3>
<F4>RunScript(heos_player, player/play_preset, -p, preset=4)</F4>
<F12>RunScript(heos_player, player/set_play_state, -p, state=stop)</F12>
</keyboard>
</global>
<Home>
</Home>
</keymap>
```

## To-do

Currently, heospy cannot listen to events, as specified in [1]. 

## Credits

- first code from <https://github.com/mrjohnsen/heos-python>
- the SSDS discovery library is from
  <https://gist.github.com/dankrause/6000248>, with an additional modification
  by Adam Baxter to get this working for Python 3.
