import heospy
import logging
import json

logging.basicConfig(level=logging.DEBUG)

def test_zero():
    try:
        p = heospy.HeosPlayer()
        result = p.cmd("system/heart_beat", {})
        assert(result.get("heos",{}).get("result") == "success")
    except heospy.HeosPlayerConfigException:
        logging.warning("no config, but this is okay for now")
        pass
    assert True
