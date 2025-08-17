"""A tkinter-based GUI for the Dynamic Ollama Assistant."""

import logging
import os
import sys
import threading
import tkinter as tk
import warnings
import time
from tkinter import filedialog, messagebox, scrolledtext, ttk

import requests
import pandas as pd
from docling.document_converter import DocumentConverter

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
        self.parsed_document_content = None

        try:
            self.data_by_sheet = load_csvs(CSV_DIR, CSV_GLOB)
        except Exception as e:
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

        self.ui = UIComponents(self)
        self.populate_treeview()

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
            {
                p
                for field in fields_to_check
                for p in find_placeholders(str(field))
                if p != "parsed_document"
            }
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
        description = self.selected_prompt_row.get(
            "Description "
        ) or self.selected_prompt_row.get("Description")
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

        logging.info("Send pressed. is_thinking=%s", self.is_thinking)
        
        # Clear input first, then disable
        self.ui.user_input.delete(0, "end")
        
        # Disable input while we process to prevent overlapping streams
        try:
            self.ui.user_input.config(state="disabled")
        except Exception:
            pass
        self.update_chat_history(f"👤 User: {user_msg}\n\n")
        self.update_chat_history("🤖 Assistant: ")

        # Start thinking animation
        self.is_thinking = True
        self._thinking_animation()

        # Pass document content directly to the thread
        thread = threading.Thread(
            target=self.run_ollama_query, args=(user_msg, self.parsed_document_content)
        )
        thread.start()

    def clear_chat(self):
        """Clears the chat history."""
        self.ui.chat_history.config(state="normal")
        self.ui.chat_history.delete("1.0", "end")
        self.ui.chat_history.config(state="disabled")
        self.conversation_history = []  # Clear conversation history
        self.system_prompt = None  # Reset system prompt

    def run_ollama_query(self, user_msg, document_content):
        """Run the Ollama query in a separate thread."""
        if self.selected_prompt_row is not None:
            fill_values = {
                ph: entry.get() for ph, entry in self.ui.placeholder_entries.items()
            }
            if document_content:
                # Truncate very large content to reduce model startup latency
                content_to_attach = (
                    document_content[:20000] + "\n\n… [truncated]"
                    if len(document_content) > 20000
                    else document_content
                )
                logging.info(
                    "Attaching parsed document content to prompt (%d chars).",
                    len(content_to_attach),
                )
                fill_values["parsed_document"] = content_to_attach
            else:
                logging.warning(
                    "No parsed document content available to attach to prompt."
                )
            system_prompt, _ = build_system_prompt(
                self.selected_prompt_row, fill_values
            )
        else:
            # If no prompt is selected, use a generic system prompt but still allow
            # for document context to be included.
            fill_values = {}
            if document_content:
                content_to_attach = (
                    document_content[:20000] + "\n\n… [truncated]"
                    if len(document_content) > 20000
                    else document_content
                )
                logging.info(
                    "Attaching parsed document content to general chat (%d chars).",
                    len(content_to_attach),
                )
                fill_values["parsed_document"] = content_to_attach
            else:
                logging.warning(
                    "No parsed document content available for general chat."
                )

            # Create a dummy row for build_system_prompt
            base_prompt = "You are a helpful assistant."
            if document_content:
                base_prompt = """You are a helpful assistant with access to a user-provided document. 

When responding to queries:
- Use the document content to provide accurate, specific answers
- Quote relevant sections when appropriate
- If asked to summarize, provide a comprehensive summary of the document
- If the query relates to the document, prioritize information from the document
- If the document doesn't contain relevant information, clearly state that"""
            
            dummy_row = pd.Series(
                {
                    "Mega-Prompt": base_prompt,
                    "Prompt Name": "General Chat",
                    "Description": "",
                    "What This Mega-Prompt Does": "",
                    "Tips": "",
                    "How to Use": "",
                    "Additional Tips": "",
                }
            )
            system_prompt, _ = build_system_prompt(dummy_row, fill_values)

        # Only generate system prompt for the first message in conversation
        if not self.system_prompt:
            self.system_prompt = system_prompt
            logging.info("Generated initial system prompt for conversation")
        
        # Add user message to conversation history
        self.conversation_history.append({"role": "user", "content": user_msg})
        
        # Stream the response in this background thread; UI updates use `after`
        logging.info("Starting streaming for message")
        self._clear_and_stream_response(self.system_prompt, user_msg)
        logging.info("Finished streaming for message")

    def update_chat_history(self, message):
        """Update the chat history text widget in a thread-safe way."""
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
        logging.info(f"Starting to parse file: {file_path}")
        try:
            self._extracted_from__run_file_parsing_5(file_path)
        except Exception as e:
            logging.error(f"An error occurred during file parsing: {e}", exc_info=True)
            self.after(0, self._show_parsing_error, e)

    # TODO Rename this here and in `_run_file_parsing`
    def _extracted_from__run_file_parsing_5(self, file_path):
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

        if content_parts:
            self.parsed_document_content = "\n\n".join(content_parts)
            status_message = f"Loaded: {os.path.basename(file_path)}"
            logging.info(
                f"Successfully parsed and loaded file. Content length: {len(self.parsed_document_content)}"
            )
        else:
            self.parsed_document_content = ""
            status_message = (
                f"Could not extract content from: {os.path.basename(file_path)}"
            )
            logging.warning(
                f"Failed to extract content from {file_path}. ConversionResult had no document(s)."
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
                OLLAMA_MODEL, system_prompt, user_msg, self.conversation_history
            ):
                if first_chunk:
                    # Stop the animation and clear the ellipsis once the first chunk arrives
                    self.is_thinking = False

                    def _clear_ellipsis():
                        # Find and clear only the thinking dots after the last assistant message
                        self.ui.chat_history.config(state="normal")
                        # Get current content and find the last "🤖 Assistant:" 
                        content = self.ui.chat_history.get("1.0", "end")
                        last_assistant_pos = content.rfind("🤖 Assistant:")
                        if last_assistant_pos != -1:
                            # Find the position after "🤖 Assistant: " and clear only dots/ellipsis
                            lines = content[:last_assistant_pos].count('\n')
                            start_pos = f"{lines + 1}.{len('🤖 Assistant: ')}"
                            # Delete from after the label to end of that line only
                            line_end_pos = f"{lines + 1}.end"
                            current_line_content = self.ui.chat_history.get(start_pos, line_end_pos)
                            if current_line_content.strip() in [".", "..", "..."]:
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
                self.conversation_history.append({"role": "assistant", "content": full_response.strip()})
                
        except requests.exceptions.RequestException as e:
            self.update_chat_history(f"\n\n❌ API Error: {e}\n\n")
        finally:
            # Ensure thinking state is reset even if an error occurs
            self.is_thinking = False
            # Re-enable input
            try:
                self.ui.user_input.config(state="normal")
                self.ui.user_input.focus_set()
            except Exception:
                pass

    def _warm_up_model(self):
        """Send a tiny background request to keep the model warm."""
        try:
            # Minimal system prompt and user ping
            sys_prompt = "You are a helpful assistant. Reply with a single dot."
            for chunk in query_ollama_chat_for_gui(OLLAMA_MODEL, sys_prompt, "ping"):
                # Stop after first small chunk
                break
            logging.info("Model warm-up completed.")
        except Exception as e:
            logging.debug("Model warm-up skipped or failed: %s", e)

    def _thinking_animation(self, dot_count=0):
        """Animate the thinking ellipsis in the chat window."""
        if not self.is_thinking:
            return

        ellipsis = "." * ((dot_count % 3) + 1)
        if last_assistant_message_start := self.ui.chat_history.search(
            "🤖 Assistant:", "end-1l", backwards=True, regexp=False
        ):
            start_pos = f"{last_assistant_message_start} + 13c"
            self.ui.chat_history.config(state="normal")
            self.ui.chat_history.delete(start_pos, "end-1c")
            self.ui.chat_history.insert(start_pos, ellipsis, "assistant")
            self.ui.chat_history.config(state="disabled")

        self.thinking_animation_id = self.after(
            500, lambda: self._thinking_animation(dot_count + 1)
        )

    def run(self):
        """Run the main application loop."""
        self.mainloop()


if __name__ == "__main__":
    app = OllamaGUI()
    app.run()
