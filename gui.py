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
from tkinter import font as tkfont

import requests
import pandas as pd
from docling.document_converter import DocumentConverter

from dynamic_ollama_assistant import (
    CSV_DIR,
    CSV_GLOB,
    EXCEL_GLOB,
    DEFAULT_MODEL as OLLAMA_MODEL,  # Use the setting from the other module
    load_prompt_catalog,
    query_ollama_chat_for_gui,  # Import the new GUI-specific function
    build_system_prompt,
    find_placeholders,
)


class Tooltip:
    """A very small tooltip that shows on hover with dynamic text."""

    def __init__(self, widget, text_provider):
        self.widget = widget
        self.text_provider = text_provider  # callable returning str
        self.tipwindow = None
        self._after_id = None
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        widget.bind("<ButtonPress>", self._on_leave)

    def _on_enter(self, _event=None):
        # small delay before showing
        self._schedule(400, self._show_tooltip)

    def _on_leave(self, _event=None):
        self._cancel()
        self._hide_tooltip()

    def _schedule(self, delay_ms, func):
        self._cancel()
        self._after_id = self.widget.after(delay_ms, func)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show_tooltip(self):
        if self.tipwindow is not None:
            return
        text = (
            self.text_provider()
            if callable(self.text_provider)
            else str(self.text_provider)
        )
        if not text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            padx=6,
            pady=4,
            wraplength=400,
        )
        label.pack(ipadx=1)
        self.tipwindow = tw

    def _hide_tooltip(self):
        if self.tipwindow is not None:
            try:
                self.tipwindow.destroy()
            except Exception:
                pass
            self.tipwindow = None


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

        # Upload button (multi-file capable)
        self.upload_multi_button = ttk.Button(
            file_ops_frame,
            text="Upload Files",
            command=self.parent.upload_and_parse_files,
        )
        self.upload_multi_button.pack(side="left", padx=5, pady=5)

        # Right-side controls first to reserve space
        self.clear_files_button = ttk.Button(
            file_ops_frame, text="Clear Files", command=self.parent.clear_uploaded_files
        )
        self.clear_files_button.pack(side="right", padx=5, pady=5)

        self.manage_files_button = ttk.Button(
            file_ops_frame, text="Manage Files", command=self.parent.manage_parsed_files
        )
        self.manage_files_button.pack(side="right", padx=5, pady=5)

        # File summary label expands in remaining space
        self.parsed_file_label = ttk.Label(file_ops_frame, text="No file loaded.")
        self.parsed_file_label.pack(side="left", padx=5, pady=5, fill="x", expand=True)

        # Conversation Management Section
        conversation_frame = ttk.LabelFrame(
            content_area, text="Conversation Management"
        )
        conversation_frame.pack(fill="x", pady=5, anchor="n")
        # Use a responsive grid for conversation controls
        conv_inner = ttk.Frame(conversation_frame)
        conv_inner.pack(fill="x", expand=True)
        conv_inner.columnconfigure(4, weight=1)  # Status label stretches

        self.load_conversation_button = ttk.Button(
            conv_inner,
            text="Load Conversation",
            command=self.parent.load_conversation,
        )
        self.load_conversation_button.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.save_conversation_button = ttk.Button(
            conv_inner,
            text="Save Conversation",
            command=self.parent.save_conversation,
        )
        self.save_conversation_button.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Quick way to return to general chat (no specific prompt bound)
        self.general_chat_button = ttk.Button(
            conv_inner,
            text="General Chat",
            command=self.parent.switch_to_general_chat,
        )
        self.general_chat_button.grid(row=0, column=2, padx=5, pady=5, sticky="w")

        # Info icon popup for full status text
        def _show_status_popup():
            full = getattr(self.conversation_status_label, "full_text", "")
            win = tk.Toplevel(self.parent)
            win.title("Conversation Status")
            win.transient(self.parent)
            win.resizable(True, True)
            # Position near mouse
            x = self.parent.winfo_pointerx() + 12
            y = self.parent.winfo_pointery() + 12
            win.geometry(f"+{x}+{y}")
            frm = ttk.Frame(win, padding=10)
            frm.pack(fill="both", expand=True)
            lbl = ttk.Label(
                frm, text=full or "", justify="left", anchor="w", wraplength=600
            )
            lbl.pack(fill="both", expand=True)
            ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=(8, 6))
            btn = ttk.Button(frm, text="Close", command=win.destroy)
            btn.pack(anchor="e")

        self.info_button = ttk.Button(
            conv_inner, text="ⓘ", width=3, command=_show_status_popup
        )
        self.info_button.grid(row=0, column=3, padx=(0, 5), pady=5, sticky="w")

        # A stretching status area that ellipsizes text and shows a tooltip for full content
        status_frame = ttk.Frame(conv_inner)
        status_frame.grid(row=0, column=4, padx=5, pady=5, sticky="nsew")
        # Ensure this column grows
        conv_inner.columnconfigure(4, weight=1)
        self.conversation_status_label = ttk.Label(
            status_frame, text="No conversation loaded.", anchor="w", justify="left"
        )
        self.conversation_status_label.pack(fill="x", expand=True)

        # Store the full, non-truncated text
        self.conversation_status_label.full_text = "No conversation loaded."

        def _ellipsize_status_text(_event=None):
            # Ellipsize label text based on available width
            try:
                available = max(10, status_frame.winfo_width() - 10)
                full = getattr(self.conversation_status_label, "full_text", "")
                if not full:
                    self.conversation_status_label.config(text="")
                    # Hide icon if no text
                    if hasattr(self, "info_button"):
                        self.info_button.grid_remove()
                    return
                fnt = tkfont.Font(font=self.conversation_status_label["font"])  # type: ignore
                # If full text fits, show it and hide the icon
                if fnt.measure(full) <= available:
                    self.conversation_status_label.config(text=full)
                    if hasattr(self, "info_button"):
                        self.info_button.grid_remove()
                    return
                # Otherwise, show icon only (no truncated text)
                self.conversation_status_label.config(text="")
                if hasattr(self, "info_button"):
                    self.info_button.grid()
            except Exception:
                # Fallback to non-wrapped full text on any error
                self.conversation_status_label.config(
                    text=self.conversation_status_label.cget("text")
                )

        # Bind resize to re-ellipsize
        status_frame.bind("<Configure>", _ellipsize_status_text)
        conv_inner.bind("<Configure>", _ellipsize_status_text)

        # Tooltips: label (when visible) and icon (when shown)
        self._status_tooltip = Tooltip(
            self.conversation_status_label,
            lambda: self.conversation_status_label.full_text,
        )
        self._status_icon_tooltip = Tooltip(
            self.info_button, lambda: self.conversation_status_label.full_text
        )

        # Apply once initially so icon/text are mutually exclusive from the start
        self.parent.after(0, _ellipsize_status_text)

        # Expose helpers for external updates
        self._ellipsize_status_text = _ellipsize_status_text

        def set_conversation_status(text: str):
            self.conversation_status_label.full_text = text or ""
            _ellipsize_status_text()

        self.set_conversation_status = set_conversation_status

        # Context controls: preference + status
        self.context_pref_check = ttk.Checkbutton(
            conv_inner,
            text="Always restrict on switch",
            variable=self.parent.always_restrict_var,
            command=self.parent._save_conversation_state,
        )
        self.context_pref_check.grid(row=0, column=5, padx=5, pady=5, sticky="e")

        self.context_status_label = ttk.Label(conv_inner, text="Context: Shared")
        self.context_status_label.grid(row=0, column=6, padx=5, pady=5, sticky="e")

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
        input_frame.columnconfigure(0, weight=1)

        # Use a multi-line Text widget for input that auto-expands up to 8 lines
        self.user_input = tk.Text(
            input_frame,
            font=("Proxima Nova Alt", 10),
            wrap="word",
            height=1,
            state="normal",
        )
        self.user_input.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        # Buttons grouped in a bar so they remain visible on resize
        button_bar = ttk.Frame(input_frame)
        button_bar.grid(row=0, column=1, sticky="e")

        stop_button = ttk.Button(
            button_bar, text="Stop", command=self.parent.stop_response
        )
        stop_button.pack(side="left")

        send_button = ttk.Button(
            button_bar, text="Send", command=self.parent.send_message
        )
        send_button.pack(side="left", padx=(6, 0))

        clear_button = ttk.Button(
            button_bar, text="Clear", command=self.parent.clear_chat
        )
        clear_button.pack(side="left", padx=(6, 0))

        # Enter to send, Shift+Enter for newline
        def _on_return(event):
            # Only send if not holding Shift
            if not (event.state & 0x0001):  # Shift mask
                self.parent.send_message()
                return "break"
            return None

        self.user_input.bind("<Return>", _on_return)

        # Auto-resize on input changes up to 8 lines
        def _auto_resize(_event=None):
            try:
                lines = int(self.user_input.index("end-1c").split(".")[0])
            except Exception:
                lines = 1
            lines = max(1, min(8, lines))
            self.user_input.configure(height=lines)

        self.user_input.bind("<KeyRelease>", _auto_resize)


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
        self.parsed_files = []  # List[dict{name, content}] for multi-file support

        try:
            self.data_by_sheet = load_prompt_catalog(CSV_DIR, CSV_GLOB, EXCEL_GLOB)
        except (FileNotFoundError, IOError) as e:
            messagebox.showerror(
                "Failed to Load Prompts",
                f"An error occurred while loading the prompt catalog (CSV/Excel):\n\n{e}",
            )
            sys.exit(1)

        self.selected_prompt_row = None
        self.is_thinking = False
        self.thinking_animation_id = None
        self.conversation_history = []  # Track conversation messages
        self.system_prompt = None  # Store system prompt to avoid regenerating
        self._current_sheet_name = None
        self._current_row_index = None
        # Context carry-over controls
        self.context_restricted = False  # False => Shared (default), True => Restricted
        self.always_restrict_var = tk.BooleanVar(master=self, value=False)
        # Track which line the current assistant "typing" indicator lives on
        self.current_assistant_line_index: str | None = None
        # Event for stopping in-flight streaming responses
        self.stop_event = threading.Event()

        # Initialize UI first
        self.ui = UIComponents(self)
        self.populate_treeview()

        # Then load conversation state after UI is ready
        self._load_conversation_state()

        # Force proper layout calculation after UI creation
        self.update_idletasks()

        # Warm up Ollama model in the background to reduce first-response latency
        threading.Thread(target=self._warm_up_model, daemon=True).start()

        # Prompt to save on close and persist state
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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

            # Collapse categories by default; open only when searching
            sheet_node = self.ui.prompt_tree.insert(
                "",
                "end",
                text=str(sheet_name or "Unnamed Category"),
                open=bool(search_query),
            )

            for sub_cat, group in filtered_df.groupby("Sub-Category"):
                sub_cat_text = str(sub_cat or "Unnamed Sub-Category")
                # Collapse sub-categories by default; open only when searching
                sub_cat_node = self.ui.prompt_tree.insert(
                    sheet_node, "end", text=sub_cat_text, open=bool(search_query)
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

        # If there is an active conversation, optionally restrict context per preference
        has_chat_text = self.ui.chat_history.get("1.0", "end").strip()
        if self.conversation_history or has_chat_text:
            if bool(self.always_restrict_var.get()):
                self._clear_conversation_state()
                self.context_restricted = True
            else:
                choice = self._confirm_restrict_context()
                if choice is None:
                    return
                self.context_restricted = bool(choice)
                if choice is True:
                    self._clear_conversation_state()
            self._update_context_status_label()
            self._save_conversation_state()

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

    def _clear_prompt_ui(self):
        """Clear any prompt-specific UI (placeholders/description) and selection label."""
        for widget in self.ui.placeholder_frame.winfo_children():
            widget.destroy()
        for widget in self.ui.description_frame.winfo_children():
            widget.destroy()
        self.ui.placeholder_entries.clear()
        self.ui.selected_prompt_label.config(
            text="No Prompt Selected", font=("Proxima Nova Alt", 10, "italic")
        )

    def switch_to_general_chat(self):
        """Switch out of a specific prompt and back to general chat mode."""
        # Ask whether to restrict context if an active conversation exists
        has_chat_text = self.ui.chat_history.get("1.0", "end").strip()
        if self.conversation_history or has_chat_text:
            if bool(self.always_restrict_var.get()):
                self._clear_conversation_state()
                self.context_restricted = True
            else:
                choice = self._confirm_restrict_context()
                if choice is None:  # Cancel switch
                    return
                self.context_restricted = bool(choice)
                if choice is True:
                    self._clear_conversation_state()
            self._update_context_status_label()
            self._save_conversation_state()

        # By default keep current conversation; just detach from any selected prompt
        self.selected_prompt_row = None
        self._current_sheet_name = None
        self._current_row_index = None
        # Clear prompt-specific UI and mark the header
        self._clear_prompt_ui()
        self.ui.selected_prompt_label.config(
            text="General Chat", font=("Proxima Nova Alt", 10, "bold")
        )
        # Force system prompt to be rebuilt on next send (will include parsed doc if any)
        self.system_prompt = None

    def _update_context_status_label(self):
        """Update the context status label to reflect shared/restricted mode."""
        if hasattr(self.ui, "context_status_label"):
            mode = "Restricted" if self.context_restricted else "Shared"
            self.ui.context_status_label.config(text=f"Context: {mode}")

    def _clear_conversation_state(self):
        """Clears the conversation history and resets the chat UI."""
        self.conversation_history.clear()
        self.system_prompt = None
        self.ui.chat_history.config(state="normal")
        self.ui.chat_history.delete("1.0", "end")
        self.ui.chat_history.config(state="disabled")
        # Update status via ellipsis-aware setter
        if hasattr(self.ui, "set_conversation_status"):
            self.ui.set_conversation_status("No conversation loaded.")
        else:
            self.ui.conversation_status_label.config(text="No conversation loaded.")
        self._save_conversation_state()  # Persist the cleared state

    def _save_conversation_state(self):
        """Saves the current conversation history to a state file."""
        state = {
            "conversation_history": self.conversation_history,
            "system_prompt": self.system_prompt,
            "parsed_files": self.parsed_files,
            "parsed_document_content": self.parsed_document_content,
            "context_restricted": self.context_restricted,
            "always_restrict_on_switch": bool(self.always_restrict_var.get()),
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
                    self.parsed_files = state.get("parsed_files", []) or []
                    self.parsed_document_content = state.get("parsed_document_content")
                    self.context_restricted = bool(
                        state.get("context_restricted", False)
                    )
                    # Load preference; default False
                    self.always_restrict_var.set(
                        bool(state.get("always_restrict_on_switch", False))
                    )

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

                # Update parsed files label to reflect loaded state
                self._update_parsed_label_from_state()
                self._update_context_status_label()
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
            # Ensure uploaded document is present even if the template omitted it
            if getattr(self, "parsed_document_content", None):
                system_prompt = self._ensure_doc_appended(
                    system_prompt, self.parsed_document_content
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
        """Load chat text and return it along with the expected sidecar path for attachments."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        chat_content_start = content.find("👤 User:")
        chat_text = (
            content if chat_content_start == -1 else content[chat_content_start:]
        )

        base, _ = os.path.splitext(file_path)
        sidecar_path = base + ".json"
        return chat_text, sidecar_path

    def _display_loaded_conversation(self, chat_content, file_path, sidecar_path):
        """Update UI with loaded conversation and attach any saved files from sidecar."""
        # Reset current state to tie attachments to this conversation
        self._clear_conversation_state()

        # Load chat text
        self.ui.chat_history.config(state="normal")
        self.ui.chat_history.insert("1.0", chat_content)
        self.ui.chat_history.config(state="disabled")
        if hasattr(self.ui, "set_conversation_status"):
            self.ui.set_conversation_status(f"Loaded: {os.path.basename(file_path)}")
        else:
            self.ui.conversation_status_label.config(
                text=f"Loaded: {os.path.basename(file_path)}"
            )

        # Load attachments from sidecar if present
        try:
            if os.path.exists(sidecar_path):
                with open(sidecar_path, "r", encoding="utf-8") as jf:
                    sc = json.load(jf)
                self.parsed_files = sc.get("parsed_files", []) or []
                self.parsed_document_content = sc.get("parsed_document_content")
                # Invalidate system prompt so next turn reflects attachments
                self.system_prompt = None
                self._update_parsed_label_from_state()
        except (IOError, json.JSONDecodeError) as e:
            logging.warning("Failed to load attachments for conversation: %s", e)

        # Persist
        self._save_conversation_state()
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
            chat_content, sidecar_path = self._load_and_parse_conversation_file(
                file_path
            )
            self._display_loaded_conversation(chat_content, file_path, sidecar_path)
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load conversation:\n{e}")

    def _confirm_restrict_context(self) -> bool | None:
        """Ask whether to restrict context to the new chat.

        Returns:
            True  -> Restrict context (clear current conversation)
            False -> Keep context across chats (default)
            None  -> Cancel switch
        """
        result = messagebox.askyesnocancel(
            "Restrict Context?",
            "Do you want to restrict context to this chat?\n\n"
            "Yes: Start a fresh context for the new chat.\n"
            "No: Carry over the existing conversation context.",
            icon="question",
        )
        return result

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
            # Save human-readable transcript
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# Conversation Export\n")
                f.write(
                    f"Exported: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                )
                f.write(conversation_content)

            # Save sidecar with attachments so they can be restored with the transcript
            sidecar_path = os.path.splitext(file_path)[0] + ".json"
            sidecar = {
                "parsed_files": self.parsed_files or [],
                "parsed_document_content": self.parsed_document_content,
            }
            with open(sidecar_path, "w", encoding="utf-8") as jf:
                json.dump(sidecar, jf, indent=2)

            messagebox.showinfo(
                "Saved",
                f"Conversation saved as '{conversation_name}' (with attachments) in conversations folder",
            )
        except IOError as e:
            logging.error("Error saving conversation: %s", e)
            messagebox.showerror("Save Error", f"Failed to save conversation:\n{e}")

    def send_message(self, _event=None):
        """Send a message to the Ollama model and display the response."""
        # Text widget: fetch full text and strip trailing newline
        user_msg = self.ui.user_input.get("1.0", "end-1c").strip()
        if not user_msg or self.is_thinking:
            return

        # Reset any previous stop request before starting a new stream
        self.stop_event.clear()

        # Clear input box (Text indices)
        self.ui.user_input.delete("1.0", "end")
        self.update_chat_history(f"👤 User: {user_msg}\n\n")
        self.conversation_history.append({"role": "user", "content": user_msg})

        # Build an effective system prompt (base prompt + prompt-catalog hints)
        effective_system_prompt = self._build_effective_system_prompt(user_msg)

        self.is_thinking = True
        self.update_chat_history("🤖 Assistant: ")
        # Cancel any stray previous animation just in case
        if getattr(self, "thinking_animation_id", None):
            with contextlib.suppress(Exception):
                self.after_cancel(self.thinking_animation_id)
        self.thinking_animation_id = self.after(100, self._thinking_animation)

        # Use streaming helper that clears the thinking ellipsis on first chunk
        threading.Thread(
            target=self._clear_and_stream_response,
            args=(effective_system_prompt, user_msg),
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
        gen = query_ollama_chat_for_gui(
            model=OLLAMA_MODEL,
            system_prompt=system_prompt,
            user_msg=user_msg,
            conversation_history=self.conversation_history,
        )
        try:
            for chunk in gen:
                if self.stop_event.is_set():
                    # Close underlying HTTP stream via generator close
                    with contextlib.suppress(Exception):
                        gen.close()
                    break
                full_response += chunk
                self.update_chat_history(chunk)
        finally:
            # Ensure generator is closed if we exit early
            with contextlib.suppress(Exception):
                gen.close()

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
        """Insert text into the chat history widget with appropriate alignment, tracking the current assistant line."""
        self.ui.chat_history.config(state="normal")

        # Determine the correct tag based on the message sender
        tag = "user" if message.startswith("👤 User:") else "assistant"
        self.ui.chat_history.insert("end", message, tag)
        # If we just inserted the assistant label, remember its line index for the ellipsis animation
        if message.startswith("🤖 Assistant:"):
            # The cursor is at end-1c after insert; store just the line component
            end_index = self.ui.chat_history.index("end-1c")
            self.current_assistant_line_index = end_index.split(".")[0]

        self.ui.chat_history.config(state="disabled")
        self.ui.chat_history.yview("end")

    # ---- Prompt catalog helpers -------------------------------------------------
    def _search_prompts(
        self, query: str, limit: int = 20
    ) -> list[tuple[str, str, str]]:
        """Return top matches from the CSV catalog for a free-text query.

        Each result is a tuple: (sheet_name, sub_category, page_name)
        """
        q = (query or "").strip().lower()
        if not q:
            return []
        tokens = [t for t in q.replace("/", " ").replace("-", " ").split() if t]
        if not tokens:
            return []

        results: list[tuple[int, str, str, str]] = []
        for sheet_name, df in self.data_by_sheet.items():
            for _, row in df.iterrows():
                page = str(row.get("Short Description (PAGE NAME)") or "")
                subc = str(row.get("Sub-Category") or "")
                desc = str(row.get("Description") or row.get("Description ") or "")
                hay = " ".join([page, subc, desc]).lower()
                score = sum(hay.count(tok) for tok in tokens)
                if score > 0:
                    results.append((score, str(sheet_name), subc, page))

        results.sort(key=lambda x: x[0], reverse=True)
        return [(s, c, p) for _, s, c, p in results[:limit]]

    def _build_effective_system_prompt(self, user_msg: str) -> str:
        """Compose the system prompt for this turn, optionally appending catalog hints."""
        # Ensure base system prompt is available (may include parsed document, etc.)
        self._ensure_system_prompt()
        base = self.system_prompt or "You are a helpful assistant."

        matches = self._search_prompts(user_msg, limit=15)
        if not matches:
            return base

        lines = ["\n\nPROMPT CATALOG HINTS (top matches for user's query):"]
        for sheet, subc, page in matches:
            lines.append(f"- [{sheet} > {subc}] {page}")
        return base + "\n" + "\n".join(lines)

    def upload_and_parse_file(self):
        """Handle file upload in the main thread and start parsing in a background thread."""
        file_path = filedialog.askopenfilename(
            title="Select a file to parse",
            filetypes=[
                (
                    "All supported files",
                    "*.pdf *.docx *.html *.md *.pptx *.xlsx *.xls *.csv *.json",
                ),
                ("PDF files", "*.pdf"),
                ("Word documents", "*.docx"),
                ("HTML files", "*.html"),
                ("Markdown files", "*.md"),
                ("PowerPoint presentations", "*.pptx"),
                ("CSV files", "*.csv"),
                ("JSON files", "*.json"),
                ("Excel workbooks", "*.xlsx *.xls"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        base = os.path.basename(file_path)
        self.ui.parsed_file_label.config(
            text=f"Parsing {self._truncate_filename(base, max_len=32)}..."
        )
        self._set_parsed_label_tooltip(base)
        self.update_idletasks()

        thread = threading.Thread(target=self._run_file_parsing, args=(file_path,))
        thread.start()

    def upload_and_parse_files(self):
        """Select and parse multiple files in a background thread."""
        file_paths = filedialog.askopenfilenames(
            title="Select files to parse",
            filetypes=[
                (
                    "All supported files",
                    "*.pdf *.docx *.html *.md *.pptx *.xlsx *.xls *.csv *.json",
                ),
                ("PDF files", "*.pdf"),
                ("Word documents", "*.docx"),
                ("HTML files", "*.html"),
                ("Markdown files", "*.md"),
                ("PowerPoint presentations", "*.pptx"),
                ("CSV files", "*.csv"),
                ("JSON files", "*.json"),
                ("Excel workbooks", "*.xlsx *.xls"),
                ("All files", "*.*"),
            ],
        )
        if not file_paths:
            return
        self.ui.parsed_file_label.config(text=f"Parsing {len(file_paths)} file(s)...")
        self.update_idletasks()
        threading.Thread(
            target=self._run_files_parsing, args=(file_paths,), daemon=True
        ).start()

    def _run_file_parsing(self, file_path):
        """Run the file parsing logic in a separate thread."""
        logging.info("Starting to parse file: %s", file_path)
        try:
            self._parse_file_content(file_path)
        except IOError as e:
            logging.error("An error occurred during file parsing: %s", e, exc_info=True)
            self.after(0, self._show_parsing_error, e)

    def _run_files_parsing(self, file_paths):
        """Parse multiple files and aggregate their contents."""
        aggregated = []
        parsed_list = []
        for fp in file_paths:
            try:
                content = self._parse_single_file_collect(fp)
                if content:
                    parsed_list.append(
                        {"name": os.path.basename(fp), "content": content}
                    )
                    header = f"===== FILE: {os.path.basename(fp)} ====="
                    aggregated.append(f"{header}\n\n{content}")
            except Exception as e:
                logging.warning("Skipping file due to parse error: %s (%s)", fp, e)

        # Update state and label on UI thread by appending
        aggregated_text = "\n\n\n".join(aggregated) if aggregated else ""
        self.after(0, lambda: self._append_parsed_items(parsed_list, aggregated_text))

    def _parse_file_content(self, file_path):
        converter = DocumentConverter()
        result = None
        try:
            result = converter.convert(file_path)
        except Exception as e:
            logging.warning(
                "Docling conversion failed for %s: %s", os.path.basename(file_path), e
            )

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

        # Fallback for Excel using pandas if docling produced no content
        if not content_parts and (
            file_path.lower().endswith(".xlsx") or file_path.lower().endswith(".xls")
        ):
            try:
                excel = pd.ExcelFile(file_path)
                sheet_md_parts = []
                for sheet in excel.sheet_names:
                    try:
                        df = excel.parse(sheet)
                        # Limit overly large tables for responsiveness
                        preview = df.head(200)
                        md = preview.to_markdown(index=False)
                        sheet_md = f"# Sheet: {sheet}\n\n{md}"
                        sheet_md_parts.append(sheet_md)
                    except Exception as se:
                        sheet_md_parts.append(
                            f"# Sheet: {sheet}\n\n(Unable to parse sheet: {se})"
                        )
                if sheet_md_parts:
                    content_parts.append("\n\n---\n\n".join(sheet_md_parts))
                    logging.info(
                        "Parsed Excel via pandas fallback: %d sheet(s)",
                        len(sheet_md_parts),
                    )
            except Exception as e:
                logging.warning("Excel fallback failed: %s", e)

        # Fallback for CSV using pandas if docling produced no content
        if not content_parts and file_path.lower().endswith(".csv"):
            try:
                df = pd.read_csv(file_path, on_bad_lines="skip")
                preview = df.head(500)
                md = preview.to_markdown(index=False)
                content_parts.append(f"# CSV Preview (first 500 rows)\n\n{md}")
                logging.info(
                    "Parsed CSV via pandas fallback: %s rows previewed", len(preview)
                )
            except Exception as e:
                logging.warning("CSV fallback failed: %s", e)

        # Fallback for JSON: if array of objects, tabularize; else pretty-print
        if not content_parts and file_path.lower().endswith(".json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    df = pd.DataFrame(data)
                    preview = df.head(500)
                    md = preview.to_markdown(index=False)
                    content_parts.append(
                        f"# JSON Table Preview (first 500 rows)\n\n{md}"
                    )
                else:
                    pretty = json.dumps(data, indent=2, ensure_ascii=False)[:200000]
                    content_parts.append(f"```json\n{pretty}\n```")
                logging.info(
                    "Parsed JSON fallback for file: %s", os.path.basename(file_path)
                )
            except Exception as e:
                logging.warning("JSON fallback failed: %s", e)

        if content_parts:
            content_text = "\n\n".join(content_parts)
            item = {"name": os.path.basename(file_path), "content": content_text}
            header = f"===== FILE: {item['name']} =====\n\n{content_text}"
            # Append on UI thread to keep state consistent
            self.after(0, lambda: self._append_parsed_items([item], header))
            logging.info(
                "Successfully parsed file '%s' (length=%d) and appended to context.",
                item["name"],
                len(content_text),
            )
        else:
            logging.warning(
                "Failed to extract content from %s. ConversionResult had no document(s).",
                file_path,
            )
            self.after(
                0,
                lambda: self.ui.parsed_file_label.config(
                    text=(
                        "Could not extract content from: "
                        f"{self._truncate_filename(os.path.basename(file_path), max_len=32)}"
                    )
                ),
            )
            self.after(
                0, lambda: self._set_parsed_label_tooltip(os.path.basename(file_path))
            )

    def _append_parsed_items(self, new_items, aggregated_text: str):
        """Append parsed items and aggregated text to existing state and update label."""
        # Initialize containers if None
        if self.parsed_files is None:
            self.parsed_files = []
        if self.parsed_document_content is None:
            self.parsed_document_content = ""

        # Append items list
        if new_items:
            self.parsed_files.extend(new_items)

        # Append aggregated text with proper separator
        if aggregated_text:
            if self.parsed_document_content:
                self.parsed_document_content += "\n\n\n" + aggregated_text
            else:
                self.parsed_document_content = aggregated_text

        # Invalidate any previously cached system prompt so the next turn includes the new document
        # contents via `_ensure_system_prompt()` or explicit generation.
        self.system_prompt = None

        # Update label and persist
        self._update_parsed_label_from_state()
        self._save_conversation_state()

    def _update_parsed_label_from_state(self):
        """Update the parsed_file_label based on current parsed_files/document content."""
        total = len(self.parsed_files or [])
        if total > 0:
            # Truncate each displayed filename to avoid pushing UI buttons out of view
            names = ", ".join(
                self._truncate_filename(item["name"], max_len=24)
                for item in self.parsed_files[:3]
            )
            more = "" if total <= 3 else f" (+{total-3} more)"
            self.ui.parsed_file_label.config(
                text=f"Loaded: {total} file(s): {names}{more}"
            )
            # Tooltip with full filenames
            tooltip_text = "\n".join(
                item.get("name", "<unnamed>") for item in (self.parsed_files or [])
            )
            self._set_parsed_label_tooltip(tooltip_text)
        elif self.parsed_document_content:
            self.ui.parsed_file_label.config(text="Loaded: cached document")
            self._set_parsed_label_tooltip("Cached document content loaded")
        else:
            self.ui.parsed_file_label.config(text="No file loaded.")
            self._set_parsed_label_tooltip("")

    def manage_parsed_files(self):
        """Open a simple dialog to remove specific uploaded files."""
        if not (self.parsed_files or []):
            messagebox.showinfo("Manage Files", "No files to manage.")
            return

        top = tk.Toplevel(self)
        top.title("Manage Files")
        top.geometry("450x300")
        top.transient(self)
        top.grab_set()

        ttk.Label(top, text="Select files to remove:").pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        frame = ttk.Frame(top)
        frame.pack(fill="both", expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(frame, orient="vertical")
        listbox = tk.Listbox(frame, selectmode="extended", yscrollcommand=scrollbar.set)
        scrollbar.config(command=listbox.yview)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for item in self.parsed_files:
            listbox.insert("end", item.get("name", "<unnamed>"))

        btn_frame = ttk.Frame(top)
        btn_frame.pack(fill="x", padx=10, pady=10)

        def remove_selected():
            sel = listbox.curselection()
            if not sel:
                return
            names_to_remove = {listbox.get(i) for i in sel}
            self.parsed_files = [
                it
                for it in (self.parsed_files or [])
                if it.get("name") not in names_to_remove
            ]
            # Update UI/state
            self._update_parsed_label_from_state()
            self._save_conversation_state()
            # Refresh list
            listbox.delete(0, "end")
            for it in self.parsed_files:
                listbox.insert("end", it.get("name", "<unnamed>"))
            if not self.parsed_files:
                top.destroy()

        remove_btn = ttk.Button(
            btn_frame, text="Remove Selected", command=remove_selected
        )
        remove_btn.pack(side="left")

        close_btn = ttk.Button(btn_frame, text="Close", command=top.destroy)
        close_btn.pack(side="right")

    def _truncate_filename(self, filename: str, max_len: int = 24) -> str:
        """Truncate a filename with middle ellipsis, preserving extension when present."""
        if not filename or len(filename) <= max_len:
            return filename
        root, ext = os.path.splitext(filename)
        # Leave room for ext and ellipsis
        budget = max(5, max_len - len(ext) - 3)
        return (
            f"{self._truncate_middle(root, budget)}…{ext}"
            if ext
            else self._truncate_middle(filename, max_len)
        )

    def _truncate_middle(self, text: str, max_len: int) -> str:
        """Truncate the middle of a string with an ellipsis to fit max_len."""
        if len(text) <= max_len:
            return text
        half = (max_len - 1) // 2
        return f"{text[:half]}…{text[-(max_len - 1 - half):]}"

    # --- Tooltip helpers for showing full filenames on hover ---
    def _set_parsed_label_tooltip(self, text: str):
        """Attach or update a tooltip for the parsed files label."""
        # Create lazily
        if not hasattr(self, "_parsed_files_tooltip"):
            self._parsed_files_tooltip = ToolTip(self.ui.parsed_file_label, text=text)
        else:
            self._parsed_files_tooltip.text = text or ""

    def _parse_single_file_collect(self, file_path) -> str:
        """Parse a single file and return its extracted text without touching UI state."""
        converter = DocumentConverter()
        result = None
        try:
            result = converter.convert(file_path)
        except Exception as e:
            logging.warning(
                "Docling conversion failed for %s: %s", os.path.basename(file_path), e
            )

        content_parts = []
        if result:
            if hasattr(result, "documents") and result.documents:
                content_parts.extend(
                    doc.export_to_markdown() for doc in result.documents
                )
            elif hasattr(result, "document") and result.document:
                content_parts.append(result.document.export_to_markdown())

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
            except Exception as e:
                logging.warning("PPTX fallback failed for %s: %s", file_path, e)

        # Excel fallback
        if not content_parts and (
            file_path.lower().endswith(".xlsx") or file_path.lower().endswith(".xls")
        ):
            try:
                excel = pd.ExcelFile(file_path)
                sheet_md_parts = []
                for sheet in excel.sheet_names:
                    try:
                        df = excel.parse(sheet)
                        preview = df.head(200)
                        md = preview.to_markdown(index=False)
                        sheet_md_parts.append(f"# Sheet: {sheet}\n\n{md}")
                    except Exception as se:
                        sheet_md_parts.append(
                            f"# Sheet: {sheet}\n\n(Unable to parse sheet: {se})"
                        )
                if sheet_md_parts:
                    content_parts.append("\n\n---\n\n".join(sheet_md_parts))
            except Exception as e:
                logging.warning("Excel fallback failed for %s: %s", file_path, e)

        # CSV fallback
        if not content_parts and file_path.lower().endswith(".csv"):
            try:
                df = pd.read_csv(file_path, on_bad_lines="skip")
                preview = df.head(500)
                md = preview.to_markdown(index=False)
                content_parts.append(f"# CSV Preview (first 500 rows)\n\n{md}")
            except Exception as e:
                logging.warning("CSV fallback failed for %s: %s", file_path, e)

        # JSON fallback
        if not content_parts and file_path.lower().endswith(".json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    df = pd.DataFrame(data)
                    preview = df.head(500)
                    md = preview.to_markdown(index=False)
                    content_parts.append(
                        f"# JSON Table Preview (first 500 rows)\n\n{md}"
                    )
                else:
                    pretty = json.dumps(data, indent=2, ensure_ascii=False)[:200000]
                    content_parts.append(f"```json\n{pretty}\n```")
            except Exception as e:
                logging.warning("JSON fallback failed for %s: %s", file_path, e)

        return "\n\n".join(content_parts) if content_parts else ""

    def clear_uploaded_files(self):
        """Clear any uploaded/parsed files and their aggregated content."""
        self.parsed_files = []
        self.parsed_document_content = None
        self.ui.parsed_file_label.config(text="No file loaded.")
        self._set_parsed_label_tooltip("")
        self._save_conversation_state()

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
            gen = query_ollama_chat_for_gui(
                model=OLLAMA_MODEL,
                system_prompt=system_prompt,
                user_msg=user_msg,
                conversation_history=self.conversation_history,
            )
            for chunk in gen:
                if self.stop_event.is_set():
                    with contextlib.suppress(Exception):
                        gen.close()
                    break
                if first_chunk:
                    # Stop the animation and clear the ellipsis once the first chunk arrives
                    self.is_thinking = False

                    def _clear_ellipsis():
                        # Clear only the dots on the current assistant line, if tracked
                        if not self.current_assistant_line_index:
                            return
                        self.ui.chat_history.config(state="normal")
                        line_index = self.current_assistant_line_index
                        start_pos = f"{line_index}.0 + 13c"
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
            logging.info("Total response time: %.2fs", total_time)
            # Append the full response to the conversation history
            self.conversation_history.append(
                {"role": "assistant", "content": full_response}
            )
            # Save conversation state after each assistant response
            self._save_conversation_state()
            # Reset typing line tracking now that the response is finished
            self.current_assistant_line_index = None
            # Add spacing after assistant reply for clearer UI separation
            self.update_chat_history("\n\n")
        except requests.exceptions.RequestException as e:
            logging.error("Error during streaming: %s", e)
            self.after(0, messagebox.showerror, "Error", f"Failed to get response: {e}")
        finally:
            # Ensure thinking state is reset even if an error occurs
            self.is_thinking = False
            # Re-enable input
            with contextlib.suppress(tk.TclError):
                self.ui.user_input.config(state="normal")
                self.ui.user_input.focus_set()

    def stop_response(self):
        """Signal any in-flight streaming to stop and tidy up UI state."""
        self.stop_event.set()
        # Stop thinking animation immediately
        with contextlib.suppress(Exception):
            if getattr(self, "thinking_animation_id", None):
                self.after_cancel(self.thinking_animation_id)
                self.thinking_animation_id = None
        self.is_thinking = False

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
        # Only touch the line for the current assistant typing indicator
        if self.current_assistant_line_index:
            line_index = self.current_assistant_line_index
            start_pos = f"{line_index}.0 + 13c"
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
                # Guarantee the uploaded document is appended even if template missed it
                if fill_values.get("parsed_document"):
                    system_prompt = self._ensure_doc_appended(
                        system_prompt, fill_values["parsed_document"]
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

    def _ensure_doc_appended(self, prompt: str, document: str) -> str:
        """Append the uploaded document block to the prompt if it's not already present."""
        marker_tokens = [
            "---BEGIN DOCUMENT---",
            "USER-PROVIDED DOCUMENT",
            "BEGIN DOCUMENT",
        ]
        if any(tok in (prompt or "") for tok in marker_tokens):
            return prompt
        # Don't duplicate if a very long substring already present
        if document and document[:200] in (prompt or ""):
            return prompt
        return (
            (prompt or "You are a helpful assistant.")
            + "\n\nUSER-PROVIDED DOCUMENT:\n---BEGIN DOCUMENT---\n"
            + (document or "")
            + "\n---END DOCUMENT---\n"
        )

    def _on_close(self):
        """Handle application close: persist state, cancel animations, and destroy the window."""
        # Try to persist current state
        with contextlib.suppress(Exception):
            self._save_conversation_state()

        # Cancel any pending thinking animation
        with contextlib.suppress(Exception):
            if getattr(self, "thinking_animation_id", None):
                self.after_cancel(self.thinking_animation_id)
                self.thinking_animation_id = None

        # Optionally, you could prompt the user to confirm close if desired.
        with contextlib.suppress(Exception):
            self.destroy()

    def run(self):
        """Run the main application loop."""
        self.mainloop()


class ToolTip:
    """Simple tooltip for Tk widgets."""

    def __init__(self, widget, text: str = "", delay_ms: int = 350):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._tipwindow = None
        self._id = None
        self._x = self._y = 0
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<Motion>", self._motion, add="+")

    def _enter(self, _event=None):
        self._schedule()

    def _leave(self, _event=None):
        self._unschedule()
        self._hide_tip()

    def _motion(self, event):
        self._x = event.x_root + 12
        self._y = event.y_root + 8
        if self._tipwindow:
            self._tipwindow.wm_geometry(f"+{self._x}+{self._y}")

    def _schedule(self):
        self._unschedule()
        if not self.text:
            return
        self._id = self.widget.after(self.delay_ms, self._show_tip)

    def _unschedule(self):
        if self._id:
            try:
                self.widget.after_cancel(self._id)
            except Exception:
                pass
            self._id = None

    def _show_tip(self):
        if self._tipwindow or not self.text:
            return
        # Create a toplevel window
        self._tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{self._x}+{self._y}")
        label = ttk.Label(
            tw,
            text=self.text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            padding=(6, 3),
        )
        label.pack(ipadx=1)

    def _hide_tip(self):
        tw = self._tipwindow
        if tw:
            tw.destroy()
            self._tipwindow = None


if __name__ == "__main__":
    app = OllamaGUI()
    app.run()
