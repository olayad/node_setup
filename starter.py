#!/usr/bin/python3

"""
This program initializes two liquid clients
Instructions to setup:
1. run otctradetool/tools/set_env.sh - (alias: set_env)
2. run star_liquid_instances.sh - (alias: l1d)
3. python3 starter.py
"""

import os
import shutil
import subprocess
import platform
import sys
import time
import warnings
import unittest
import simplejson as json

from bitcoinrpc.authproxy import AuthServiceProxy
import http.client
import logging

l1 = None  # bitcoin rpc auth pointer, client 1
l2 = None

# User define following params
node1_datadir = '/home/casa/liquiddir1/'
node2_datadir = '/home/casa/liquiddir2/'

tools_path = '/home/casa/multisig-example/tools/'

class Node():
    def __init__(self, datadir, name):
        self.datadir = datadir
        self.name = name
        self.conf = {}
        self.cli = None

        self.start_daemon()

    def start_daemon(self):
        """
        Starts liquidd as subprocess, on data dir given by global liq_datadir
        """
        self.load_conf(self.datadir + 'liquid.conf')
        command = 'liquidd -datadir='+self.datadir
        logging.debug('Running: '+command)
        subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        self.cli = self.get_rpc_connection(self.conf['rpcuser'],
                                           self.conf['rpcpassword'],
                                           self.conf['rpcport'])

    def load_conf(self, filename):
        """Loads liquid.conf file into a dictionary"""
        with open(filename) as f:
            for line in f:
                if len(line) == 0 or line[0] == '#' or len(line.split('=')) != 2:
                    continue
                self.conf[line.split('=')[0]] = line.split('=')[1].strip()
            self.conf['filename'] = filename



    @staticmethod
    def get_new_rpc_connection(user, password, port):
        """
        Establish a new RPC connection to a Liquid node.
        """
        connection = AuthServiceProxy('http://{}:{}@localhost:{}'.format(user,
                                                                         password,
                                                                         port))
        return connection

    @staticmethod
    def get_rpc_connection(user=None, password=None, port=None):
        """
        Wrap the connection object with a re-connect retryable. Also, don't
        re-create a connection object if one already exists.
        """

        global _connection
        global CONNECTION_PARAMS

        if password is None and CONNECTION_PARAMS is None:
            Node.configure_with_liquid_magic()

        # Setup an initial connection using (user, pass, port) as parameters.
        # Only do so if one has not already been created.
        if user is None and password is None and port is None:
            # Only create a connection object if one does not already exist.
            if _connection is not None:
                return _connection
            else:
                connection = Node.get_new_rpc_connection(*CONNECTION_PARAMS)
        else:
            connection = Node.get_new_rpc_connection(user, password, port)
            CONNECTION_PARAMS = (user, password, port)

        original_call = connection.__class__.__call__
        def custom_retryable_call(*args, retries_remaining=3, **kwargs):
            """
            Override some RPC connection code in the library and retry an RPC
            command if the connection was stale.
            """
            # don't loop forever
            if retries_remaining == 1:
                return original_call(*args, **kwargs)
            try:
                # execute over RPC or fail here
                return original_call(*args, **kwargs)
            except (BrokenPipeError, http.client.CannotSendRequest) as exception:
                # create a new connection
                args[0]._AuthServiceProxy__conn = http.client.HTTPConnection(connection._AuthServiceProxy__url.hostname,
                                                                             connection._AuthServiceProxy__url.port,
                                                                             connection._AuthServiceProxy__timeout)
                # try again
                return custom_retryable_call(*args, retries_remaining=retries_remaining-1, **kwargs)
        # monkeypatch the class
        connection.__class__.__call__ = custom_retryable_call
        # save as global
        _connection = connection
        return connection

    @staticmethod
    def configure_with_liquid_magic():
        """
        Attempt to guess the location of the Liquid config file and read the liquid
        config file for RPC port and other information.
        """
        if platform.system() == "Darwin":
            conf_file = os.path.expanduser("~/Library/Application Support/Liquid/")
        elif platform.system() == "Windows":
            conf_file = os.path.join(os.environ["APPDATA"], "Liquid")
        else:
            conf_file = os.path.expanduser("~/.liquid")
        conf_file = os.path.join(conf_file, "liquid.conf")
        conf = {}
        try:
            with open(conf_file, "r") as fd:
                for line in fd.readlines():
                    if "#" in line:
                        # trim line
                        line = line[:line.index('#')]

                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    conf[k.strip()] = v.strip()
        except FileNotFoundError:
            raise Exception("Liquid configuration file not found.")

        rpcport = int(conf.get("rpcport", 7040))
        rpcuser = conf.get("rpcuser", "") # Bitcoin Core accepts empty rpcuser
        rpcpassword = conf.get("rpcpassword", None)
        rpchost = conf.get("rpcconnect", "localhost")

        if rpcpassword is None:
            raise Exception("Liquid config file does not specify rpcpassword. "+
                            "Can't connect to Liquid node.")
        global CONNECTION_PARAMS
        CONNECTION_PARAMS = (rpcuser, rpcpassword, rpcport)

        return CONNECTION_PARAMS


