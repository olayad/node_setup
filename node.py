#!/usr/bin/python3

"""
This program initializes two liquid nodes and generates AuthServiceProxy to
communicate with them.
"""
import os
import time
import subprocess
import platform
from bitcoinrpc.authproxy import AuthServiceProxy
import http.client


class Node():
    def __init__(self, datadir):
        self.datadir = datadir
        self.conf = {}
        self.client = None

    def start_daemon(self):
        """
        Starts liquidd as subprocess, on data dir given by global liq_datadir
        """
        command = 'liquidd -datadir='+self.datadir
        print('Starting node... '+command)
        subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        self.client = self.get_rpc_connection(self.conf['rpcuser'],
                                              self.conf['rpcpassword'],
                                              self.conf['rpcport'])

    def init_node(self):
        """
        Wrapper function used to start a liquidd instance
        """
        self.load_conf(self.datadir + '/liquid.conf')
        self.start_daemon()
        time.sleep(1.0)

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


if __name__ == '__main__':
    # User define following params
    node1_datadir = '/home/casa/.liquid/liquid-regtest1/'
    node2_datadir = '/home/casa/.liquid/liquid-regtest2/'

    l1 = Node(node1_datadir)
    l2 = Node(node2_datadir)
    l1.init_node()
    l2.init_node()

    print(l1.client.getblockchaininfo())
    print(l2.client.getblockchaininfo())
