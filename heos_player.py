#!/usr/bin/env python
"""A script to control an HEOS player.

Specification of the HEOS interface at
http://rn.dmglobal.com/euheos/HEOS_CLI_ProtocolSpecification.pdf

"""

import json
import os
import telnetlib
import re
import logging
import argparse

import ssdp # Simple Service Discovery Protocol (SSDP), https://gist.github.com/dankrause/6000248


config = { }

try:
    CONFIG_PATH = os.path.dirname(__file__)
except NameError:
    CONFIG_PATH = "."
TIMEOUT = 15

class HeosPlayer(object):
    """Representation of an HEOS player with a specific player id.

This needs a JSON config file with a minimal content:

{
  "player_name": "Living Room",
  "user": "me@example.com",
  "pw": "do-not-use-qwerty-as-password"
}

"""

    URN_SCHEMA = "urn:schemas-denon-com:device:ACT-Denon:1"
    
    def __init__(self, rediscover = False,
                 config_file = os.path.join(CONFIG_PATH, 'config.json')):
        """Initialize HEOS player."""
        self.heosurl = 'heos://'

        with open(config_file) as json_data_file:
            config = json.load(json_data_file)

        self.host = config.get("host")
        self.pid = config.get("pid")
        self.player_name = config.get("player_name")

        if config.get("player_name") is None:
            logging.warn("No player name given.")
            raise Exception("No player name given.")
        
        # if host and pid is not known, detect the first HEOS device.
        if rediscover or (not self.host or not self.pid):
            logging.info("Starting to discover your HEOS player '{}' in your local network".format(self.player_name))
            ssdp_list = ssdp.discover(self.URN_SCHEMA)
            self.telnet = None
            for response in ssdp_list:
                if response.st == self.URN_SCHEMA:
                    try:
                        self.host = re.match(r"http:..([^\:]+):", response.location).group(1)
                        self.telnet = telnetlib.Telnet(self.host, 1255)
                        self.pid = self._get_player(config.get("player_name"))
                        if self.pid:
                            self.player_name = config.get("player_name")
                            logging.info("Found '{}' in your local network".format(self.player_name))
                            break
                    except Exception as e:
                        logging.error(e)
                        pass
            if self.telnet == None:
                msg = "couldn't discover HEOS player with Simple Service Discovery Protocol (SSDP)."
                logging.error(msg)
                raise Exception(msg)
                    
        else:
            logging.info("My cache says your HEOS player '{}' is at {}".format(config.get("player_name"),
                                                                               self.host))
            try:
                self.telnet = telnetlib.Telnet(self.host, 1255, timeout=TIMEOUT)
            except Exception as e:
                raise Exception("telnet failed: {}".format(e))

        # check if we've found what we were looking for
        if self.host is None:
            logging.error("No HEOS player found in your local network")
        elif self.pid is None:
            logging.error("No player with name '{}' found!".format(config.get("player_name")))
        else:
            # try to login, if possible
            if self.login(user=config.get("user"),
                          pw = config.get("pw")):
                self.user = config.get("user")
                
        # save config
        if (rediscover or config.get("pid") is None) and self.host and self.pid:
            logging.info("Save host and pid in {}".format(config_file))
            config["pid"] = self.pid
            config["host"] = self.host
            with open(os.path.join(CONFIG_PATH, 'config.json'), "w") as json_data_file:
                json.dump(config, json_data_file, indent=2)
        
    def __repr__(self):
        return "<HeosPlayer({player_name}, {user}, {host}, {pid})>".format(**self.__dict__)

    def telnet_request(self, command, wait = True):
        """Execute a `command` and return the response(s)."""
        command = self.heosurl + command
        logging.debug("telnet request {}".format(command))
        self.telnet.write(command.encode('ASCII') + b'\r\n')
        response = b''
        while True:
            response += self.telnet.read_some()
            try:
                response = json.loads(response)
                if not wait:
                    logging.debug("I accept the first response: {}".format(response))
                    break
                # sometimes, I get a response with the message "under
                # process". I might want to wait here
                message = response.get("heos", {}).get("message", "")
                if "command under process" not in message:
                    logging.debug("I assume this is the final response: {}".format(response))
                    break
                logging.debug("Wait for the final response")
                response = b'' # forget this message
            except ValueError:
                # response is not a complete JSON object
                pass
            except TypeError:
                # response is not a complete JSON object
                pass

        if response.get("result") == "fail":
            logging.warn(response)
            return None
            
        return response

    def _get_player(self, name):
        response = self.telnet_request("player/get_players")
        if response.get("payload") is None:
            return None
        for player in response.get("payload"):
            if player.get("name") == name:
                return player.get("pid")
        return None

    def login(self, user = "", pw = ""):
        return self.telnet_request("system/sign_in?un={}&pw={}".format(user, pw))

    def cmd(self, cmd, args):
        """ issue a command for our player """
        s = cmd

        if self.pid is None:
            logging.warn("no player is defined.")
        else:
            s = '{0}?pid={1}'.format(cmd, self.pid)
            
        for (key,value) in args.iteritems():
            s += "&{}={}".format(key, value)
        return self.telnet_request(s)
    
    def status(self):
        s = { "general" : [], "player" : [] }
        s["general"].append(self.telnet_request("system/heart_beat"))
        s["general"].append(self.telnet_request("system/check_account"))
        s["general"].append(self.telnet_request("browse/get_music_sources"))
        s["general"].append(self.telnet_request("player/get_players"))
        s["general"].append(self.telnet_request("group/get_groups"))
        if self.pid:
            s["player"].append(self.telnet_request("player/get_play_state?pid={0}".format(self.pid)))
            s["player"].append(self.telnet_request("player/get_player_info?pid={0}".format(self.pid)))
            s["player"].append(self.telnet_request("player/get_volume?pid={0}".format(self.pid)))
            s["player"].append(self.telnet_request("player/get_mute?pid={0}".format(self.pid)))
            s["player"].append(self.telnet_request('player/get_now_playing_media?pid={0}'.format(self.pid)))
        return s

