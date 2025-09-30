#!/Users/brittaneyperry-morgan/Desktop/auto/.venv/bin/python
"""
Helper script to launch Chrome with remote debugging enabled on Mac.
This allows the authenticated scraper to connect to an existing browser session.
"""

import os
import subprocess
import sys
import time
import requests
from pathlib import Path


def find_chrome_path():
    """Find Chrome installation path on Mac."""
    possible_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None


def is_port_in_use(port):
    """Check if a port is already in use."""
    try:
        response = requests.get(f"http://localhost:{port}/json", timeout=2)
        return response.status_code == 200
    except:
        return False


def launch_chrome_with_debugging(port=9222, user_data_dir=None):
    """Launch Chrome with remote debugging enabled."""
    
    chrome_path = find_chrome_path()
    if not chrome_path:
        print("❌ Chrome not found. Please install Google Chrome.")
        return False
    
    # Check if port is already in use
    if is_port_in_use(port):
        print(f"✅ Chrome is already running with debugging on port {port}")
        print(f"🌐 Debug interface: http://localhost:{port}")
        return True
    
    # Set up user data directory
    if user_data_dir is None:
        user_data_dir = f"/tmp/chrome-debug-{port}"
    
    # Create user data directory if it doesn't exist
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)
    
    # Launch Chrome with remote debugging and ensure window is visible
    chrome_args = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-plugins", 
        "--disable-default-apps",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=TranslateUI",
        "--disable-ipc-flooding-protection",
        "--disable-web-security",
        "--disable-features=VizDisplayCompositor",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "https://www.google.com"  # Open with a default page to ensure window is visible
    ]
    
    print(f"🚀 Launching Chrome with debugging on port {port}...")
    print(f"📁 User data directory: {user_data_dir}")
    
    try:
        # Launch Chrome in background
        process = subprocess.Popen(chrome_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Wait for Chrome to start
        for i in range(10):
            time.sleep(1)
            if is_port_in_use(port):
                print(f"✅ Chrome launched successfully!")
                print(f"🌐 Debug interface: http://localhost:{port}")
                print(f"🔧 Process ID: {process.pid}")
                print(f"\n📋 To connect from your script:")
                print(f"   scraper = AuthenticatedScraper(connect_to_existing=True, debug_port={port})")
                return True
        
        print("❌ Chrome failed to start with debugging enabled")
        return False
        
    except Exception as e:
        print(f"❌ Failed to launch Chrome: {e}")
        return False


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Launch Chrome with remote debugging")
    parser.add_argument("--port", type=int, default=9222, help="Debug port (default: 9222)")
    parser.add_argument("--user-data-dir", help="Custom user data directory")
    parser.add_argument("--check", action="store_true", help="Check if debugging is already enabled")
    
    args = parser.parse_args()
    
    if args.check:
        if is_port_in_use(args.port):
            print(f"✅ Chrome debugging is active on port {args.port}")
            print(f"🌐 Debug interface: http://localhost:{args.port}")
        else:
            print(f"❌ No Chrome debugging found on port {args.port}")
        return
    
    success = launch_chrome_with_debugging(args.port, args.user_data_dir)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
