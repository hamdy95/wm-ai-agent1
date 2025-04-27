#!/usr/bin/env python3

import os
import sys
import uvicorn

# Add the parent directory to the system path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the app from orchestra_agent
from offline.orchestra_agent import app

if __name__ == "__main__":
    print("Starting WordPress Theme Transformer API...")
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=8000)
