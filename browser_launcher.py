"""
Simple GUI for launching Chrome with remote debugging.
Integrates with the authenticated scraper for existing browser sessions.
"""

import logging
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from launch_chrome_debug import find_chrome_path, is_port_in_use


class BrowserLauncherGUI:
    """GUI for managing Chrome debugging sessions."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Chrome Debug Launcher")
        self.root.geometry("600x500")
        self.root.resizable(True, True)

        # Track Chrome process
        self.chrome_process = None

        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Configure main frame grid weights
        main_frame.grid_rowconfigure(4, weight=1)  # Instructions frame gets extra space
        main_frame.grid_columnconfigure(0, weight=1)

        # Title
        title_label = ttk.Label(
            main_frame,
            text="Chrome Remote Debugging Launcher",
            font=("Arial", 14, "bold"),
        )
        title_label.grid(row=0, column=0, pady=(0, 10), sticky="ew")

        # Port configuration
        port_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="10")
        port_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        port_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(port_frame, text="Debug Port:").grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )
        self.port_var = tk.StringVar(value="9222")
        port_entry = ttk.Entry(port_frame, textvariable=self.port_var, width=10)
        port_entry.grid(row=0, column=1, sticky="w", pady=(0, 5), padx=(10, 0))

        ttk.Label(port_frame, text="User Data Directory (optional):").grid(
            row=1, column=0, sticky="w", pady=(0, 5)
        )
        self.user_data_var = tk.StringVar()
        user_data_entry = ttk.Entry(
            port_frame, textvariable=self.user_data_var, width=40
        )
        user_data_entry.grid(row=1, column=1, sticky="ew", pady=(0, 5), padx=(10, 0))

        # Status display
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        status_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ttk.Label(status_frame, text="Ready to launch Chrome")
        self.status_label.grid(row=0, column=0, sticky="w", pady=(0, 5))

        self.debug_url_label = ttk.Label(status_frame, text="", foreground="blue")
        self.debug_url_label.grid(row=1, column=0, sticky="w", pady=(0, 5))

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        self.check_button = ttk.Button(
            button_frame, text="Check Status", command=self.check_status
        )
        self.check_button.grid(row=0, column=0, padx=(0, 5), sticky="w")

        self.launch_button = ttk.Button(
            button_frame, text="Launch Chrome", command=self.launch_chrome
        )
        self.launch_button.grid(row=0, column=1, padx=(5, 5), sticky="w")

        self.open_debug_button = ttk.Button(
            button_frame,
            text="Open Debug Interface",
            command=self.open_debug_interface,
            state="disabled",
        )
        self.open_debug_button.grid(row=0, column=2, padx=(5, 5), sticky="w")

        self.stop_button = ttk.Button(
            button_frame,
            text="Stop Chrome",
            command=self.stop_chrome,
            state="disabled",
        )
        self.stop_button.grid(row=0, column=3, padx=(5, 5), sticky="w")
        
        self.focus_button = ttk.Button(
            button_frame,
            text="Focus Window",
            command=self.focus_chrome_window,
            state="disabled",
        )
        self.focus_button.grid(row=0, column=4, padx=(5, 0), sticky="w")

        # Instructions
        instructions_frame = ttk.LabelFrame(
            main_frame, text="Instructions", padding="10"
        )
        instructions_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        instructions_frame.grid_rowconfigure(0, weight=1)
        instructions_frame.grid_columnconfigure(0, weight=1)

        # Create text widget with scrollbar
        text_frame = ttk.Frame(instructions_frame)
        text_frame.grid(row=0, column=0, sticky="nsew")
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        instructions_text = tk.Text(
            text_frame,
            height=8,
            wrap="word",
            background="#000000",
            foreground="#ffffff",
            font=("Proxima Nova Alt Condensed", 10, "normal"),
        )
        instructions_text.grid(row=0, column=0, sticky="nsew")

        # Add scrollbar
        scrollbar = ttk.Scrollbar(
            text_frame, orient="vertical", command=instructions_text.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        instructions_text.configure(yscrollcommand=scrollbar.set)

        instructions = """1. Click "Launch Chrome" to start Chrome with remote debugging
2. Use the opened Chrome browser to manually navigate and login to sites
3. In your scraper code, use: AuthenticatedScraper(connect_to_existing=True, debug_port=9222)
4. The scraper will connect to your existing browser session with all cookies and login state

