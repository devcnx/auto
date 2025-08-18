"""A tkinter-based GUI for the Dynamic Ollama Assistant."""

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

import requests
from docling.document_converter import DocumentConverter

from dynamic_ollama_assistant import (
    CSV_DIR,
    CSV_GLOB,
    DEFAULT_MODEL as OLLAMA_MODEL,  # Use the setting from the other module
    load_csvs,
    query_ollama_chat_for_gui,  # Import the new GUI-specific function
    build_system_prompt,
    find_placeholders,
)


class UIComponents:
    """
    A container for all UI widgets of the OllamaGUI.

    Fields:
        - parent: The OllamaGUI instance.
        :type parent: OllamaGUI

        - placeholder_entries: A dictionary of placeholder entries.
        :type placeholder_entries: dict

        - search_var: The search variable.
        :type search_var: tk.StringVar

        - prompt_tree: The treeview for displaying prompts.
        :type prompt_tree: ttk.Treeview

        - selected_prompt_label: The label for the selected prompt.
        :type selected_prompt_label: ttk.Label

        - placeholder_frame: The frame for placeholder entries.
        :type placeholder_frame: ttk.Frame

        - description_frame: The frame for prompt descriptions.
        :type description_frame: ttk.Frame

        - chat_history: The chat history widget.
        :type chat_history: scrolledtext.ScrolledText

        - user_input: The user input widget.
        :type user_input: ttk.Entry
    """

    def __init__(self, parent):
        """Initialize and create all UI components."""
        self.parent = parent  # The parent is the OllamaGUI instance
        self.placeholder_entries = {}

        # --- Main layout frames ---
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill="both", expand=True)

        paned_window = ttk.PanedWindow(main_frame, orient="horizontal")
        paned_window.pack(fill="both", expand=True)

        sidebar = ttk.Frame(paned_window, width=400)
        paned_window.add(sidebar, weight=1)

        content_area = ttk.Frame(paned_window)
        paned_window.add(content_area, weight=3)

        # --- Sidebar components ---
        self._create_sidebar_widgets(sidebar)

        # --- Content area components ---
        self._create_content_area_widgets(content_area)

    def _create_sidebar_widgets(self, sidebar):
        """Create widgets for the sidebar."""
        search_frame = ttk.Frame(sidebar)
        search_frame.pack(fill="x", pady=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(fill="x", padx=5, ipady=2)
        search_entry.insert(0, "Search prompts...")
        search_entry.bind("<FocusIn>", self.parent.clear_placeholder)
        search_entry.bind("<FocusOut>", self.parent.add_placeholder)
        self.search_var.trace_add("write", self.parent.on_search)

        button_frame = ttk.Frame(sidebar)
        button_frame.pack(fill="x", pady=5)
        expand_button = ttk.Button(
            button_frame, text="Expand All", command=self.parent.expand_all
        )
        expand_button.pack(side="left", padx=5, expand=True, fill="x")
        collapse_button = ttk.Button(
            button_frame, text="Collapse All", command=self.parent.collapse_all
        )
        collapse_button.pack(side="left", padx=5, expand=True, fill="x")

        self.prompt_tree = ttk.Treeview(sidebar)
        self.prompt_tree.pack(fill="both", expand=True)
        self.prompt_tree.bind("<<TreeviewSelect>>", self.parent.on_prompt_select)

    def update_response(self, chunk):
        """Update the chat display with a chunk of the response."""
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.insert(tk.END, chunk)
        self.chat_history.see(tk.END)
        self.chat_history.config(state=tk.DISABLED)
        self.chat_history.update_idletasks()

    def _create_content_area_widgets(self, content_area):
        """Create widgets for the main content area."""
        prompt_frame = ttk.LabelFrame(content_area, text="Prompt Details")
        prompt_frame.pack(fill="x", pady=(0, 10), anchor="n")

        self.selected_prompt_label = ttk.Label(
            prompt_frame,
            text="No Prompt Selected",
            font=("Proxima Nova Alt", 10, "italic"),
        )
        self.selected_prompt_label.pack(pady=5)

        self.description_frame = ttk.Frame(prompt_frame, padding="5 0 0 0")
        self.description_frame.pack(fill="x", expand=True, padx=10, pady=(0, 10))

        self.placeholder_frame = ttk.Frame(prompt_frame)
        self.placeholder_frame.pack(fill="x", padx=10, pady=10)

        file_ops_frame = ttk.LabelFrame(content_area, text="File Operations")
        file_ops_frame.pack(fill="x", pady=5, anchor="n")

        self.upload_button = ttk.Button(
            file_ops_frame,
            text="Upload & Parse File",
            command=self.parent.upload_and_parse_file,
        )
        self.upload_button.pack(side="left", padx=5, pady=5)

        self.parsed_file_label = ttk.Label(file_ops_frame, text="No file loaded.")
        self.parsed_file_label.pack(side="left", padx=5, pady=5, fill="x", expand=True)

        # Conversation Management Section
        conversation_frame = ttk.LabelFrame(
            content_area, text="Conversation Management"
        )
        conversation_frame.pack(fill="x", pady=5, anchor="n")

        self.load_conversation_button = ttk.Button(
            conversation_frame,
            text="Load Conversation",
            command=self.parent.load_conversation,
        )
        self.load_conversation_button.pack(side="left", padx=5, pady=5)

        self.save_conversation_button = ttk.Button(
            conversation_frame,
            text="Save Conversation",
            command=self.parent.save_conversation,
        )
        self.save_conversation_button.pack(side="left", padx=5, pady=5)

        self.conversation_status_label = ttk.Label(
            conversation_frame, text="No conversation loaded."
        )
        self.conversation_status_label.pack(
            side="left", padx=5, pady=5, fill="x", expand=True
        )

        chat_frame = ttk.LabelFrame(content_area, text="Chat")
        chat_frame.pack(fill="both", expand=True)

        self.chat_history = scrolledtext.ScrolledText(
            chat_frame, wrap="word", state="disabled", font=("Proxima Nova Alt", 10)
        )
        self.chat_history.pack(fill="both", expand=True, padx=10, pady=10)

        # Configure tags for chat message alignment
        self.chat_history.tag_configure("user", justify="right")
        self.chat_history.tag_configure("assistant", justify="left")

        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.user_input = ttk.Entry(input_frame, font=("Proxima Nova Alt", 10))
        self.user_input.pack(side="left", fill="x", expand=True)
        self.user_input.bind("<Return>", self.parent.send_message)

        clear_button = ttk.Button(
            input_frame, text="Clear", command=self.parent.clear_chat
        )
        clear_button.pack(side="right", padx=(0, 5))

        send_button = ttk.Button(
            input_frame, text="Send", command=self.parent.send_message
        )
        send_button.pack(side="right")


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
# Suppress PyTorch MPS pin_memory warnings on macOS
warnings.filterwarnings(
    "ignore",
    message=r".*'pin_memory' argument is set as true but not supported on MPS.*",
    category=UserWarning,
)


class OllamaGUI(tk.Tk):
    """A GUI for interacting with the Dynamic Ollama Assistant."""

    def __init__(self):
        """Initialize the main application window."""
        super().__init__()
        self.title("Dynamic Ollama Assistant")
        self.geometry("1200x800")
        self.minsize(1000, 600)  # Set minimum window size
        self.parsed_document_content = None

        try:
            self.data_by_sheet = load_csvs(CSV_DIR, CSV_GLOB)
        except (FileNotFoundError, IOError) as e:
            messagebox.showerror(
                "Failed to Load Prompts",
                f"An error occurred while loading the CSV files:\n\n{e}",
            )
            sys.exit(1)

        self.selected_prompt_row = None
        self.is_thinking = False
        self.thinking_animation_id = None
        self.conversation_history = []  # Track conversation messages
        self.system_prompt = None  # Store system prompt to avoid regenerating
        self._current_sheet_name = None
        self._current_row_index = None

        # Initialize UI first
        self.ui = UIComponents(self)
        self.populate_treeview()

        # Then load conversation state after UI is ready
        self._load_conversation_state()

        # Force proper layout calculation after UI creation
        self.update_idletasks()

        # Warm up Ollama model in the background to reduce first-response latency
        threading.Thread(target=self._warm_up_model, daemon=True).start()

    def expand_all(self):
        """Expand all nodes in the treeview."""
        self._toggle_all(True)

    def collapse_all(self):
        """Collapse all nodes in the treeview."""
        self._toggle_all(False)

    def _toggle_all(self, open_state: bool):
        """Recursively open or close all items in the treeview."""
        for item in self.ui.prompt_tree.get_children():
            self._toggle_children(item, open_state)

    def _toggle_children(self, parent: str, open_state: bool):
        """Recursively open or close all children of a parent node."""
        self.ui.prompt_tree.item(parent, open=open_state)
        for child in self.ui.prompt_tree.get_children(parent):
            self._toggle_children(child, open_state)

    def clear_placeholder(self, _event=None):
        """Clear placeholder text on focus."""
        if self.ui.search_var.get() == "Search prompts...":
            self.ui.search_var.set("")

    def add_placeholder(self, _event=None):
        """Add placeholder text if entry is empty."""
        if not self.ui.search_var.get():
            self.ui.search_var.set("Search prompts...")

    def on_search(self, *_args):
        """Filter the treeview based on the search query."""
        search_query = self.ui.search_var.get().lower()
        if search_query == "search prompts...":
            search_query = ""
        self.populate_treeview(search_query)

    def populate_treeview(self, search_query=""):
        """Populate the treeview with prompts, optionally filtered by a search query."""
        for item in self.ui.prompt_tree.get_children():
            self.ui.prompt_tree.delete(item)

        for sheet_name, df in self.data_by_sheet.items():
            # Create a copy to avoid modifying the original DataFrame
            filtered_df = df.copy()

            if search_query:
                # Ensure search works on string representations of columns
                mask = filtered_df.apply(
                    lambda row: search_query
                    in str(row["Short Description (PAGE NAME)"]).lower()
                    or search_query in str(row["Sub-Category"]).lower(),
                    axis=1,
                )
                filtered_df = filtered_df[mask]

            if filtered_df.empty:
                continue

            sheet_node = self.ui.prompt_tree.insert(
                "", "end", text=str(sheet_name or "Unnamed Category"), open=True
            )

            for sub_cat, group in filtered_df.groupby("Sub-Category"):
                sub_cat_text = str(sub_cat or "Unnamed Sub-Category")
                sub_cat_node = self.ui.prompt_tree.insert(
                    sheet_node, "end", text=sub_cat_text, open=True
                )
                for index, row in group.iterrows():
                    page_name = str(
                        row.get("Short Description (PAGE NAME)") or "Unnamed Prompt"
                    )
                    item_id = f"{sheet_name}|{index}"
                    self.ui.prompt_tree.insert(
                        sub_cat_node, "end", text=page_name, iid=item_id
                    )

    def on_prompt_select(self, _event=None):
        """Handle the event when a prompt is selected from the treeview."""
        selected_item = self.ui.prompt_tree.selection()
        if not selected_item:
            return

        item_id = selected_item[0]
        if "|" not in item_id:
            return

        # Parse the selected prompt info
        sheet_name, row_index = item_id.split("|")
        row_index = int(row_index)

        # Check if we're actually switching to a different prompt
        if (
            hasattr(self, "_current_sheet_name")
            and hasattr(self, "_current_row_index")
            and self._current_sheet_name == sheet_name
            and self._current_row_index == row_index
        ):
            # Same prompt selected, no need to clear conversation or UI
            return

        # Check if we have an active conversation and ask user what to do (only when switching prompts)
        has_chat_text = self.ui.chat_history.get("1.0", "end").strip()
        if (
            self.conversation_history or has_chat_text
        ) and not self._handle_conversation_switch():
            return

        # Clear previous prompt's details only when actually switching
        for widget in self.ui.placeholder_frame.winfo_children():
            widget.destroy()
        for widget in self.ui.description_frame.winfo_children():
            widget.destroy()
        self.ui.placeholder_entries.clear()
        self.ui.selected_prompt_label.config(
            text="No Prompt Selected", font=("Proxima Nova Alt", 10, "italic")
        )
        self.selected_prompt_row = None

        # Update the selected prompt label
        page_name = self.ui.prompt_tree.item(item_id, "text")
        self.ui.selected_prompt_label.config(
            text=f"Active: {page_name}", font=("Proxima Nova Alt", 10, "bold")
        )

        sheet_name, index_str = item_id.split("|")
        index = int(index_str)
        self.selected_prompt_row = self.data_by_sheet[sheet_name].loc[index]
        self._current_sheet_name = sheet_name  # Track current sheet for comparison
        self._current_row_index = index  # Track current row index for comparison

        # --- Populate Placeholders and Description ---
        self._populate_details()

    def _clear_conversation_state(self):
        """Clears the conversation history and resets the chat UI."""
        self.conversation_history.clear()
        self.system_prompt = None
        self.ui.chat_history.config(state="normal")
        self.ui.chat_history.delete("1.0", "end")
        self.ui.chat_history.config(state="disabled")
        self.ui.conversation_status_label.config(text="No conversation loaded.")
        self._save_conversation_state()  # Persist the cleared state

    def _save_conversation_state(self):
        """Saves the current conversation history to a state file."""
        state = {
            "conversation_history": self.conversation_history,
            "system_prompt": self.system_prompt,
        }
        try:
            with open("conversation_state.json", "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except IOError as e:
            logging.warning("Could not save conversation state: %s", e)

    def _load_conversation_state(self):
        """Loads conversation history from a state file if it exists."""
        try:
            if os.path.exists("conversation_state.json"):
                with open("conversation_state.json", "r", encoding="utf-8") as f:
                    state = json.load(f)
                    self.conversation_history = state.get("conversation_history", [])
                    self.system_prompt = state.get("system_prompt")

                # Repopulate chat history UI
                self.ui.chat_history.config(state="normal")
                self.ui.chat_history.delete("1.0", "end")
                for msg in self.conversation_history:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    if role == "user":
                        self.update_chat_history(f"👤 User: {content}\n\n")
                    elif role == "assistant":
                        self.update_chat_history(f"🤖 Assistant: {content}\n\n")
                self.ui.chat_history.config(state="disabled")
        except (IOError, json.JSONDecodeError) as e:
            logging.warning("Could not load conversation state: %s", e)
            self.conversation_history = []

    def _populate_details(self):
        """Populate the UI with details from the selected prompt row."""
        if self.selected_prompt_row is None:
            return

        # --- Description Only --- (align with CSV columns in dynamic_ollama_assistant)
        description = (
            self.selected_prompt_row.get("Description ")
            or self.selected_prompt_row.get("Description")
            or "No description available."
        )

        # Only show the description; do NOT include the mega-prompt or other long fields
        desc_text = str(description).strip()

        desc_label = ttk.Label(
            self.ui.description_frame,
            text=desc_text,
            wraplength=400,
            justify="left",
        )
        desc_label.pack(fill="x")

        # --- Placeholders --- (collect from 'Mega-Prompt' and related fields)
        mega_prompt = self.selected_prompt_row.get("Mega-Prompt", "")
        prompt_name = self.selected_prompt_row.get("Prompt Name", "")
        fields_to_scan = [
            mega_prompt,
            # Restrict placeholder scanning to mega_prompt (and prompt_name for safety)
            prompt_name,
        ]
        placeholders = sorted(
            {ph for field in fields_to_scan for ph in find_placeholders(str(field))}
        )

        # Dynamically create input fields for each placeholder
        for placeholder in placeholders:
            row_frame = ttk.Frame(self.ui.placeholder_frame)
            row_frame.pack(fill="x", pady=2)
            label = ttk.Label(row_frame, text=f"{placeholder}:", width=20)
            label.pack(side="left")
            entry = ttk.Entry(row_frame)
            entry.pack(side="left", fill="x", expand=True)
            self.ui.placeholder_entries[placeholder] = entry

        # Add a button to generate the system prompt
        generate_button = ttk.Button(
            self.ui.placeholder_frame,
            text="Generate System Prompt",
            command=self._generate_system_prompt,
        )
        generate_button.pack(pady=10)

    def _generate_system_prompt(self):
        """Build the system prompt using CSV schema and include parsed document if any."""
        if self.selected_prompt_row is None:
            return

        # Collect values from the entry fields
        fill_values = {
            key: entry.get().strip()
            for key, entry in self.ui.placeholder_entries.items()
            if entry.get().strip()
        }
        # Include parsed document content for use by build_system_prompt
        if getattr(self, "parsed_document_content", None):
            fill_values["parsed_document"] = self.parsed_document_content

        try:
            system_prompt, _ = build_system_prompt(
                self.selected_prompt_row, fill_values
            )
            self.system_prompt = system_prompt
            messagebox.showinfo(
                "System Prompt Set",
                "The system prompt has been generated and is ready for your next message.",
            )
        except Exception as e:
            logging.exception("Failed to generate system prompt")
            messagebox.showerror(
                "System Prompt Error",
                f"Failed to generate system prompt: {e}",
            )

    def _load_and_parse_conversation_file(self, file_path):
        """Loads and parses the content of a conversation file."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        chat_content_start = content.find("👤 User:")
        # Fallback for older formats or plain text files
        return content if chat_content_start == -1 else content[chat_content_start:]

    def _display_loaded_conversation(self, chat_content, file_path):
        """Updates the UI to display the loaded conversation content."""
        self._clear_conversation_state()
        self.ui.chat_history.config(state="normal")
        self.ui.chat_history.insert("1.0", chat_content)
        self.ui.chat_history.config(state="disabled")
        self.ui.conversation_status_label.config(
            text=f"Loaded: {os.path.basename(file_path)}"
        )
        messagebox.showinfo("Success", "Conversation loaded successfully.")

    def load_conversation(self):
        """Load a conversation from a file."""
        conversations_dir = os.path.join(os.path.dirname(__file__), "conversations")
        file_path = filedialog.askopenfilename(
            title="Load Conversation",
            initialdir=conversations_dir,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not file_path:
            return

        try:
            chat_content = self._load_and_parse_conversation_file(file_path)
            self._display_loaded_conversation(chat_content, file_path)
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load conversation:\n{e}")

    def _handle_conversation_switch(self):
        """Handle switching chats, offering to save/clear the conversation."""

        result = messagebox.askyesnocancel(
            "Save Conversation?",
            "You have an active conversation. Would you like to:\n\n"
            "• Yes - Save conversation to a file\n"
            "• No - Clear conversation and continue\n"
            "• Cancel - Stay in current mode",
            icon="question",
        )

        if result is None:  # Cancel
            return False
        elif result is True:  # Yes - Save
            self.save_conversation()
            self._clear_conversation_state()
            return True
        else:  # No - Clear
            self._clear_conversation_state()
            return True

    def clear_chat(self):
        """Clears the current chat conversation."""
        self._clear_conversation_state()

    def save_conversation(self):
        """Save the current conversation to the conversations directory."""

        # Get conversation content from chat history
        conversation_content = self.ui.chat_history.get("1.0", "end").strip()
        if not conversation_content:
            messagebox.showwarning("No Content", "No conversation to save.")
            return

        # Create conversations directory if it doesn't exist
        conversations_dir = os.path.join(os.path.dirname(__file__), "conversations")
        os.makedirs(conversations_dir, exist_ok=True)

        # Ask user for conversation name
        conversation_name = simpledialog.askstring(
            "Save Conversation",
            "Enter a name for this conversation:",
            initialvalue=f"conversation_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        )

        if not conversation_name:
            return

        # Ensure .txt extension
        if not conversation_name.endswith(".txt"):
            conversation_name += ".txt"

        file_path = os.path.join(conversations_dir, conversation_name)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# Conversation Export\n")
                f.write(
                    f"Exported: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                )
                f.write(conversation_content)
            messagebox.showinfo(
                "Saved",
                f"Conversation saved as '{conversation_name}' in conversations folder",
            )
        except IOError as e:
            logging.error("Error saving conversation: %s", e)
            messagebox.showerror("Save Error", f"Failed to save conversation:\n{e}")

    def send_message(self, _event=None):
        """Send a message to the Ollama model and display the response."""
        user_msg = self.ui.user_input.get().strip()
        if not user_msg or self.is_thinking:
            return

        self.ui.user_input.delete(0, "end")
        self.update_chat_history(f"👤 User: {user_msg}\n\n")
        self.conversation_history.append({"role": "user", "content": user_msg})

        # Ensure we have a system prompt if user hasn't generated one yet
        self._ensure_system_prompt()

        self.is_thinking = True
        self.update_chat_history("🤖 Assistant: ")
        self.thinking_animation_id = self.after(100, self._thinking_animation)

        # Use streaming helper that clears the thinking ellipsis on first chunk
        threading.Thread(
            target=self._clear_and_stream_response,
            args=(self.system_prompt or "", user_msg),
            daemon=True,
        ).start()

    def _stream_and_process_response(self, user_msg):
        """Helper to stream response from Ollama and update conversation state."""
        try:
            self._stream_ollama_response(user_msg)
        except requests.exceptions.RequestException as e:
            logging.error("Error in Ollama query: %s", e)
            self.after(0, messagebox.showerror, "Error", f"Failed to get response: {e}")
        finally:
            self.is_thinking = False

    def _stream_ollama_response(self, user_msg):
        system_prompt = self.system_prompt or ""
        full_response = ""

        # Stream the response from Ollama
        for chunk in query_ollama_chat_for_gui(
            model=OLLAMA_MODEL,
            system_prompt=system_prompt,
            user_msg=user_msg,
            conversation_history=self.conversation_history,
        ):
            full_response += chunk
            self.update_chat_history(chunk)

        # Add assistant's response to conversation history
        self.conversation_history.append(
            {"role": "assistant", "content": full_response}
        )
        self.ui.chat_history.config(state=tk.DISABLED)

        # Save conversation state after each assistant response
        self._save_conversation_state()

    def update_chat_history(self, message):
        """Update the chat history in a thread-safe manner."""
        # ... (rest of the method remains the same)
        # Use `after` to schedule the update on the main thread
        self.after(0, self._insert_text, message)

    def _insert_text(self, message):
        """Insert text into the chat historyfrtn widget with appropriate alignment."""
        self.ui.chat_history.config(state="normal")

        # Determine the correct tag based on the message sender
        tag = "user" if message.startswith("👤 User:") else "assistant"
        self.ui.chat_history.insert("end", message, tag)

        self.ui.chat_history.config(state="disabled")
        self.ui.chat_history.yview("end")

    def upload_and_parse_file(self):
        """Handle file upload in the main thread and start parsing in a background thread."""
        file_path = filedialog.askopenfilename(
            title="Select a file to parse",
            filetypes=[
                ("All supported files", "*.pdf;*.docx;*.html;*.md;*.pptx"),
                ("PDF files", "*.pdf"),
                ("Word documents", "*.docx"),
                ("HTML files", "*.html"),
                ("Markdown files", "*.md"),
                ("PowerPoint presentations", "*.pptx"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        self.ui.parsed_file_label.config(
            text=f"Parsing {os.path.basename(file_path)}..."
        )
        self.update_idletasks()

        thread = threading.Thread(target=self._run_file_parsing, args=(file_path,))
        thread.start()

    def _run_file_parsing(self, file_path):
        """Run the file parsing logic in a separate thread."""
        logging.info("Starting to parse file: %s", file_path)
        try:
            self._parse_file_content(file_path)
        except IOError as e:
            logging.error("An error occurred during file parsing: %s", e, exc_info=True)
            self.after(0, self._show_parsing_error, e)

    def _parse_file_content(self, file_path):
        converter = DocumentConverter()
        result = converter.convert(file_path)

        content_parts = []
        if result:
            # Newer docling may return a list of documents
            if hasattr(result, "documents") and result.documents:
                content_parts.extend(
                    doc.export_to_markdown() for doc in result.documents
                )
            # Older/other versions may return a single document
            elif hasattr(result, "document") and result.document:
                content_parts.append(result.document.export_to_markdown())

        # Fallback for PPTX using python-pptx if docling produced no content
        if not content_parts and file_path.lower().endswith(".pptx"):
            try:
                from pptx import Presentation

                prs = Presentation(file_path)
                slides_text = []
                for slide in prs.slides:
                    slides_text.extend(
                        shape.text for shape in slide.shapes if hasattr(shape, "text")
                    )
                if slides_text:
                    content_parts.append("\n\n".join(slides_text))
                    logging.info("Parsed PPTX via python-pptx fallback.")
            except Exception as e:
                logging.warning("PPTX fallback failed: %s", e)

        if content_parts:
            self.parsed_document_content = "\n\n".join(content_parts)
            status_message = f"Loaded: {os.path.basename(file_path)}"
            logging.info(
                "Successfully parsed and loaded file. Content length: %d",
                len(self.parsed_document_content),
            )
        else:
            self.parsed_document_content = ""
            status_message = (
                f"Could not extract content from: {os.path.basename(file_path)}"
            )
            logging.warning(
                "Failed to extract content from %s. ConversionResult had no document(s).",
                file_path,
            )

        self.after(0, lambda: self.ui.parsed_file_label.config(text=status_message))

    def _show_parsing_error(self, error):
        """Display parsing error in a thread-safe way."""
        self.ui.parsed_file_label.config(text="Failed to parse file.")
        messagebox.showerror(
            "Parsing Error", f"An error occurred while parsing the file:\n{error}"
        )

    def _clear_and_stream_response(self, system_prompt, user_msg):
        """Keep thinking until first chunk, then clear and stream the response from Ollama."""
        try:
            full_response = ""
            first_chunk = True
            start_time = time.time()
            for chunk in query_ollama_chat_for_gui(
                model=OLLAMA_MODEL,
                system_prompt=system_prompt,
                user_msg=user_msg,
                conversation_history=self.conversation_history,
            ):
                if first_chunk:
                    # Stop the animation and clear the ellipsis once the first chunk arrives
                    self.is_thinking = False

                    def _clear_ellipsis():
                        # Find and clear only the thinking dots after the last assistant label on the same line
                        self.ui.chat_history.config(state="normal")
                        if last_assistant_message_start := self.ui.chat_history.search(
                            "🤖 Assistant:", "end-1l", backwards=True, regexp=False
                        ):
                            start_pos = f"{last_assistant_message_start} + 13c"
                            line_index = last_assistant_message_start.split(".")[0]
                            line_end_pos = f"{line_index}.end"
                            current_line_content = self.ui.chat_history.get(
                                start_pos, line_end_pos
                            )
                            if current_line_content.strip() in {".", "..", "..."}:
                                self.ui.chat_history.delete(start_pos, line_end_pos)
                        self.ui.chat_history.config(state="disabled")

                    self.after(0, _clear_ellipsis)
                    ttfb = time.time() - start_time
                    logging.info("TTFB (time-to-first-byte): %.2fs", ttfb)
                    first_chunk = False

                full_response += chunk
                self.update_chat_history(chunk)
            total_time = time.time() - start_time
            logging.info("Total stream time: %.2fs", total_time)
            self.update_chat_history("\n\n")

            # Add assistant response to conversation history
            if full_response.strip():
                self.conversation_history.append(
                    {"role": "assistant", "content": full_response.strip()}
                )

        except requests.exceptions.RequestException as e:
            self.update_chat_history(f"\n\n❌ API Error: {e}\n\n")
        finally:
            # Ensure thinking state is reset even if an error occurs
            self.is_thinking = False
            # Re-enable input
            with contextlib.suppress(tk.TclError):
                self.ui.user_input.config(state="normal")
                self.ui.user_input.focus_set()

    def _warm_up_model(self):
        """Send a tiny background request to keep the model warm."""
        try:
            # Minimal system prompt and user ping
            sys_prompt = "You are a helpful assistant. Reply with a single dot."
            for _ in query_ollama_chat_for_gui(
                model=OLLAMA_MODEL,
                system_prompt=sys_prompt,
                user_msg="ping",
                conversation_history=[],
            ):
                # Stop after first small chunk
                break
            logging.info("Model warm-up completed.")
        except requests.exceptions.RequestException as e:
            logging.debug("Model warm-up skipped or failed: %s", e)

    def _thinking_animation(self, dot_count=0):
        """Animate the thinking ellipsis in the chat window."""
        if not self.is_thinking:
            return

        ellipsis = "." * ((dot_count % 3) + 1)
        if last_assistant_message_start := self.ui.chat_history.search(
            "🤖 Assistant:", "end-1l", backwards=True, regexp=False
        ):
            # Calculate start and end only within the same line as the label
            line_index = last_assistant_message_start.split(".")[0]
            start_pos = f"{last_assistant_message_start} + 13c"
            line_end_pos = f"{line_index}.end"
            self.ui.chat_history.config(state="normal")
            self.ui.chat_history.delete(start_pos, line_end_pos)
            self.ui.chat_history.insert(start_pos, ellipsis, "assistant")
            self.ui.chat_history.config(state="disabled")

        self.thinking_animation_id = self.after(
            500, lambda: self._thinking_animation(dot_count + 1)
        )

    def _ensure_system_prompt(self):
        """Ensure there is a system prompt ready, auto-including parsed document if available."""
        if self.system_prompt:
            return

        fill_values = {}
        if getattr(self, "parsed_document_content", None):
            fill_values["parsed_document"] = self.parsed_document_content

        try:
            if self.selected_prompt_row is not None:
                # Build using the selected row schema so placeholders are respected
                system_prompt, _ = build_system_prompt(
                    self.selected_prompt_row, fill_values
                )
                self.system_prompt = system_prompt
            elif fill_values.get("parsed_document"):
                # Fallback minimal system prompt that includes the document
                doc = fill_values["parsed_document"]
                self.system_prompt = (
                    "You are a helpful assistant. Use the provided document to answer.\n\n"
                    "USER-PROVIDED DOCUMENT:\n---BEGIN DOCUMENT---\n"
                    f"{doc}\n"
                    "---END DOCUMENT---\n"
                )
            else:
                # Final fallback minimal prompt
                self.system_prompt = "You are a helpful assistant."
        except Exception as e:
            logging.warning("Auto system prompt generation failed: %s", e)
            # Ensure we still have something
            if not self.system_prompt:
                self.system_prompt = "You are a helpful assistant."

    def run(self):
        """Run the main application loop."""
        self.mainloop()


if __name__ == "__main__":
    app = OllamaGUI()
    app.run()