def parse_args():
    """Parse command line arguments."""

    epilog = """Some example commands:
        
  python heos_player.py player/toggle_mute
  python heos_player.py player/set_volume -p level=19
  python heos_player.py player/play_preset -p preset=3
  python heos_player.py player/set_play_state -p state=stop
"""

    parser = argparse.ArgumentParser(description=__doc__, epilog=epilog,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cmd", nargs="?",
                        help="command to send to HEOS player")
    parser.add_argument("-s", "--status", action='store_true', default=False,
                        help="return various status information", dest="status")
    parser.add_argument("-r", "--rediscover", action='store_true', default=False,
                        help="force to discover HEOS IP address and player id", dest="rediscover")
    parser.add_argument("-p", "--param", action='append', 
                        type=lambda kv: kv.split("="), dest='param', metavar="param=value",
                        help="optional key-value pairs that needs to be accompanied to the command that is sent to the HEOS player.")
    parser.add_argument("-c", "--config", dest="config", default="", metavar="filename",
                        help="config file (by default, the script looks for a config file in the current directory)")
    parser.add_argument("-l", "--log", dest="logLevel", default="INFO",
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], help="Set the logging level")

    return parser.parse_args()

def main():
    script_args = parse_args()
    heos_cmd = script_args.cmd
    heos_args = {}

    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        level=getattr(logging, script_args.logLevel))
    
    if script_args.param:
        heos_args = dict(script_args.param)

    # determine the config file
    config_file  = os.path.join(CONFIG_PATH, 'config.json')
    if script_args.config:
        config_file  = script_args.config

    # initialize connection to HEOS player
    try:
        p = HeosPlayer(rediscover = script_args.rediscover, config_file=config_file)
    except:
        if script_args.rediscover == False:
            logging.info("First connection failed. Try to rediscover the HEOS players.")
            p = HeosPlayer(rediscover = True, config_file=config_file)

    # check status or issue a command
    if script_args.status:
        logging.info("Try to find some status info from {}".format(p.host))
        print(json.dumps(p.status(), indent=2))
    elif heos_cmd:
        logging.info("Issue command '{}' with arguments {}".format(heos_cmd, heos_args))
        print(json.dumps(p.cmd(heos_cmd, heos_args), indent=2))
    else:
        logging.info("Nothing to do.")
        
if __name__ == "__main__":
    main()
