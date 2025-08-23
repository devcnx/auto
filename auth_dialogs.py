"""
Authentication dialog components for the Dynamic Ollama Assistant GUI.

This module contains dialog classes for authentication workflows.
"""

import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser


class ManualSelectorDialog:
    """Dialog for manual CSS selector entry when sites block automated analysis."""

    def __init__(self, parent, error_info, url):
        self.parent = parent
        self.error_info = error_info
        self.url = url
        self.dialog = None
        self.entries = {}

    def show(self):
        """Show the manual selector dialog."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Manual Selector Entry - Site Blocks Analysis")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # Center the dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (700 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (500 // 2)
        self.dialog.geometry(f"700x500+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self):
        """Create dialog widgets."""
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill="both", expand=True)

        # Error explanation
        ttk.Label(
            main_frame,
            text="⚠️ Site Blocks Automated Analysis",
            font=("Arial", 14, "bold"),
            foreground="#ff6b35",
        ).pack(pady=(0, 10))

        # Error details
        self._create_error_section(main_frame)
        
        # Manual entry section
        self._create_manual_entry_section(main_frame)
        
        # Help section
        self._create_help_section(main_frame)
        
        # Buttons
        self._create_buttons(main_frame)

    def _create_error_section(self, parent):
        """Create error details section."""
        error_frame = ttk.LabelFrame(parent, text="Error Details", padding="10")
        error_frame.pack(fill="x", pady=(0, 15))

        error_text = tk.Text(
            error_frame, height=3, wrap="word", background="#2b2b2b", foreground="white"
        )
        error_text.pack(fill="x")
        error_text.insert(
            "1.0", f"{self.error_info['error']}\n\n{self.error_info.get('suggestion', '')}"
        )
        error_text.config(state="disabled")

    def _create_manual_entry_section(self, parent):
        """Create manual selector entry section."""
        manual_frame = ttk.LabelFrame(
            parent, text="Manual CSS Selector Entry", padding="10"
        )
        manual_frame.pack(fill="both", expand=True, pady=(0, 15))

        # Instructions
        ttk.Label(
            manual_frame,
            text="Enter CSS selectors manually by inspecting the login page:",
            font=("Arial", 10, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        # Selector entries
        common_selectors = self.error_info.get("common_selectors", {})

        for field, placeholder in [
            ("username", "Username/Email field selector"),
            ("password", "Password field selector"),
            ("submit", "Submit button selector"),
        ]:
            field_frame = ttk.Frame(manual_frame)
            field_frame.pack(fill="x", pady=5)

            ttk.Label(field_frame, text=f"{field.title()}:", width=12).pack(side="left")
            entry = ttk.Entry(field_frame, width=50)
            entry.pack(side="left", fill="x", expand=True, padx=(5, 0))

            # Pre-fill with common selector suggestions
            if field in common_selectors:
                entry.insert(0, common_selectors[field].split(",")[0].strip())

            self.entries[field] = entry

    def _create_help_section(self, parent):
        """Create help section."""
        help_frame = ttk.LabelFrame(
            parent, text="How to Find Selectors", padding="10"
        )
        help_frame.pack(fill="x", pady=(10, 0))

        help_text = tk.Text(
            help_frame, height=6, wrap="word", background="#2b2b2b", foreground="white"
        )
        help_text.pack(fill="x")
        help_text.insert(
            "1.0",
            """1. Open the login page in your browser
2. Right-click on the username field → "Inspect Element"
3. Copy the CSS selector (right-click element → Copy → Copy selector)
4. Repeat for password field and submit button
5. Common patterns: input[name="email"], #password, button[type="submit"]""",
        )
        help_text.config(state="disabled")

    def _create_buttons(self, parent):
        """Create dialog buttons."""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill="x", pady=(10, 0))

        def use_manual_selectors():
            selectors = {}
            for field, entry in self.entries.items():
                value = entry.get().strip()
                if value:
                    selectors[field] = value

            if len(selectors) >= 2:  # At least username and password
                self.parent.ui.login_analyzed = True
                self.parent.ui.login_selectors = selectors
                self.parent._update_auth_button_states()
                self.dialog.destroy()
                messagebox.showinfo(
                    "Success", "Manual selectors saved! You can now use Login & Scrape."
                )
            else:
                messagebox.showerror(
                    "Error", "Please enter at least username and password selectors."
                )

        def open_browser():
            webbrowser.open(self.url)

        ttk.Button(button_frame, text="Open Login Page", command=open_browser).pack(
            side="left"
        )
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(
            side="right"
        )
        ttk.Button(
            button_frame, text="Use These Selectors", command=use_manual_selectors
        ).pack(side="right", padx=(0, 10))


