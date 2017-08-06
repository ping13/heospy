# Control an HEOS player with a Python script

## Requirements

You have an [HEOS][] speaker in your local network and Python 2.7.

## Usage

1. Create a `config.json` file in the same directory as the script. The file
   contains the name of the [HEOS][] player you want to control and the
   username and password of your [HEOS account][]. See `example-config.json`for
   an example.

2. Run the script for the first time to see how this works:

        $ python heos_player.py 
        2017-02-12 20:32:29,880 INFO Starting to discover your HEOS player 'Living room' in your local network
        2017-02-12 20:32:36,824 INFO Found 'Living room' in your local network
        $
        
3. Call any command from the [CLI specs][specs], see also `docs/` folder. Additional
   arguments are given with `-p`. The player id will be automatically
   submitted. Some examples:

        python heos_player.py player/toggle_mute
        python heos_player.py player/set_volume -p level=19
        python heos_player.py player/play_preset -p preset=3
        python heos_player.py player/set_play_state -p state=stop
        
    Use the flag `--help` for a detailed help.

[specs]: http://rn.dmglobal.com/euheos/HEOS_CLI_ProtocolSpecification.pdf
[HEOS]: http://heoslink.denon.com
[HEOS account]: http://denon.custhelp.com/app/answers/detail/a_id/1968

## Limitations and To-dos

The class `HeosPlayer` currently works with one HEOS player (as I only have one
HEOS speaker). One should extend this to support multiple players, preferably
with a default player for issuing commands.

The cache in the `config.json` file should contain the players, groups and
sources.

## Usage with Raspberry Pi and Kodi

If you have [OSMC][] or any other [Kodi Media center][Kodi] implementation on
your [Raspberry Pi][raspi], you can map certain actions for your HEOS on a
[keymap][].

[OSMC]: https://osmc.tv
[raspi]: https://www.raspberrypi.org
[Kodi]: http://kodi.wiki/view/Kodi
[keymap]: http://kodi.wiki/view/Keymaps

Example `keyboard.xml`-file:
```
<keymap>
  <global>
    <keyboard>
      <F1>RunScript(/home/osmc/dev/heospy/heos_player.py, player/play_preset, -p, preset=1)</F1>
      <F2>RunScript(/home/osmc/dev/heospy/heos_player.py, player/play_preset, -p, preset=2)</F2>
      <F3>RunScript(/home/osmc/dev/heospy/heos_player.py, player/play_preset, -p, preset=3)</F3>
      <F4>RunScript(/home/osmc/dev/heospy/heos_player.py, player/play_preset, -p, preset=4)</F4>
      <F12>RunScript(/home/osmc/dev/heospy/heos_player.py, player/set_play_state, -p, state=stop)</F12>
    </keyboard>
  </global>
  <Home>
  </Home>
</keymap>
```

## Credits

- first code from <https://github.com/mrjohnsen/heos-python>
- the SSDS discovery library is from <https://gist.github.com/dankrause/6000248>
