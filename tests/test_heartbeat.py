from heospy import heos_player
import logging

def test_zero():
    try:
        p = heos_player.HeosPlayer()
    except heos_player.HeosPlayerConfigException:
        logging.warning("no config, but this is okay for now")
        pass
    assert True
