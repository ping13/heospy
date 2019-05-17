#!/usr/bin/env python
# -*- encoding: utf-8 -*-

"""A script to control an HEOS player, see <https://github.com/ping13/heospy>
for details.

Specification of the HEOS interface at
http://rn.dmglobal.com/euheos/HEOS_CLI_ProtocolSpecification.pdf

"""

import json
import os
import telnetlib
import re
import logging
import argparse
import six
import sys
import time
from collections import OrderedDict

from . import ssdp # Simple Service Discovery Protocol (SSDP), https://gist.github.com/dankrause/6000248


# determine a default path for the config file
DEFAULT_CONFIG_PATH = "."
for location in os.curdir, os.path.expanduser("~/.heospy"), os.environ.get("HEOSPY_CONF"):
    if location is None:
        continue
    try:
        testname = os.path.join(location,"config.json")
        if os.path.exists(testname):
            DEFAULT_CONFIG_PATH = location
            break
    except IOError:
        pass


TIMEOUT = 15

class HeosPlayerConfigException(Exception):
    pass
class HeosPlayerGeneralException(Exception):
    pass

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
                 config_file = os.path.join(DEFAULT_CONFIG_PATH, 'config.json')):
        """Initialize HEOS player."""
        self.heosurl = 'heos://'

        try:
            with open(config_file) as json_data_file:
                self._config = json.load(json_data_file)
        except IOError:
            error_msg = "cannot read your config file '{}'".format(config_file)
            logging.error(error_msg)
            raise HeosPlayerConfigException(error_msg)
        
        logging.debug("use config file '{}'".format(config_file))
        
        self.host = self._config.get("host")
        self.pid = self._config.get("pid")
        self.main_player_name = self._config.get("player_name", self._config.get("main_player_name"))
        self._config_file = config_file
        self.names = dict()
        self.names["players"] = self._config.get("players", {})
        self.names["groups"] = self._config.get("groups", {})
        self.groups = None
        
        if self.main_player_name is None:
            logging.warn("No main player name given.")
            raise HeosPlayerGeneralException("No main player name given.")
        
        # if host and pid is not known, detect the first HEOS device.
        if rediscover or (not self.host or not self.pid):
            logging.info(u"Starting to discover your HEOS player '{}' in your local network".format(self.main_player_name))
            ssdp_list = ssdp.discover(self.URN_SCHEMA)
            logging.debug("found {} possible hosts: {}".format(len(ssdp_list), ssdp_list))
            self.telnet = None
            for response in ssdp_list:
                if response.st == self.URN_SCHEMA:
                    try:
                        self.host = re.match(r"http:..([^\:]+):", response.location).group(1)
                        logging.debug("Testing host '{}'".format(self.host))                    
                        self.telnet = telnetlib.Telnet(self.host, 1255)
                        logging.debug("Telnet '{}'".format(self.telnet))                    
                        self.pid = self._get_player(self.main_player_name)
                        logging.debug("pid '{}'".format(self.pid))                                            
                        if self.pid:
                            self.main_player_name = self._config.get("player_name", self._config.get("main_player_name"))
                            logging.info(u"Found main player '{}' in your local network".format(self.main_player_name))
                            break
                    except Exception as e:
                        logging.error(e)
                        pass
            if self.telnet == None:
                msg = "couldn't discover any HEOS player with Simple Service Discovery Protocol (SSDP)."
                logging.error(msg)
                raise HeosPlayerGeneralException(msg)

            self._update_groups_players()
            
        else:
            print(repr(self.main_player_name))
            logging.info(u"My cache says your HEOS player '{}' is at {}".format(self.main_player_name,
                                                                                self.host))
            try:
                self.telnet = telnetlib.Telnet(self.host, 1255, timeout=TIMEOUT)
            except Exception as e:
                raise HeosPlayerGeneralException("telnet failed")

        # check if we've found what we were looking for
        if self.host is None:
            logging.error("No HEOS player found in your local network")
        elif self.pid is None:
            logging.error(u"No player with name '{}' found for being a main player!".format(self.main_player_name))
        else:
            # get user and password
            if self.login(user=self._config.get("user"),
                          pw = self._config.get("pw")):
                self.user = self._config.get("user")

                
        # save config
        if (rediscover or self._config.get("pid") is None) and self.host and self.pid:
                
            logging.info("Save host and pid in {}".format(config_file))
            self._config["pid"] = self.pid
            self._config["host"] = self.host
            with open(os.path.join(self._config_file), "w") as json_data_file:
                json.dump(self._config, json_data_file, indent=2)             
                
    def __repr__(self):
        return "<HeosPlayer({main_player_name}, {user}, {host}, {pid})>".format(**self.__dict__)

    def telnet_request(self, command, wait = True):
        """Execute a `command` and return the response(s)."""
        command = self.heosurl + command
        logging.debug("telnet request {}".format(command))
        self.telnet.write(command.encode('ascii') + b'\n')
        response = b''
        logging.debug("starting response loop")
        while True:
            response += self.telnet.read_some()
            try:
                response = json.loads(response.decode("utf-8"))
                logging.debug("found valid JSON: {}".format(json.dumps(response)))
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
                logging.debug("... unfinished response: {}".format(response))
                # response is not a complete JSON object
                pass
            except TypeError:
                logging.debug("... unfinished response: {}".format(response))                
                # response is not a complete JSON object
                pass

        # try to parse the message attribute of the response, there might be
        # some useful information, especially if the payload attribute is
        # missing
        if response.get("heos", {}).get("message"):
            message_parsed_list = response.get("heos", {}).get("message").split("&")
            logging.debug(message_parsed_list)
            message_parsed = OrderedDict()
            for item in message_parsed_list:
                split_items = item.split("=")
                if len(split_items) == 1:
                    split_items.append(True)
                message_parsed[split_items[0]] = split_items[1]
            response["heos_message_parsed"] = message_parsed

        logging.debug("found valid response: {}".format(json.dumps(response)))
        return response

    def _update_groups_players(self):
        idx = { "groups" : "gid", "players" : "pid" }
        
        for aggregate in ["players", "groups"]:
            result = self.telnet_request("player/get_{}".format(aggregate)).get("payload")
            if result:
                self.names[aggregate] = {}
                logging.debug(result)
                for this_item in result:
                    self.names[aggregate][this_item["name"]] = this_item[ idx[aggregate] ]
                    self._config[aggregate] = self.names[aggregate]
                logging.info("In total, I found {} {} in your local network.".format(len(self.names[aggregate]), aggregate))
            else:
                msg = "I couldn't find a list of {}.".format(aggregate)
                if aggregate == "groups":
                    logging.warn(msg)
                else:
                    logging.error(msg)
                    raise HeosPlayerGeneralException(msg)
        
        return True

    def _get_player(self, name):
        response = self.telnet_request("player/get_players")
        if response.get("payload") is None:
            return None
        for player in response.get("payload"):
            logging.debug(u"found '{}', looking for '{}'".format(player.get("name"), name))
            if player.get("name") == name:
                return player.get("pid")
        return None

    def login(self, user = "", pw = ""):
        # fist check if we're already signed in: get the currently signed in
        # user from the system
        signed_in_message = self.telnet_request("system/check_account").get("heos",{}).get("message", "")
        is_signed_in = "signed_in&" in signed_in_message

        if is_signed_in:
            # if signed in, we should also have the same user here.
            signed_in_user = signed_in_message.split("&")[1][3:]
            if signed_in_user==user:
                logging.info("Already signed in as {}".format(signed_in_user))
                return True
            else:
                logging.info("user '{}' is different from '{}'".format(signed_in_user, user))

        # At this point, it seems as if we have to really sign in, which takes
        # a second or two...
        logging.info("Need to sign in as {} to have access to favorites etc.".format(user))
        return self.telnet_request("system/sign_in?un={}&pw={}".format(user, pw))
    

    def cmd(self, cmd, args):
        """ issue a command for our player """

        # parse args and check if there is a gid or pid exlicitly given
        args_concatenated = ""
        pid_explicitly_given = False
        gid_explicitly_given = False

        for (key,value) in six.iteritems(args):
            if key == "pname" or key == "gname" : # these are custom command, working only with this package

                idx = { "gname" : "gid", "pname" : "pid" }
                idx2 = { "gid" : "groups", "pid" : "players" }

                # reassign key
                key = idx[key]
                # analyse the value, which could be one or many speaker names
                named_values = value.decode("utf-8").split(u",")
                value_list = []
                for named_value in named_values:
                    new_value = self.names[ idx2[key] ].get(named_value, False)
                    if new_value is False:
                        raise HeosPlayerGeneralException("Name '{}' is not known. ({}). Try to rediscover (use flag '-r').".format(value, self.names[idx2[key]].keys()))
                    logging.debug("translated name '{}' to {}={}".format(value, idx, new_value))
                    value_list.append(str(new_value))
                value = ",".join(value_list)

            args_concatenated += "&{}={}".format(key, value)

            logging.info("cmd : {}, args {}".format(cmd, args_concatenated))

            if key == "pid":
                pid_explicitly_given = True
            if key == "gid":
                gid_explicitly_given = True
                


        if self.pid is None and ("groups/" in cmd or "group/" in cmd or "browse/" in cmd):
            logging.warn("No default player is defined.")
        else:
            # if this is a command where a gid or a pid is needed, check if we
            # could use the default pid from the config file
            if ("groups/" in cmd or "group/" in cmd or "browse/" in cmd) and not gid_explicitly_given:
                logging.info("I assume default group with id {0}".format(self.pid))
                s = '{0}?gid={1}'.format(cmd, self.pid)
            elif ("player/" in cmd or "players" in cmd) and not pid_explicitly_given:
                logging.info("I assume default player with id {0}".format(self.pid))
                s = '{0}?pid={1}'.format(cmd, self.pid)
            else:
                s = '{0}?dummy=1'.format(cmd) # use dummy so that
                                              # args_concatenated is correctly attached

        return self.telnet_request(s + args_concatenated)
    
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
        
  heos_player player/toggle_mute
  heos_player player/set_volume -p level=19
  heos_player player/play_preset -p preset=3
  heos_player player/set_play_state -p state=stop
