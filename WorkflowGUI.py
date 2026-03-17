#!/usr/bin/env python3
# WorkflowGUI.py — launches the Stage One GUI and internal static HTTP server

import tkinter as tk
import os
import socket
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

from StageOnePanel import StageOnePanel


# --------------------------------------------------------------
# FIND FREE PORT
# --------------------------------------------------------------
def find_free_port():
    """Find an available TCP port."""
    s = socket.socket()
    s.bind(("", 0))
    _, port = s.getsockname()
    s.close()
    return port


# --------------------------------------------------------------
# START INTERNAL STATIC HTTP SERVER
# --------------------------------------------------------------
def start_server_in_background(port, directory):
    """
    Start a static HTTP server (HTML / JS / CSV only)
    No POST, no writing, display-only.
    """
    os.chdir(directory)
    server = HTTPServer(("localhost", port), SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# --------------------------------------------------------------
# MAIN GUI ENTRY POINT
# --------------------------------------------------------------
def run_gui():
    root = tk.Tk()

    # Working directory = project root
    working_dir = os.path.dirname(os.path.abspath(__file__))

    # Start internal static server
    server_port = find_free_port()
    start_server_in_background(server_port, working_dir)

    # Load Stage One panel (viewer launcher)
    app = StageOnePanel(root, server_port)

    # Main loop
    root.mainloop()


# --------------------------------------------------------------
# LAUNCH
# --------------------------------------------------------------
if __name__ == "__main__":
    run_gui()
