#!/usr/bin/env python3
import os
import sys
import uvicorn

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def run_api():
    """Run the WordPress Theme Transformer API"""
    print("Starting WordPress Theme Transformer API...")
    
    print("\nAPI Documentation and Testing:")
    print("- Swagger UI: http://localhost:8000/docs")
    print("- ReDoc: http://localhost:8000/redoc")
    
    print("\nKey Endpoints:")
    print("1. /store-complete-theme - Upload and store a WordPress theme")
    print("2. /transform-by-id - Transform a theme by its ID from the database")
    print("3. /generate/onepage - Generate a one-page WordPress site")
    print("4. /generate/multipage - Generate a multi-page WordPress site")
    
    # Import the app here to ensure the paths are set up correctly
    from offline.orchestra_agent import app
    
    # Run the API server
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    run_api() 