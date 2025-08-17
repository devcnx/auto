"""A tkinter-based GUI for the Dynamic Ollama Assistant."""

import tkinter as tk
import threading
from tkinter import ttk, scrolledtext

import requests
import pandas as pd

from dynamic_ollama_assistant import (
    load_csvs,
    build_system_prompt,
    find_placeholders,
    PromptData,
    query_ollama_chat_for_gui,  # Import the new GUI-specific function
    DEFAULT_MODEL as OLLAMA_MODEL,  # Use the setting from the other module
    CSV_DIR,
    CSV_GLOB,
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


class OllamaGUI(tk.Tk):
    """A GUI for interacting with the Dynamic Ollama Assistant."""

    def __init__(self):
        """Initialize the main application window."""
        super().__init__()
        self.title("Dynamic Ollama Assistant")
        self.geometry("1200x800")

        self.data_by_sheet = load_csvs(CSV_DIR, CSV_GLOB)
        self.selected_prompt_row = None

        self.ui = UIComponents(self)
        self.populate_treeview()

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
        # Clear previous prompt's details
        for widget in self.ui.placeholder_frame.winfo_children():
            widget.destroy()
        for widget in self.ui.description_frame.winfo_children():
            widget.destroy()
        self.ui.placeholder_entries.clear()
        self.ui.selected_prompt_label.config(
            text="No Prompt Selected", font=("Proxima Nova Alt", 10, "italic")
        )
        self.selected_prompt_row = None

        selected_item = self.ui.prompt_tree.selection()
        if not selected_item:
            return

        item_id = selected_item[0]
        if "|" not in item_id:
            return

        # Update the selected prompt label
        page_name = self.ui.prompt_tree.item(item_id, "text")
        self.ui.selected_prompt_label.config(
            text=f"Active: {page_name}", font=("Proxima Nova Alt", 10, "bold")
        )

        sheet_name, index_str = item_id.split("|")
        index = int(index_str)
        self.selected_prompt_row = self.data_by_sheet[sheet_name].loc[index]

        # --- Populate Placeholders and Description ---
        self._populate_details()

    def _populate_details(self):
        """Find and display placeholders and the description for the selected prompt."""
        self._populate_placeholders()
        self._populate_description()

    def _populate_placeholders(self):
        """Find and display placeholder entry fields for the selected prompt."""
        prompt_data = PromptData.from_series(self.selected_prompt_row)
        fields_to_check = [
            prompt_data.prompt_name,
            prompt_data.mega_prompt,
            prompt_data.description,
            prompt_data.what_this_does,
            prompt_data.tips,
            prompt_data.how_to_use,
            prompt_data.additional_tips,
        ]
        placeholders = sorted(
            {p for field in fields_to_check for p in find_placeholders(str(field))}
        )

        if not placeholders:
            ttk.Label(
                self.ui.placeholder_frame, text="No placeholders for this prompt."
            ).pack()
            return

        for i, ph in enumerate(placeholders):
            ttk.Label(self.ui.placeholder_frame, text=f"{ph}:").grid(
                row=i, column=0, sticky="w", padx=5, pady=2
            )
            entry = ttk.Entry(self.ui.placeholder_frame, width=50)
            entry.grid(row=i, column=1, sticky="ew", padx=5, pady=2)
            self.ui.placeholder_entries[ph] = entry
        self.ui.placeholder_frame.columnconfigure(1, weight=1)

    def _populate_description(self):
        """Display the prompt's description if it exists."""
        description = self.selected_prompt_row.get("Description ") or self.selected_prompt_row.get("Description")
        if pd.notna(description) and description.strip():
            self._display_prompt_description(description)

    def _display_prompt_description(self, description):
        """Render the prompt's description in the GUI."""
        ttk.Separator(self.ui.description_frame).pack(
            fill="x", expand=True, pady=(10, 5)
        )

        desc_label = ttk.Label(
            self.ui.description_frame,
            text="Description:",
            font=("Proxima Nova Alt", 10, "bold"),
        )
        desc_label.pack(anchor="w")

        # Use a ScrolledText widget for robust, read-only display
        desc_text = scrolledtext.ScrolledText(
            self.ui.description_frame,
            height=10,
            wrap="word",
            font=("Proxima Nova Alt", 10),
            relief="flat",
            borderwidth=0,
            bg=self.cget("background"),
        )
        desc_text.insert("1.0", description)
        desc_text.config(state="disabled")
        desc_text.pack(fill="both", expand=True)

    def send_message(self, _event=None):
        """Send the user's message to the Ollama model."""
        user_msg = self.ui.user_input.get().strip()
        if not user_msg:
            return

        self.ui.user_input.delete(0, "end")
        self.update_chat_history(f"👤 User: {user_msg}\n\n")

        thread = threading.Thread(target=self.run_ollama_query, args=(user_msg,))
        thread.start()

    def clear_chat(self):
        """Clears the chat history."""
        self.ui.chat_history.config(state="normal")
        self.ui.chat_history.delete("1.0", "end")
        self.ui.chat_history.config(state="disabled")

    def run_ollama_query(self, user_msg):
        """Run the Ollama query in a separate thread."""
        if self.selected_prompt_row is None:
            self.update_chat_history("🤖 Assistant: Please select a prompt first.\n")
            return

        fill_values = {
            ph: entry.get() for ph, entry in self.ui.placeholder_entries.items()
        }

        system_prompt, _ = build_system_prompt(self.selected_prompt_row, fill_values)

        self.update_chat_history("🤖 Assistant: ")
        full_response = ""
        try:
            for chunk in query_ollama_chat_for_gui(
                OLLAMA_MODEL, system_prompt, user_msg
            ):
                full_response += chunk
                self.update_chat_history(chunk)
            self.update_chat_history("\n\n")
        except requests.exceptions.RequestException as e:
            self.update_chat_history(f"\n\n❌ API Error: {e}\n\n")

    def update_chat_history(self, message):
        """Update the chat history text widget in a thread-safe way."""
        # Use `after` to schedule the update on the main thread
        self.after(0, self._insert_text, message)

    def _insert_text(self, message):
        """Insert text into the chat history widget with appropriate alignment."""
        self.ui.chat_history.config(state="normal")

        # Determine the correct tag based on the message sender
        tag = "user" if message.startswith("👤 User:") else "assistant"
        self.ui.chat_history.insert("end", message, tag)

        self.ui.chat_history.config(state="disabled")
        self.ui.chat_history.yview("end")


if __name__ == "__main__":
    app = OllamaGUI()
    app.mainloop()