Benefits:
• Manually handle CAPTCHAs and 2FA
• Preserve login sessions between scraping runs
• Debug and inspect elements in real-time
• Bypass bot detection more effectively"""

        instructions_text.insert("1.0", instructions)
        instructions_text.config(state="disabled")

        # Auto-check status on startup
        self.root.after(500, self.check_status)

    def check_status(self):
        """Check if Chrome debugging is already running."""
        try:
            port = int(self.port_var.get())
            if is_port_in_use(port):
                self.status_label.config(
                    text="✅ Chrome debugging is active", foreground="green"
                )
                self.debug_url_label.config(
                    text=f"Debug interface: http://localhost:{port}"
                )
                self.open_debug_button.config(state="normal")
                self.stop_button.config(state="normal")
                self.focus_button.config(state="normal")
                self.launch_button.config(text="Already Running")
            else:
                self.status_label.config(
                    text="❌ Chrome debugging not detected", foreground="red"
                )
                self.debug_url_label.config(text="")
                self.open_debug_button.config(state="disabled")
                self.stop_button.config(state="disabled")
                self.focus_button.config(state="disabled")
                self.launch_button.config(text="Launch Chrome")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid port number")

    def launch_chrome(self):
        """Launch Chrome with debugging in a separate thread."""
        try:
            port = int(self.port_var.get())
            user_data_dir = self.user_data_var.get().strip() or None

            if is_port_in_use(port):
                result = messagebox.askyesno(
                    "Chrome Already Running", 
                    f"Chrome is already running with debugging on port {port}.\n\n"
                    "Would you like to open a new tab in the existing browser?",
                    icon="question"
                )
                if result:
                    self.focus_chrome_window()
                return

            self.status_label.config(text="🚀 Launching Chrome...", foreground="orange")
            self.launch_button.config(state="disabled")

            def launch_thread():

                chrome_path = find_chrome_path()
                if not chrome_path:
                    self.root.after(0, lambda: self.launch_complete(False))
                    return

                # Set up user data directory
                nonlocal user_data_dir
                if not user_data_dir:
                    user_data_dir = f"/tmp/chrome-debug-{port}"

                Path(user_data_dir).mkdir(parents=True, exist_ok=True)

                # Chrome launch arguments
                args = [
                    chrome_path,
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
                ]

                try:
                    # Launch Chrome and store process reference
                    self.chrome_process = subprocess.Popen(
                        args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )

                    # Wait for Chrome to start
                    for i in range(10):
                        time.sleep(1)
                        if is_port_in_use(port):
                            self.root.after(0, lambda: self.launch_complete(True))
                            return

                    self.root.after(0, lambda: self.launch_complete(False))
                except Exception as e:
                    logging.error(f"Failed to launch Chrome: {e}")
                    self.root.after(0, lambda: self.launch_complete(False))

            threading.Thread(target=launch_thread, daemon=True).start()

        except ValueError:
            messagebox.showerror("Error", "Please enter a valid port number")

    def launch_complete(self, success):
        """Handle launch completion."""
        self.launch_button.config(state="normal")
        if success:
            self.check_status()
            messagebox.showinfo(
                "Success",
                "Chrome launched successfully!\n\nYou can now use the browser manually and connect to it from your scraper.",
            )
        else:
            self.chrome_process = None
            messagebox.showerror("Error", "Failed to launch Chrome with debugging")

    def open_debug_interface(self):
        """Open the Chrome debug interface in default browser."""
        try:
            port = int(self.port_var.get())
            import webbrowser

            webbrowser.open(f"http://localhost:{port}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open debug interface: {e}")

    def stop_chrome(self):
        """Stop the Chrome debug browser gracefully."""
        try:
            port = int(self.port_var.get())

            # First try to close gracefully via CDP
            try:
                import requests

                response = requests.get(f"http://localhost:{port}/json", timeout=2)
                if response.status_code == 200:
                    # Try to close all tabs first
                    tabs = response.json()
                    for tab in tabs:
                        if "webSocketDebuggerUrl" in tab:
                            try:
                                requests.post(
                                    f"http://localhost:{port}/json/close/{tab['id']}",
                                    timeout=1,
                                )
                            except Exception:
                                pass
            except Exception:
                pass

            # If we have the process reference, terminate it
            if self.chrome_process and self.chrome_process.poll() is None:
                self.chrome_process.terminate()
                # Wait a bit for graceful shutdown
                time.sleep(2)
                if self.chrome_process.poll() is None:
                    self.chrome_process.kill()
                self.chrome_process = None
            else:
                # Fallback: find and kill Chrome processes with our debug port
                try:
                    # Find processes using the debug port
                    result = subprocess.run(
                        ["lsof", "-ti", f":{port}"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.stdout.strip():
                        pids = result.stdout.strip().split("\n")
                        for pid in pids:
                            try:
                                subprocess.run(["kill", "-TERM", pid], timeout=2)
                            except Exception:
                                pass
                except Exception:
                    pass

            # Update UI
            self.status_label.config(text="Chrome stopped", foreground="orange")
            self.debug_url_label.config(text="")
            self.open_debug_button.config(state="disabled")
            self.stop_button.config(state="disabled")
            self.focus_button.config(state="disabled")
            self.launch_button.config(text="Launch Chrome")

            messagebox.showinfo("Success", "Chrome debug browser stopped successfully")

        except ValueError:
            messagebox.showerror("Error", "Please enter a valid port number")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop Chrome: {e}")
            
    def focus_chrome_window(self):
        """Bring Chrome debug window to front and open a new tab."""
        try:
            port = int(self.port_var.get())
            
            # First, try to open a new tab via CDP and navigate to a visible page
            try:
                import requests
                response = requests.post(f"http://localhost:{port}/json/new", timeout=2)
                if response.status_code == 200:
                    tab_info = response.json()
                    
                    # Navigate to a page to make the window visible
                    tab_id = tab_info.get('id')
                    if tab_id:
                        navigate_response = requests.post(
                            f"http://localhost:{port}/json/runtime/evaluate",
                            json={
                                "expression": "window.location.href = 'https://www.google.com';"
                            },
                            timeout=2
                        )
                    
                    # Now try to focus the specific Chrome process
                    self._focus_debug_chrome_process(port)
                    messagebox.showinfo(
                        "Success", 
                        f"New tab opened and window focused\nTab ID: {tab_info.get('id', 'Unknown')}"
                    )
                    return
                else:
                    raise Exception("Failed to create new tab")
            except Exception:
                # Try to focus without creating new tab
                if self._focus_debug_chrome_process(port):
                    messagebox.showinfo(
                        "Window Focus", 
                        "Brought Chrome debug window to front"
                    )
                else:
                    # Final fallback: just open debug interface
                    import webbrowser
                    webbrowser.open(f"http://localhost:{port}")
                    messagebox.showinfo(
                        "Debug Interface", 
                        "Opened debug interface in your default browser"
                    )
            
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid port number")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to focus Chrome window: {e}")
    
    def _focus_debug_chrome_process(self, port):
        """Focus the specific Chrome process running with debug port."""
        try:
            print(f"DEBUG: Attempting to focus Chrome on port {port}")
            
            # Method 1: Use lsof to find the exact process using the debug port
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            print(f"DEBUG: lsof result: '{result.stdout.strip()}'")
            
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                print(f"DEBUG: Found PIDs: {pids}")
                for pid in pids:
                    try:
                        # Get process info to confirm it's Chrome
                        ps_result = subprocess.run(
                            ["ps", "-p", pid, "-o", "comm="], 
                            capture_output=True, 
                            text=True, 
                            timeout=2
                        )
                        print(f"DEBUG: PID {pid} process: '{ps_result.stdout.strip()}'")
                        if "Chrome" in ps_result.stdout or "chrome" in ps_result.stdout:
                            print(f"DEBUG: Attempting to focus Chrome PID {pid}")
                            # Use AppleScript to focus this specific process
                            applescript = f'''
                            tell application "System Events"
                                set chromeProcess to first process whose unix id is {pid}
                                set frontmost of chromeProcess to true
                            end tell
                            '''
                            applescript_result = subprocess.run(["osascript", "-e", applescript], 
                                                               capture_output=True, text=True, timeout=5)
                            print(f"DEBUG: AppleScript result: {applescript_result.returncode}, stderr: {applescript_result.stderr}")
                            if applescript_result.returncode == 0:
                                print(f"DEBUG: Successfully focused Chrome PID {pid}")
                                return True
                    except Exception as e:
                        print(f"DEBUG: Error with PID {pid}: {e}")
                        continue
            
            # Method 2: Try to find Chrome with remote debugging argument
            print(f"DEBUG: Method 1 failed, trying Method 2 - searching ps aux")
            ps_result = subprocess.run(
                ["ps", "aux"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            print(f"DEBUG: Searching for remote-debugging-port={port} in process list")
            for line in ps_result.stdout.split('\n'):
                if f"remote-debugging-port={port}" in line and "Chrome" in line:
                    print(f"DEBUG: Found Chrome debug process: {line}")
                    # Extract PID (second column)
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        print(f"DEBUG: Extracted PID: {pid}")
                        try:
                            applescript = f'''
                            tell application "System Events"
                                set chromeProcess to first process whose unix id is {pid}
                                set frontmost of chromeProcess to true
                            end tell
                            '''
                            applescript_result = subprocess.run(["osascript", "-e", applescript], 
                                                               capture_output=True, text=True, timeout=5)
                            print(f"DEBUG: Method 2 AppleScript result: {applescript_result.returncode}, stderr: {applescript_result.stderr}")
                            if applescript_result.returncode == 0:
                                print(f"DEBUG: Successfully focused Chrome via Method 2")
                                return True
                        except Exception as e:
                            print(f"DEBUG: Method 2 error: {e}")
                            continue
            
            # Method 3: Fallback to generic Chrome activation
            print(f"DEBUG: Method 2 failed, trying Method 3 - generic Chrome activation")
            applescript = '''
            tell application "Google Chrome"
                activate
            end tell
            '''
            applescript_result = subprocess.run(["osascript", "-e", applescript], 
                                               capture_output=True, text=True, timeout=5)
            print(f"DEBUG: Method 3 AppleScript result: {applescript_result.returncode}, stderr: {applescript_result.stderr}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to focus Chrome process: {e}")
            return False

    def run(self):
        """Run the GUI."""
        self.root.mainloop()


if __name__ == "__main__":
    app = BrowserLauncherGUI()
    app.run()