class VerificationRequiredDialog:
    """Dialog for when CAPTCHA or human verification is detected."""

    def __init__(self, parent, verification_info, url):
        self.parent = parent
        self.verification_info = verification_info
        self.url = url
        self.dialog = None

    def show(self):
        """Show the verification required dialog."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Human Verification Required")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # Center the dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (400 // 2)
        self.dialog.geometry(f"600x400+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self):
        """Create dialog widgets."""
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill="both", expand=True)

        # Warning header
        ttk.Label(
            main_frame,
            text="🤖 Human Verification Detected",
            font=("Arial", 14, "bold"),
            foreground="#ff6b35",
        ).pack(pady=(0, 10))

        # Verification details
        self._create_details_section(main_frame)
        
        # Instructions
        self._create_instructions_section(main_frame)
        
        # Buttons
        self._create_buttons(main_frame)

    def _create_details_section(self, parent):
        """Create verification details section."""
        details_frame = ttk.LabelFrame(
            parent, text="Verification Details", padding="10"
        )
        details_frame.pack(fill="x", pady=(0, 15))

        details_text = tk.Text(
            details_frame,
            height=4,
            wrap="word",
            background="#2b2b2b",
            foreground="white",
        )
        details_text.pack(fill="x")

        details_content = f"Site: {self.verification_info.get('current_url', self.url)}\n"
        details_content += (
            f"Page Title: {self.verification_info.get('page_title', 'Unknown')}\n\n"
        )

        if self.verification_info.get("content_matches"):
            details_content += (
                f"Detected: {', '.join(self.verification_info['content_matches'][:3])}"
            )

        details_text.insert("1.0", details_content)
        details_text.config(state="disabled")

    def _create_instructions_section(self, parent):
        """Create instructions section."""
        instructions_frame = ttk.LabelFrame(
            parent, text="What This Means", padding="10"
        )
        instructions_frame.pack(fill="both", expand=True, pady=(0, 15))

        instructions_text = tk.Text(
            instructions_frame,
            height=8,
            wrap="word",
            background="#2b2b2b",
            foreground="white",
        )
        instructions_text.pack(fill="x")
        instructions_text.insert(
            "1.0",
            """This site requires human verification (CAPTCHA, "I'm not a robot", etc.) which cannot be automated.

Options to proceed:
1. Manual Login: Complete the verification manually in your browser, then try scraping
2. Session Import: If you have valid cookies/session data, import them
3. Alternative Approach: Some sites offer API access or different login methods