"""

    parser = argparse.ArgumentParser(description=__doc__, epilog=epilog,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cmd", nargs="?",
                        help="command to send to HEOS player")
    parser.add_argument("-i", '--infile', nargs='?', type=argparse.FileType('r'),
                        default=None)
    parser.add_argument("-s", "--status", action='store_true', default=False,
                        help="return various status information", dest="status")
    parser.add_argument("-r", "--rediscover", action='store_true', default=False,
                        help="force to discover HEOS IP address and player id", dest="rediscover")
    parser.add_argument("-p", "--param", action='append', 
                        type=lambda kv: kv.split("="), dest='param', metavar="param=value",
                        help="optional key-value pairs that needs to be accompanied to the command that is sent to the HEOS player.")
    parser.add_argument("-c", "--config", dest="config", default="", metavar="filename",
                        help="config file (by default, the script looks for a config file called `config.json` in the current directory, then in $HOME/.heospy, then in $HEOSPY_CONF)")
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
        try:
            heos_args = OrderedDict(script_args.param)
        except ValueError:
            logging.error("there are some errors in your '--param' arguments: '{}'".format(script_args.param))
            sys.exit(0)

    # determine the config file
    logging.debug("DEFAULT_CONFIG_PATH is '{}'".format(DEFAULT_CONFIG_PATH))
    config_file  = os.path.join(DEFAULT_CONFIG_PATH, 'config.json')
    if script_args.config:
        config_file  = script_args.config
        logging.debug("from --config, I got '{}'".format(config_file))

    # initialize connection to HEOS player
    try:
        p = HeosPlayer(rediscover = script_args.rediscover, config_file=config_file)
    except HeosPlayerConfigException:
        logging.info("Try to find a valid config file and specify it with '--config'...")
        sys.exit(-1)
    except HeosPlayerGeneralException:
        # if the connection failed, it might be because the cached IP for
        # the HEOS player is not valid anymore. We check if we can rediscover
        # the new IP of the HEOS player
        if script_args.rediscover == False:
            logging.info("First connection failed. Try to rediscover the HEOS players.")
            p = HeosPlayer(rediscover = True, config_file=config_file)
    except:
        logging.error("Someting unexpected got wrong...")
        raise

    # check status or issue a command
    if script_args.status:
        logging.info("Try to find some status info from {}".format(p.host))
        print(json.dumps(p.status(), indent=2))
    elif script_args.infile:
        logging.debug("reading a list of commands from {}".format(script_args.infile))
        all_lines = script_args.infile.read().splitlines()
        # execute each cmd
        all_results = []
        fail = False
        for line in all_lines:
            if len(line) > 0 and line[0] == "#": continue # skip comments
            # get elements separated by whitespaces
            cmd_args = line.split()
            if len(cmd_args) == 0: continue
            # first element is the command, like "player/set_volume"
            heos_cmd = cmd_args[0]
            if heos_cmd == "wait": # this is a special command
                try:
                    secs = int(cmd_args[1])
                except IndexError:
                    secs=1
                time.sleep(secs)
                all_results.append({ "heospy" : { "sleep": "successful for {} secs".format(secs) } })
            else:
                # other elements are parameters like "level=10" or "pid=387387",
                # collect them in a dictionary
                heos_args = OrderedDict([ kv.split("=") for kv in cmd_args[1:] ])
                # issue the actual command
                logging.info("Issue command '{}' with arguments {}".format(heos_cmd, json.dumps(heos_args)))
                result = p.cmd(heos_cmd, heos_args)
                all_results.append(result)
                if result.get("heos", {}).get("result", "") != "success":
                    fail = True
                    break
            
        # print all results at the end
        print(json.dumps(all_results, indent=2))

        # if the last result was not a success, return with -1
        if fail:
            sys.exit(-1)
            
    elif heos_cmd:
        logging.info("Issue command '{}' with arguments {}".format(heos_cmd, json.dumps(heos_args)))
        result = p.cmd(heos_cmd, heos_args)
        print(json.dumps(result, indent=2))

        # if the result was not a success, return with -1
        if result.get("heos", {}).get("result", "") != "success":
            sys.exit(-1)
    else:
        logging.info("Nothing to do.")
        
if __name__ == "__main__":
    main()
