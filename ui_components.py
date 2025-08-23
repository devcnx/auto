"""
UI Components for the Dynamic Ollama Assistant GUI.

This module contains the UI component classes and helper functions. It is intended to be used
as a component of the Dynamic Ollama Assistant GUI.

Imports:
    - tkinter: The main GUI framework.
    - ttk: The ttk module for creating the UI components.
    - webbrowser: The webbrowser module for opening web pages.
"""

import tkinter as tk
from tkinter import ttk
import webbrowser


class UIComponents:
    """Container for all UI components."""

    def __init__(self, parent):
        self.parent = parent
        self.setup_ui()

    def setup_ui(self):
        """Initialize all UI components."""
        # Authentication state
        self.login_analyzed = False
        self.authenticated_session = False
        self.login_selectors = None

        # Create main frames
        self._create_main_frames()
        self._create_conversation_area()
        self._create_input_area()
        self._create_file_management()
        self._create_web_scraping()
        self._create_authentication()

    def _create_main_frames(self):
        """Create the main layout frames using grid for better responsive design."""
        # Configure main window grid
        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)

        # Main container with resizable paned window
        self.main_paned = ttk.PanedWindow(self.parent, orient="horizontal")
        self.main_paned.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Left panel for conversation
        self.left_panel = ttk.Frame(self.main_paned)
        self.main_paned.add(self.left_panel, weight=3)  # Takes 75% of space initially

        # Right panel for controls (sidebar)
        self.right_panel = ttk.Frame(self.main_paned)
        self.main_paned.add(self.right_panel, weight=1)  # Takes 25% of space initially

        # Configure right panel grid for scrollable content
        self.right_panel.grid_rowconfigure(0, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        # Create canvas and scrollbar for right panel
        self.canvas = tk.Canvas(self.right_panel, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            self.right_panel, orient="vertical", command=self.canvas.yview
        )
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.canvas.bind("<MouseWheel>", _on_mousewheel)

    def _create_conversation_area(self):
        """Create the conversation display area."""
        # Configure left panel grid
        self.left_panel.grid_rowconfigure(0, weight=1)  # Conversation expands
        self.left_panel.grid_rowconfigure(1, weight=0)  # Status label fixed
        self.left_panel.grid_rowconfigure(2, weight=0)  # Input area fixed
        self.left_panel.grid_rowconfigure(3, weight=0)  # Button area fixed
        self.left_panel.grid_columnconfigure(0, weight=1)

        # Conversation frame
        conversation_frame = ttk.LabelFrame(
            self.left_panel, text="Conversation", padding="5"
        )
        conversation_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        # Configure conversation frame grid
        conversation_frame.grid_rowconfigure(0, weight=1)
        conversation_frame.grid_columnconfigure(0, weight=1)

        # Conversation display
        self.conversation_text = tk.Text(
            conversation_frame,
            wrap="word",
            state="disabled",
            background="#1e1e1e",
            foreground="white",
            insertbackground="white",
            font=("Consolas", 11),
        )

        # Scrollbar for conversation
        conversation_scrollbar = ttk.Scrollbar(
            conversation_frame, orient="vertical", command=self.conversation_text.yview
        )
        self.conversation_text.configure(yscrollcommand=conversation_scrollbar.set)

        self.conversation_text.grid(row=0, column=0, sticky="nsew")
        conversation_scrollbar.grid(row=0, column=1, sticky="ns")

        # Status label
        self.conversation_status_label = ttk.Label(
            self.left_panel, text="Ready", foreground="green"
        )
        self.conversation_status_label.grid(row=1, column=0, sticky="w", pady=(2, 5))

    def _create_input_area(self):
        """Create the user input area."""
        # Input frame
        input_frame = ttk.LabelFrame(self.left_panel, text="Your Message", padding="5")
        input_frame.grid(row=2, column=0, sticky="ew", pady=(0, 5))

        # Configure input frame grid
        input_frame.grid_rowconfigure(0, weight=1)
        input_frame.grid_columnconfigure(0, weight=1)

        # Input text area
        self.user_input = tk.Text(
            input_frame,
            height=4,
            wrap="word",
            background="#2b2b2b",
            foreground="white",
            insertbackground="white",
            font=("Consolas", 11),
        )

        # Scrollbar for input
        input_scrollbar = ttk.Scrollbar(
            input_frame, orient="vertical", command=self.user_input.yview
        )
        self.user_input.configure(yscrollcommand=input_scrollbar.set)

        self.user_input.grid(row=0, column=0, sticky="nsew")
        input_scrollbar.grid(row=0, column=1, sticky="ns")

        # Button frame
        button_frame = ttk.Frame(self.left_panel)
        button_frame.grid(row=3, column=0, sticky="ew", pady=(0, 5))

        # Configure button frame grid
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=0)

        # Clear button
        self.clear_button = ttk.Button(
            button_frame,
            text="Clear Conversation",
            command=self.parent.clear_conversation,
        )
        self.clear_button.grid(row=0, column=0, sticky="w")

        # Send button
        self.send_button = ttk.Button(
            button_frame, text="Send", command=self.parent.send_message
        )
        self.send_button.grid(row=0, column=1, sticky="e")

    def _create_file_management(self):
        """Create the file management section."""
        # File management frame
        file_frame = ttk.LabelFrame(
            self.scrollable_frame, text="File Management", padding="5"
        )
        file_frame.pack(fill="x", pady=(0, 5))

        # Upload button
        self.upload_button = ttk.Button(
            file_frame, text="Upload File", command=self.parent.upload_file
        )
        self.upload_button.pack(fill="x", pady=(0, 5))

        # File status label
        self.parsed_file_label = ttk.Label(file_frame, text="No file loaded.")
        self.parsed_file_label.pack(fill="x", pady=(0, 5))

        # Clear files button
        self.clear_files_button = ttk.Button(
            file_frame, text="Clear Files", command=self.parent.clear_uploaded_files
        )
        self.clear_files_button.pack(fill="x")

    def _create_web_scraping(self):
        """Create the web scraping section."""
        # Web scraping frame
        web_frame = ttk.LabelFrame(
            self.scrollable_frame, text="Web Scraping", padding="5"
        )
        web_frame.pack(fill="x", pady=(0, 5))

        # URL row
        web_row = ttk.Frame(web_frame)
        web_row.pack(fill="x", pady=(0, 5))

        ttk.Label(web_row, text="URL:").pack(side="left")

        self.url_entry = ttk.Entry(web_row, width=40)
        self.url_entry.pack(side="left", padx=(5, 5), fill="x", expand=True)

        # Set up placeholder behavior for URL field
        self.url_placeholder = "Enter URL to scrape..."
        self.url_entry.insert(0, self.url_placeholder)
        self.url_entry.config(foreground="gray")

        def url_focus_in(event):
            if self.url_entry.get() == self.url_placeholder:
                self.url_entry.delete(0, tk.END)
                self.url_entry.config(foreground="white")

        def url_focus_out(event):
            if not self.url_entry.get().strip():
                self.url_entry.insert(0, self.url_placeholder)
                self.url_entry.config(foreground="gray")

        self.url_entry.bind("<FocusIn>", url_focus_in)
        self.url_entry.bind("<FocusOut>", url_focus_out)

        # Scrape button
        self.scrape_button = ttk.Button(
            web_row, text="Scrape", command=self.parent.scrape_url
        )
        self.scrape_button.pack(side="left", padx=(5, 0))

    def _create_authentication(self):
        """Create the authentication section."""
        # Authentication frame
        auth_frame = ttk.LabelFrame(
            self.scrollable_frame, text="Authenticated Scraping", padding="5"
        )
        auth_frame.pack(fill="x", pady=(0, 5))

        # Credentials row
        cred_row = ttk.Frame(auth_frame)
        cred_row.pack(fill="x", pady=(0, 5))

        # Username field
        ttk.Label(cred_row, text="Username:").pack(anchor="w")
        self.username_entry = ttk.Entry(cred_row, width=30)
        self.username_entry.pack(fill="x", pady=(0, 5))
        self.username_entry.config(foreground="white")

        # Password field
        ttk.Label(cred_row, text="Password:").pack(anchor="w")
        self.password_entry = ttk.Entry(cred_row, width=30, show="*")
        self.password_entry.pack(fill="x", pady=(0, 5))
        self.password_entry.config(foreground="white")

        # Setup placeholder behavior for credentials
        self._setup_credential_placeholders()

        # Button container with responsive layout
        self.auth_button_container = ttk.Frame(auth_frame)
        self.auth_button_container.pack(fill="x", pady=(5, 0))

        # Create authentication buttons
        self._create_auth_buttons()

        # Bind resize event for responsive layout
        self.right_panel.bind("<Configure>", self._on_sidebar_resize)

    def _setup_credential_placeholders(self):
        """Setup placeholder behavior for credential fields."""
        # Username placeholder
        username_placeholder = "Username"
        self.username_entry.insert(0, username_placeholder)
        self.username_entry.config(foreground="gray")

        def username_focus_in(event):
            if self.username_entry.get() == username_placeholder:
                self.username_entry.delete(0, tk.END)
                self.username_entry.config(foreground="white")

        def username_focus_out(event):
            if not self.username_entry.get().strip():
                self.username_entry.insert(0, username_placeholder)
                self.username_entry.config(foreground="gray")

        self.username_entry.bind("<FocusIn>", username_focus_in)
        self.username_entry.bind("<FocusOut>", username_focus_out)

        # Password placeholder
        password_placeholder = "Password"
        self.password_entry.insert(0, password_placeholder)
        self.password_entry.config(foreground="gray", show="")

        def password_focus_in(event):
            if self.password_entry.get() == password_placeholder:
                self.password_entry.delete(0, tk.END)
                self.password_entry.config(foreground="white", show="*")

        def password_focus_out(event):
            if not self.password_entry.get().strip():
                self.password_entry.insert(0, password_placeholder)
                self.password_entry.config(foreground="gray", show="")

        self.password_entry.bind("<FocusIn>", password_focus_in)
        self.password_entry.bind("<FocusOut>", password_focus_out)

    def _create_auth_buttons(self):
        """Create authentication buttons with responsive layout."""
        # Clear existing buttons
        for widget in self.auth_button_container.winfo_children():
            widget.destroy()

        # Configure grid columns
        self.auth_button_container.grid_columnconfigure(0, weight=1, minsize=120)
        self.auth_button_container.grid_columnconfigure(1, weight=1, minsize=120)

        # Row 1: Login & Scrape and Analyze Login buttons
        self.login_scrape_button = ttk.Button(
            self.auth_button_container,
            text="Login & Scrape",
            command=self.parent.scrape_with_login,
            state="disabled",
        )
        self.login_scrape_button.grid(
            row=0, column=0, sticky="ew", padx=(0, 3), pady=(0, 3)
        )

        self.analyze_button = ttk.Button(
            self.auth_button_container,
            text="Analyze Login",
            command=self.parent.analyze_login_form,
        )
        self.analyze_button.grid(row=0, column=1, sticky="ew", padx=(3, 0), pady=(0, 3))

        # Row 2: Navigate Site and Reset buttons
        self.navigate_button = ttk.Button(
            self.auth_button_container,
            text="Navigate Site",
            command=self.parent.navigate_authenticated_site,
            state="disabled",
        )
        self.navigate_button.grid(
            row=1, column=0, sticky="ew", padx=(0, 3), pady=(3, 0)
        )

        self.reset_button = ttk.Button(
            self.auth_button_container,
            text="Reset",
            command=self.parent.reset_authentication_state,
        )
        self.reset_button.grid(row=1, column=1, sticky="ew", padx=(3, 0), pady=(3, 0))

    def _on_sidebar_resize(self, event):
        """Handle sidebar resize to adjust button layout responsively."""
        if event.widget != self.right_panel:
            return

        sidebar_width = event.width

        # Adaptive layout based on sidebar width
        if sidebar_width < 300:
            # Narrow sidebar - stack buttons vertically
            self._create_vertical_button_layout()
        elif sidebar_width < 450:
            # Medium sidebar - compact 2x2 grid
            self._create_compact_button_layout()
        else:
            # Wide sidebar - standard 2x2 grid with more spacing
            self._create_standard_button_layout()

    def _create_vertical_button_layout(self):
        """Create vertical button layout for narrow sidebar."""
        # Clear existing buttons
        for widget in self.auth_button_container.winfo_children():
            widget.destroy()

        # Single column layout
        self.auth_button_container.grid_columnconfigure(0, weight=1)

        buttons = [
            ("Analyze Login", self.parent.analyze_login_form, "normal"),
            ("Login & Scrape", self.parent.scrape_with_login, "disabled"),
            ("Navigate Site", self.parent.navigate_authenticated_site, "disabled"),
            ("Reset", self.parent.reset_authentication_state, "normal"),
        ]

        for i, (text, command, state) in enumerate(buttons):
            btn = ttk.Button(
                self.auth_button_container, text=text, command=command, state=state
            )
            btn.grid(row=i, column=0, sticky="ew", pady=2)

            # Store button references
            if text == "Login & Scrape":
                self.login_scrape_button = btn
            elif text == "Analyze Login":
                self.analyze_button = btn
            elif text == "Navigate Site":
                self.navigate_button = btn
            elif text == "Reset":
                self.reset_button = btn

    def _create_compact_button_layout(self):
        """Create compact 2x2 button layout for medium sidebar."""
        self._create_auth_buttons()  # Use standard layout but with tighter spacing

    def _create_standard_button_layout(self):
        """Create standard 2x2 button layout for wide sidebar."""
        self._create_auth_buttons()

    def set_conversation_status(self, status):
        """Set the conversation status text."""
        self.conversation_status_label.config(text=status)


class ToolTip:
    """Simple tooltip for Tk widgets."""

    def __init__(self, widget, text: str = "", delay_ms: int = 350):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.tooltip_window = None
        self.after_id = None

        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.on_leave)

    def on_enter(self, event=None):
        """Handle mouse enter event."""
        if self.text:
            self.after_id = self.widget.after(self.delay_ms, self.show_tooltip)

    def on_leave(self, event=None):
        """Handle mouse leave event."""
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        self.hide_tooltip()

    def show_tooltip(self):
        """Show the tooltip."""
        if self.tooltip_window or not self.text:
            return

        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 25

        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("tahoma", "8", "normal"),
        )
        label.pack(ipadx=1)

    def hide_tooltip(self):
        """Hide the tooltip."""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

    def update_text(self, new_text: str):
        """Update tooltip text."""
        self.text = new_text