class TestTrade(unittest.TestCase):
    global l1, l2

    def setUp(self):
        global node1_datadir, node2_datadir

        warnings.simplefilter('ignore', ResourceWarning)
        logging_setup("experiments", "DEBUG")

        l1 = Node(node1_datadir, "proposer")
        l2 = Node(node2_datadir, "respondent")

    def test(self):
        self.assertEqual(1, 1)

    def tearDown(self):
        logging.info('Tearing down test environment...')

def logging_setup(filename, level):
    """Sets logging to file and std. errror"""
    global l1, l2

    logFormatter = logging.Formatter("%(asctime)s [%(levelname)-8.8s]: %(message)s")
    rootLogger = logging.getLogger()
    if level is "DEBUG":
        rootLogger.setLevel(logging.DEBUG)
    else:
        rootLogger.setLevel(logging.INFO)

    # Debugging - list of all  logging modules
    # for key in logging.Logger.manager.loggerDict:
    #     print("Logging module: ",key)

    # Setting logging levels per module
    # urlib3 = logging.getLogger('urllib3')
    # urlib3.setLevel(logging.WARNING)
    bitcoin_rpc = logging.getLogger('BitcoinRPC')
    bitcoin_rpc.setLevel(logging.WARNING)

    # Setting up stream handlers
    logPath = "."
    fileHandler = logging.FileHandler("{0}/{1}.log".format(logPath, filename))
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

def set_up_env():
    """
    Setting up testing environment. First calls a bash script that terminates all
    running liquid daemons with SIGINT (Ctrl+C). Then deletes existing
    regtest folders as specified in global variables.
    Creates new folder and copies configuration files.
    """

    # Terminate (SIGINT) all running liquidd daemons
    subprocess.call(os.path.join(tools_path, 'killdaemon.sh'))

    # Delete Liquid datadir regtest folders
    if os.path.isdir(node1_datadir):
        shutil.rmtree(node1_datadir)
    if os.path.isdir(node2_datadir):
        shutil.rmtree(node2_datadir)

    # Create new regtest folders, copy config file
    os.makedirs(node1_datadir)
    os.makedirs(node2_datadir)
    path_src_conf1 = os.path.join(tools_path, 'conf', 'liquid1.conf')
    path_src_conf2 = os.path.join(tools_path, 'conf', 'liquid2.conf')
    shutil.copy(path_src_conf1, node1_datadir)
    shutil.copy(path_src_conf2, node2_datadir)
    path_dest_conf1 = os.path.join(node1_datadir, 'liquid1.conf')
    path_dest_conf2 = os.path.join(node2_datadir, 'liquid2.conf')
    path_renamed_conf1 = os.path.join(node1_datadir, 'liquid.conf')
    path_renamed_conf2 = os.path.join(node2_datadir, 'liquid.conf')
    os.rename(path_dest_conf1, path_renamed_conf1)
    os.rename(path_dest_conf2, path_renamed_conf2)

def wait4sync(c1, c2):
    logging.debug('Waiting for node to sync...')
    while True:
        try:
            if (c1.getblockchaininfo()['blocks'] ==
                    c2.getblockchaininfo()['blocks']):
                break
        except:
            pass
    return


if __name__ == '__main__':

    # Initialize logging module
    warnings.simplefilter('ignore', ResourceWarning)
    logging_setup("experiments", "DEBUG")

    # Setup testing environment (regtest dirs and conf files)
    set_up_env()
    l1 = Node(node1_datadir, "proposer")
    l2 = Node(node2_datadir, "respondent")
    wait4sync(l1.cli, l2.cli)
    logging.debug('Nodes are online...')

    # Initial sanity check
    balance1 = l1.cli.getbalance()['bitcoin']
    balance2 = l1.cli.getbalance()['bitcoin']
    assert(balance1 == balance2)

    # Spend all OP_RETURN TRUE UTXO's from fresh node instance
    logging.info('All utxo with OP_RETURN True')

    addr = l1.cli.getnewaddress()
    print(l1.cli.getnewaddress())
    logging.info('Spend all utxo to user1')

    print("L1 getbalance()")
    print(json.dumps(l1.cli.getbalance(), indent=4))
    print("L2 getbalance()")
    print(json.dumps(l2.cli.getbalance(), indent=4))



