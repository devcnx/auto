"""
Refactored GUI for the Dynamic Ollama Assistant.

This is a simplified version that uses modular components to reduce file size.
"""

import contextlib
import datetime
import json
import logging
import os
import sys
import threading
import time
import warnings
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

from dynamic_ollama_assistant import (
    CSV_DIR,
    CSV_GLOB,
    EXCEL_GLOB,
    DEFAULT_MODEL as OLLAMA_MODEL,
    load_prompt_catalog,
    query_ollama_chat_for_gui,
    build_system_prompt,
    find_placeholders,
)
from web_scraper import scrape_web_content, crawl_website
from authenticated_scraper import (
    scrape_with_login_sync,
    analyze_login_form_sync,
    navigate_and_scrape_sync,
)
from ui_components import UIComponents
from auth_dialogs import (
    ManualSelectorDialog,
    VerificationRequiredDialog,
    LoginAnalysisDialog,
    NavigationDialog,
)
from file_utils import process_uploaded_file, validate_url, aggregate_parsed_content


class OllamaGUI(tk.Tk):
    """Main GUI application for the Dynamic Ollama Assistant."""

    def __init__(self):
        super().__init__()
        self.title("Dynamic Ollama Assistant")
        self.geometry("1200x800")
        self.configure(bg="#2b2b2b")

        # Initialize state
        self.conversation_history = []
        self.parsed_files = []
        self.parsed_document_content = None
        self.conversation_state_file = "conversation_state.json"

        # Create UI components
        self.ui = UIComponents(self)

        # Load conversation state
        self._load_conversation_state()

        # Setup event handlers
        self._setup_event_handlers()

        # Load prompt catalog
        self.prompt_catalog = load_prompt_catalog(CSV_DIR, CSV_GLOB, EXCEL_GLOB)

        # Warm up the model
        self._warm_up_model()

    def _setup_event_handlers(self):
        """Setup keyboard and window event handlers."""
        self.bind("<Control-Return>", lambda e: self.send_message())
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _warm_up_model(self):
        """Warm up the Ollama model in a background thread."""
        def warm_up():
            try:
                list(query_ollama_chat_for_gui(
                    model=OLLAMA_MODEL,
                    system_prompt="You are a helpful assistant.",
                    user_msg="Hello",
                    conversation_history=[],
                ))
                logging.info("Model warm-up completed.")
            except Exception as e:
                logging.warning(f"Model warm-up failed: {e}")

        threading.Thread(target=warm_up, daemon=True).start()

    def send_message(self):
        """Send user message and get AI response."""
        user_msg = self.ui.user_input.get("1.0", tk.END).strip()
        if not user_msg:
            return

        # Clear input
        self.ui.user_input.delete("1.0", tk.END)

        # Add user message to conversation
        self.conversation_history.append({"role": "user", "content": user_msg})
        self._update_conversation_display()

        # Get AI response in background thread
        threading.Thread(
            target=self._get_ai_response,
            args=(user_msg,),
            daemon=True
        ).start()

    def _get_ai_response(self, user_msg):
        """Get AI response in background thread."""
        try:
            # Build system prompt with file context
            system_prompt = build_system_prompt(
                parsed_document_content=aggregate_parsed_content(self.parsed_files)
            )

            # Update status
            self.ui.set_conversation_status("Thinking...")

            # Stream response
            full_response = ""
            first_chunk = True

            for chunk in query_ollama_chat_for_gui(
                model=OLLAMA_MODEL,
                system_prompt=system_prompt,
                user_msg=user_msg,
                conversation_history=self.conversation_history[:-1],  # Exclude current message
            ):
                if first_chunk:
                    self.conversation_history.append({"role": "assistant", "content": ""})
                    self._update_conversation_display()
                    self.ui.set_conversation_status("Responding...")
                    first_chunk = False

                full_response += chunk
                self.conversation_history[-1]["content"] = full_response
                self._update_conversation_display()

            self.ui.set_conversation_status("Ready")
            self._save_conversation_state()

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.conversation_history.append({"role": "assistant", "content": error_msg})
            self._update_conversation_display()
            self.ui.set_conversation_status("Error occurred")

    def _update_conversation_display(self):
        """Update the conversation display."""
        self.ui.conversation_text.config(state="normal")
        self.ui.conversation_text.delete("1.0", tk.END)

        for msg in self.conversation_history:
            role = msg["role"]
            content = msg["content"]
            
            if role == "user":
                self.ui.conversation_text.insert(tk.END, f"You: {content}\n\n")
            else:
                self.ui.conversation_text.insert(tk.END, f"Assistant: {content}\n\n")

        self.ui.conversation_text.see(tk.END)
        self.ui.conversation_text.config(state="disabled")

    def clear_conversation(self):
        """Clear the conversation history."""
        self.conversation_history = []
        self._update_conversation_display()
        self.ui.set_conversation_status("Conversation cleared")
        self._save_conversation_state()

    def upload_file(self):
        """Handle file upload."""
        file_path = filedialog.askopenfilename(
            title="Select a file to upload",
            filetypes=[
                ("All supported", "*.txt *.md *.pdf *.docx *.csv *.json *.xlsx"),
                ("Text files", "*.txt *.md"),
                ("PDF files", "*.pdf"),
                ("Word documents", "*.docx"),
                ("Spreadsheets", "*.csv *.xlsx"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )

        if file_path:
            try:
                result = process_uploaded_file(file_path)
                self.parsed_files.append(result)
                self._update_parsed_file_label()
                self._save_conversation_state()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to process file: {str(e)}")

    def _update_parsed_file_label(self):
        """Update the parsed file label."""
        if self.parsed_files:
            count = len(self.parsed_files)
            self.ui.parsed_file_label.config(text=f"{count} file(s) loaded")
        else:
            self.ui.parsed_file_label.config(text="No file loaded.")

    def clear_uploaded_files(self):
        """Clear uploaded files."""
        self.parsed_files = []
        self._update_parsed_file_label()
        self._save_conversation_state()

    def scrape_url(self):
        """Scrape content from a URL."""
        url = self.ui.url_entry.get().strip()
        if not url or url == self.ui.url_placeholder:
            messagebox.showerror("Error", "Please enter a URL to scrape.")
            return

        if not validate_url(url):
            messagebox.showerror("Error", "Please enter a valid URL.")
            return

        try:
            content = scrape_web_content(url)
            if content:
                result = {
                    "name": f"Scraped: {url}",
                    "content": content,
                    "url": url
                }
                self.parsed_files.append(result)
                self._update_parsed_file_label()
                self._save_conversation_state()
                messagebox.showinfo("Success", f"Successfully scraped content from {url}")
            else:
                messagebox.showerror("Error", "Failed to scrape content from the URL.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to scrape URL: {str(e)}")

    def analyze_login_form(self):
        """Analyze a page to help identify login form elements."""
        url = self.ui.url_entry.get().strip()

        if not url or url == self.ui.url_placeholder:
            messagebox.showerror("Error", "Please enter a URL to analyze.")
            return

        if not validate_url(url):
            messagebox.showerror("Error", "Please enter a valid URL.")
            return

        try:
            self.ui.analyze_button.config(text="Analyzing...", state="disabled")
            selectors = analyze_login_form_sync(url)

            if "error" in selectors:
                if selectors.get("manual_mode"):
                    dialog = ManualSelectorDialog(self, selectors, url)
                    dialog.show()
                else:
                    messagebox.showerror("Analysis Error", f"Analysis failed:\n{selectors['error']}")
                    self.ui.login_analyzed = False
                    self.ui.login_selectors = None
            else:
                dialog = LoginAnalysisDialog(self, selectors, url)
                dialog.show()

        except Exception as e:
            messagebox.showerror("Analysis Error", f"Failed to analyze login form:\n{str(e)}")
            self.ui.login_analyzed = False
            self.ui.login_selectors = None
        finally:
            self.ui.analyze_button.config(text="Analyze Login", state="normal")
            self._update_auth_button_states()

    def scrape_with_login(self):
        """Scrape content after authentication."""
        url = self.ui.url_entry.get().strip()
        username = self.ui.username_entry.get().strip()
        password = self.ui.password_entry.get().strip()

        if not url or url == self.ui.url_placeholder:
            messagebox.showerror("Error", "Please enter a URL to scrape.")
            return

        if not validate_url(url):
            messagebox.showerror("Error", "Please enter a valid URL.")
            return

        if not username or username == "Username":
            messagebox.showerror("Error", "Please enter a username.")
            return

        if not password or password == "Password":
            messagebox.showerror("Error", "Please enter a password.")
            return

        try:
            self.ui.login_scrape_button.config(text="Logging in...", state="disabled")
            
            login_selectors = self.ui.login_selectors if self.ui.login_analyzed else None
            result = scrape_with_login_sync(url, username, password, login_selectors)

            if result.get("requires_manual_verification"):
                verification_info = result.get("verification_info", {})
                dialog = VerificationRequiredDialog(self, verification_info, url)
                dialog.show()
                return

            if "Error" in result["name"] or "Failed" in result["name"]:
                messagebox.showerror("Authentication Error", result["content"])
                return

            # Success
            self.ui.authenticated_session = True
            self._update_auth_button_states()
            self.parsed_files.append(result)
            self._update_parsed_file_label()
            self._save_conversation_state()
            messagebox.showinfo("Success", f"Successfully authenticated and scraped {url}")

        except Exception as e:
            messagebox.showerror("Authentication Error", f"Failed to scrape with login:\n{str(e)}")
        finally:
            self.ui.login_scrape_button.config(text="Login & Scrape", state="normal")
            self._update_auth_button_states()

    def navigate_authenticated_site(self):
        """Show dialog for navigating authenticated site."""
        dialog = NavigationDialog(self)
        dialog.show()

    def _navigate_and_scrape_urls(self, urls, wait_between_loads):
        """Navigate to URLs and scrape content using authenticated session."""
        try:
            self.ui.set_conversation_status("Navigating authenticated site...")
            results = navigate_and_scrape_sync(urls, wait_between_loads)

            if "error" in results:
                messagebox.showerror("Navigation Error", f"Error during navigation: {results['error']}")
                return

            scraped_count = len([r for r in results.get("results", []) if "error" not in r])
            total_count = len(urls)

            summary = f"Navigation completed: {scraped_count}/{total_count} pages scraped successfully."
            self.ui.set_conversation_status(summary)

            if scraped_count > 0:
                self.parsed_files.extend([
                    {
                        "name": f"Navigation Result {i+1}: {r.get('url', 'Unknown')}",
                        "content": r.get("content", ""),
                        "url": r.get("url", ""),
                        "timestamp": r.get("timestamp", ""),
                    }
                    for i, r in enumerate(results.get("results", []))
                    if "error" not in r and r.get("content")
                ])
                self._update_parsed_file_label()

            messagebox.showinfo("Navigation Complete", summary)

        except Exception as e:
            error_msg = f"Navigation failed: {str(e)}"
            messagebox.showerror("Error", error_msg)
            self.ui.set_conversation_status("Navigation failed")

    def reset_authentication_state(self):
        """Reset authentication state and clear credentials."""
        # Clear URL
        self.ui.url_entry.delete(0, tk.END)
        self.ui.url_entry.insert(0, self.ui.url_placeholder)
        self.ui.url_entry.config(foreground="gray")

        # Clear credentials
        self.ui.username_entry.delete(0, tk.END)
        self.ui.username_entry.insert(0, "Username")
        self.ui.username_entry.config(foreground="gray")

        self.ui.password_entry.delete(0, tk.END)
        self.ui.password_entry.insert(0, "Password")
        self.ui.password_entry.config(foreground="gray", show="")

        # Reset authentication state flags
        self.ui.login_analyzed = False
        self.ui.authenticated_session = False
        self.ui.login_selectors = None

        # Update button states
        self._update_auth_button_states()
        self.ui.set_conversation_status("Authentication state reset")

        # Clear session data
        try:
            session_file = "scraper_sessions.json"
            if os.path.exists(session_file):
                os.remove(session_file)
        except Exception as e:
            logging.warning(f"Failed to clear session file: {e}")

    def _update_auth_button_states(self):
        """Update button states based on authentication workflow state."""
        if hasattr(self.ui, "login_analyzed") and self.ui.login_analyzed:
            self.ui.login_scrape_button.config(state="normal")
            self.ui.analyze_button.config(state="disabled")
        else:
            self.ui.login_scrape_button.config(state="disabled")
            self.ui.analyze_button.config(state="normal")

        if hasattr(self.ui, "authenticated_session") and self.ui.authenticated_session:
            self.ui.navigate_button.config(state="normal")
        else:
            self.ui.navigate_button.config(state="disabled")

    def _save_conversation_state(self):
        """Save conversation state to file."""
        try:
            state = {
                "conversation_history": self.conversation_history,
                "parsed_files": self.parsed_files,
            }
            with open(self.conversation_state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.warning(f"Failed to save conversation state: {e}")

    def _load_conversation_state(self):
        """Load conversation state from file."""
        try:
            if os.path.exists(self.conversation_state_file):
                with open(self.conversation_state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self.conversation_history = state.get("conversation_history", [])
                self.parsed_files = state.get("parsed_files", [])
                self._update_conversation_display()
                self._update_parsed_file_label()
        except Exception as e:
            logging.warning(f"Failed to load conversation state: {e}")

    def on_closing(self):
        """Handle window closing."""
        self._save_conversation_state()
        self.destroy()

    def run(self):
        """Run the main application loop."""
        self.mainloop()


def main():
    """Main entry point."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Suppress warnings
    warnings.filterwarnings("ignore", category=UserWarning)

    # Create and run GUI
    app = OllamaGUI()
    app.run()


if __name__ == "__main__":
    main()