Common verification types detected:
• reCAPTCHA ("I'm not a robot" checkbox)
• hCaptcha (image/text challenges)  
• Cloudflare bot protection
• Custom verification challenges""",
        )
        instructions_text.config(state="disabled")

    def _create_buttons(self, parent):
        """Create dialog buttons."""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill="x", pady=(10, 0))

        def open_site():
            webbrowser.open(self.url)

        def try_anyway():
            """Allow user to attempt login despite verification detection."""
            self.dialog.destroy()
            # Continue with normal login flow
            messagebox.showinfo(
                "Proceeding",
                "Attempting login despite verification detection. Manual intervention may be required.",
            )

        ttk.Button(button_frame, text="Open Site Manually", command=open_site).pack(
            side="left"
        )
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(
            side="right"
        )
        ttk.Button(button_frame, text="Try Login Anyway", command=try_anyway).pack(
            side="right", padx=(0, 10)
        )


class LoginAnalysisDialog:
    """Dialog for showing login form analysis results."""

    def __init__(self, parent, selectors, url):
        self.parent = parent
        self.selectors = selectors
        self.url = url
        self.dialog = None

    def show(self):
        """Show the login analysis dialog."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Login Form Analysis")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # Center the dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (400 // 2)
        self.dialog.geometry(f"600x400+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self):
        """Create dialog widgets."""
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(
            main_frame,
            text=f"Login Form Analysis Results for {self.url}",
            font=("Arial", 12, "bold"),
        ).pack(pady=(0, 10))

        # Results display
        results_frame = ttk.LabelFrame(main_frame, text="Detected Selectors", padding="10")
        results_frame.pack(fill="both", expand=True, pady=(0, 10))

        results_text = tk.Text(
            results_frame, wrap="word", background="#2b2b2b", foreground="white"
        )
        results_text.pack(fill="both", expand=True)

        # Display selectors
        content = "AI Analysis Results:\n\n"
        for field, selector in self.selectors.items():
            content += f"{field.title()}: {selector}\n"

        results_text.insert("1.0", content)
        results_text.config(state="disabled")

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))

        def use_selectors():
            self.parent.ui.login_analyzed = True
            self.parent.ui.login_selectors = self.selectors
            self.parent._update_auth_button_states()
            self.dialog.destroy()

        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(
            side="right"
        )
        ttk.Button(button_frame, text="Use Selectors", command=use_selectors).pack(
            side="right", padx=(0, 10)
        )


class NavigationDialog:
    """Dialog for navigating authenticated sites."""

    def __init__(self, parent):
        self.parent = parent
        self.dialog = None

    def show(self):
        """Show the navigation dialog."""
        if (
            not hasattr(self.parent.ui, "authenticated_session")
            or not self.parent.ui.authenticated_session
        ):
            messagebox.showerror("Error", "Please login first using 'Login & Scrape'.")
            return

        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Navigate Authenticated Site")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # Center the dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (400 // 2)
        self.dialog.geometry(f"500x400+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self):
        """Create dialog widgets."""
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(
            main_frame,
            text="Navigate Authenticated Site",
            font=("Arial", 14, "bold"),
        ).pack(pady=(0, 10))

        # Instructions
        instructions = ttk.Label(
            main_frame,
            text="Enter URLs to navigate and scrape (one per line):",
            font=("TkDefaultFont", 10, "bold"),
        )
        instructions.pack(anchor="w", pady=(0, 5))

        # URL input area
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill="both", expand=True, pady=(0, 10))

        url_text = tk.Text(url_frame, height=8, wrap="word")
        url_scrollbar = ttk.Scrollbar(
            url_frame, orient="vertical", command=url_text.yview
        )
        url_text.configure(yscrollcommand=url_scrollbar.set)

        url_text.pack(side="left", fill="both", expand=True)
        url_scrollbar.pack(side="right", fill="y")

        # Example URLs
        example_frame = ttk.LabelFrame(main_frame, text="Example", padding="5")
        example_frame.pack(fill="x", pady=(0, 10))

        example_text = tk.Text(example_frame, height=3, wrap="word")
        example_text.pack(fill="x")
        example_text.insert(
            "1.0",
            "https://example.com/dashboard\nhttps://example.com/profile\nhttps://example.com/settings",
        )
        example_text.config(state="disabled")

        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="5")
        options_frame.pack(fill="x", pady=(0, 10))

        wait_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame, text="Wait between page loads (2 seconds)", variable=wait_var
        ).pack(anchor="w", padx=5, pady=5)

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")

        def start_navigation():
            urls_text = url_text.get("1.0", tk.END).strip()
            if not urls_text:
                messagebox.showerror("Error", "Please enter at least one URL.")
                return

            urls = [url.strip() for url in urls_text.split("\n") if url.strip()]
            if not urls:
                messagebox.showerror("Error", "Please enter valid URLs.")
                return

            self.dialog.destroy()
            self.parent._navigate_and_scrape_urls(urls, wait_var.get())

        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(
            side="right", padx=(5, 0)
        )
        ttk.Button(
            button_frame, text="Start Navigation", command=start_navigation
        ).pack(side="right")
