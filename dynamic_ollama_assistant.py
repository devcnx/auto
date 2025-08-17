"""
Dynamic, interactive Ollama assistant loader (CSV-based, IDE-friendly).

This module is used to load a folder of CSV files (one per original sheet), e.g.:

    Mega-Prompts for Business.csv
    Mega-Prompts for Marketing.csv
    Mega-Prompts for Productivity.csv
    Mega-Prompts for Sales.csv
    Mega-Prompts for Writing.csv

Each CSV is treated like a "sheet"; we derive a Sheet name from the filename.
No CLI args; prompts you to pick Category → Sub-Category → Page, then fill placeholders, 
then chat via Ollama.

Prereqs: 
  pip install pandas requests
  ollama serve
  ollama pull llama3.1   # or your preferred model
  
Imports:
    - glob: Used to find all CSV files in the specified directory and pattern.
    - dataclasses: Used to create a dataclass for the PromptData.
    - datetime: Used to get the current date and time.
    - typing: Used to type hint the functions and variables.    
    
"""

import glob
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd
import requests

# --------- SETTINGS (edit these defaults if you want) ---------
CSV_DIR = os.environ.get(
    "MEGAPROMPTS_CSV_DIR", "/Users/brittaneyperry-morgan/Desktop/auto/data"
)
CSV_GLOB = os.environ.get("MEGAPROMPTS_CSV_GLOB", "Mega-Prompts for *.csv")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
OLLAMA_CHAT_URL = os.environ.get("OLLAMA_CHAT_URL", "http://localhost:11434/api/chat")
# --------------------------------------------------------------


@dataclass
class PromptData:
    """A container for all the data related to a single prompt."""

    mega_prompt: str
    prompt_name: str
    description: str
    what_this_does: str
    tips: str
    how_to_use: str
    additional_tips: str

    @classmethod
    def from_series(cls, row: pd.Series) -> "PromptData":
        """Create a PromptData instance from a pandas Series."""
        return cls(
            mega_prompt=row.get("Mega-Prompt", ""),
            prompt_name=row.get("Prompt Name", ""),
            description=row.get("Description ", "") or row.get("Description", ""),
            what_this_does=row.get("What This Mega-Prompt Does", ""),
            tips=row.get("Tips", ""),
            how_to_use=row.get("How to Use ", "") or row.get("How to Use", ""),
            additional_tips=row.get("Additional Tips", ""),
        )


PLACEHOLDER_PATTERNS = [
    r"\[\[([^\]]+)\]\]",  # [[placeholder]]
    r"<([^>]+)>",  # <placeholder>
]

EXPECTED_COLUMNS = [
    "Category",
    "Sub-Category",
    "Short Description (PAGE NAME)",
    "Description ",
    "What This Mega-Prompt Does",
    "Tips",
    "Prompt Name",
    "Mega-Prompt",
    "How to Use ",
    "Additional Tips",
    "Example Input",
]


def find_placeholders(text: str) -> List[str]:
    """
    Locate all placeholders within the text of the `Mega-Prompt` column.

    Parameters:
        - text: The text to search for placeholders.
        :type text: str

    Returns:
        - A list of all located placeholders.
        :rtype: List[str]
    """
    if not isinstance(text, str):
        return []
    found = []
    for pat in PLACEHOLDER_PATTERNS:
        for m in re.findall(pat, text):
            key = m.strip()
            if key and key not in found:
                found.append(key)
    return found


def replace_placeholders(text: str, values: Dict[str, str]) -> str:
    """
    Replace placeholders in the text with their corresponding values.

    Parameters:
        - text: The text to replace placeholders in.
        :type text: str
        - values: A dictionary of placeholder values.
        :type values: Dict[str, str]

    Returns:
        - The text with placeholders replaced.
        :rtype: str
    """
    if not isinstance(text, str):
        return text

    def repl_square(match: re.Match) -> str:
        """
        Replace a square-bracket placeholder.

        This function is used as a callback for the `re.sub` function. It
        is called for each match of the square-bracket placeholder pattern.

        Parameters:
            - match: The match object containing the placeholder.
            :type match: re.Match

        Returns:
            - The placeholder replaced with its corresponding value.
            :rtype: str
        """
        key = match[1].strip()
        return values.get(key, match[0])

    def repl_angle(match: re.Match) -> str:
        """
        Replace an angle-bracket placeholder.

        This function is used as a callback for the `re.sub` function. It
        is called for each match of the angle-bracket placeholder pattern.

        Parameters:
            - match: The match object containing the placeholder.
            :type match: re.Match

        Returns:
            - The placeholder replaced with its corresponding value.
            :rtype: str
        """
        key = match[1].strip()
        return values.get(key, match[0])

    text = re.sub(r"\[\[([^\]]+)\]\]", repl_square, text)
    text = re.sub(r"<([^>]+)>", repl_angle, text)
    return text


def load_csvs(csv_dir: str, pattern: str) -> Dict[str, pd.DataFrame]:
    """
    Load all CSVs and return {sheet_name: DataFrame} where sheet_name is derived from filename.

    Using glob to find all CSV files in the specified directory and pattern. `glob` is
    used instead of `os.listdir` to handle file paths with special characters.

    Parameters:
        - csv_dir: The directory where the csv files are located.
        :type csv_dir: str

        - pattern: The pattern to match against the csv files.
        :type pattern: str

    Returns:
        - A dictionary of DataFrames where the keys are the sheet names and the values are
        the DataFrames.
        :rtype: Dict[str, pd.DataFrame]
    """
    out = {}
    # Prefer predictable order
    paths = sorted(glob.glob(os.path.join(csv_dir, pattern)))
    for p in paths:
        try:
            df = pd.read_csv(p, on_bad_lines="warn")
        except UnicodeDecodeError:
            # Fallback for different encoding
            df = pd.read_csv(p, encoding="utf-8-sig", on_bad_lines="warn")
        except Exception as e:
            print(f"\n--- ERROR LOADING CSV: {os.path.basename(p)} ---")
            print(f"Error: {e}")
            print("---------------------------------------\n")
            continue

        # Derive "sheet" from filename
        base = os.path.basename(p)
        name = base.replace("Mega-Prompts for ", "").replace(".csv", "").strip()
        out[name] = df
    return out


# --- Menu Refactor ---


def _deduplicate_options(options: List[str]) -> List[str]:
    """Deduplicate and filter out invalid menu options."""
    seen = set()
    unique = []
    for item in options:
        key = str(item).strip()
        if key and key not in seen and key != "_" and key.lower() != "nan":
            seen.add(key)
            unique.append(key)
    return unique


def _display_page(options: List[str], page: int, page_size: int):
    """Display one page of menu options."""
    start_idx = page * page_size
    end_idx = start_idx + page_size
    current_page_options = options[start_idx:end_idx]
    for i, opt in enumerate(current_page_options, start=start_idx + 1):
        print(f"  {i}. {opt}")


def _build_prompt(
    total_options: int, page: int, num_pages: int, can_go_back: bool
) -> str:
    """Build the dynamic user input prompt for the menu."""
    prompt_msg = f"\nChoose 1 - {total_options}"
    nav_parts = []
    if num_pages > 1:
        nav_parts.extend([f"Page {page + 1}/{num_pages}", "N or P for Next / Prev"])
    if can_go_back:
        nav_parts.append("'B' for Back")
    nav_parts.extend(["'E' to Exit", "or Type to Search"])
    return f"{prompt_msg} ({', '.join(nav_parts)}): "


def _handle_search(search_term: str, options: List[str]) -> str | None:
    """Handle user search, returning a selection, or None if no choice was made."""
    matches = [opt for opt in options if search_term in opt.lower()]
    if len(matches) == 1:
        print(f"→ '{matches[0]}'")
        return matches[0]
    if len(matches) > 1:
        print(
            f"Found {len(matches)} Matches. Please Be More Specific or Choose from the List."
        )
        for i, m in enumerate(matches, 1):
            print(f"  {i}. {m}")
        temp_choice = input("\nChoose a Number from the Search Results: ").strip()
        if temp_choice.isdigit() and 1 <= int(temp_choice) <= len(matches):
            return matches[int(temp_choice) - 1]
    else:
        print("No Match Found. Please Try Again.")
    return None


def _process_menu_choice(
    choice: str,
    page: int,
    num_pages: int,
    unique_options: List[str],
    can_go_back: bool,
) -> Tuple[str, any]:
    """Process the user's menu choice and return an action and a value."""
    if choice in {"e", "exit", "q", "quit"}:
        return "exit", None
    if choice == "b" and can_go_back:
        return "back", None

    if choice in {"n", "p"}:
        if choice == "n" and page < num_pages - 1:
            page += 1
        elif choice == "p" and page > 0:
            page -= 1
        else:
            print("Already on the First/Last Page.")
        return "continue", page

    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(unique_options):
            return "select", unique_options[idx - 1]
        print(f"Invalid number. Please choose between 1 and {len(unique_options)}.")
        return "continue", page

    if choice:
        if search_result := _handle_search(choice, unique_options):
            return "select", search_result
    else:
        print("Invalid choice. Please try again.")

    return "continue", page


def pick_from_menu(
    title: str,
    options: List[str],
    page_size: int = 15,
    can_go_back: bool = False,
) -> str:
    """Display a paginated, searchable menu and return the user's choice."""
    print(f"\n{title}")
    if not options:
        return ""

    unique_options = _deduplicate_options(options)
    if not unique_options:
        return ""

    page = 0
    num_pages = (len(unique_options) + page_size - 1) // page_size

    while True:
        _display_page(unique_options, page, page_size)
        prompt = _build_prompt(len(unique_options), page, num_pages, can_go_back)
        choice = input(prompt).strip().lower()

        action, value = _process_menu_choice(
            choice, page, num_pages, unique_options, can_go_back
        )

        if action == "exit":
            return "__EXIT__"
        if action == "back":
            return "__BACK__"
        if action == "select":
            return value
        if action == "continue":
            page = value
            continue


def build_system_prompt(
    row: pd.Series, fill_values: Dict[str, str]
) -> Tuple[str, Dict[str, str]]:
    """Build the System Prompt."""
    prompt_data = PromptData.from_series(row)

    placeholder_fields = [
        prompt_data.mega_prompt,
        prompt_data.description,
        prompt_data.what_this_does,
        prompt_data.tips,
        prompt_data.how_to_use,
        prompt_data.additional_tips,
    ]
    needed = sorted(
        {
            placeholder
            for field in placeholder_fields
            for placeholder in find_placeholders(field)
        }
    )

    unresolved = {k: None for k in needed if k not in fill_values}

    def maybe(s: str) -> str:
        """Return a string if it is not "_'."""
        s = s.strip()
        return s if s != "_" else ""

    prompt_parts = [
        "# " + prompt_data.prompt_name if maybe(prompt_data.prompt_name) else "",
        (
            "## Tips\n" + replace_placeholders(prompt_data.tips, fill_values)
            if maybe(prompt_data.tips)
            else ""
        ),
        (
            "## How to Use\n"
            + replace_placeholders(prompt_data.how_to_use, fill_values)
            if maybe(prompt_data.how_to_use)
            else ""
        ),
        (
            "## Additional Tips\n"
            + replace_placeholders(prompt_data.additional_tips, fill_values)
            if maybe(prompt_data.additional_tips)
            else ""
        ),
    ]

    header_text = "\n".join(part for part in prompt_parts if part)
    core = replace_placeholders(prompt_data.mega_prompt, fill_values).strip()

    system_prompt = f"{header_text}\n---\n\n{core}" if header_text else core

    return system_prompt, unresolved


def query_ollama_chat_for_gui(model: str, system_prompt: str, user_msg: str):
    """Query Ollama and yield response chunks for the GUI."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": True,
    }
    try:
        with requests.post(OLLAMA_CHAT_URL, json=payload, stream=True, timeout=30) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "message" in obj and "content" in obj["message"]:
                        yield obj["message"]["content"]
                except json.JSONDecodeError:
                    yield line
    except requests.exceptions.RequestException as e:
        yield f"\n❌ API Error: {e}"


def query_ollama_chat(
    model: str,
    system_prompt: str,
    user_msg: str,
    stream: bool = True,
    output_file: str = None,
):
    """Query the Ollama chat API and optionally write the conversation to a file."""
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n> {user_msg}\n\n")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": stream,
    }
    with requests.post(OLLAMA_CHAT_URL, json=payload, stream=stream, timeout=30) as r:
        r.raise_for_status()
        if stream:
            full_response = []
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "message" in obj and "content" in obj["message"]:
                        content = obj["message"]["content"]
                        print(content, end="", flush=True)
                        full_response.append(content)
                except json.JSONDecodeError:
                    print(line, end="")
                    full_response.append(line)
            print()  # Newline after streaming is done
            if output_file:
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write("".join(full_response))
        else:
            data = r.json()
            content = data.get("message", {}).get("content", "")
            print(content)
            if output_file:
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(content)


def _navigate_menus(
    data_by_sheet: Dict[str, pd.DataFrame]
) -> Tuple[pd.Series, str, str] | None:
    """Handle the nested menu navigation logic."""
    sheet_names = list(data_by_sheet.keys())
    picked_sheet = pick_from_menu("Pick a Category:", sheet_names)
    if picked_sheet in ("__EXIT__", ""):
        return None

    while True:
        df = data_by_sheet[picked_sheet]
        sub_categories = list(df["Sub-Category"].unique())
        picked_sub = pick_from_menu(
            f"Pick a Sub-Category in '{picked_sheet}':",
            sub_categories,
            can_go_back=True,
        )

        if picked_sub == "__BACK__":
            return _navigate_menus(data_by_sheet)  # Restart navigation
        if picked_sub in ("__EXIT__", ""):
            return None

        while True:
            df_sub = df[df["Sub-Category"] == picked_sub]
            pages = list(df_sub["Short Description (PAGE NAME)"].unique())
            picked_page = pick_from_menu(
                f"Pick a Page in '{picked_sub}':", pages, can_go_back=True
            )

            if picked_page == "__BACK__":
                break  # Go back to sub-category selection
            if picked_page in ("__EXIT__", ""):
                return None

            row = df.loc[
                (df["Sub-Category"] == picked_sub)
                & (df["Short Description (PAGE NAME)"] == picked_page)
            ].iloc[0]
            return row, picked_sheet, picked_sub


def _process_prompt(
    row: pd.Series, picked_sheet: str, picked_sub: str, picked_page: str
):
    """Handle placeholder filling and the main chat loop for the selected prompt."""
    print(f"\n✅ Loaded Prompt: \n{row.get('Short Description (PAGE NAME)')}")
    print(f"   From: {picked_sheet} > {picked_sub}")

    fill_values: Dict[str, str] = {}
    system_prompt, unresolved = build_system_prompt(row, fill_values)

    if unresolved:
        print(
            "\nThis Prompt Needs a Few Details. Press Enter to Leave Any Value Blank"
            "(will keep placeholder)."
        )
        for k in sorted(unresolved.keys()):
            if val := input(f"  • {k}: ").strip():
                fill_values[k] = val
        system_prompt, _ = build_system_prompt(row, fill_values)

    print("\n— System Prompt Preview (First 800 Chars) —")
    print(system_prompt[:800] + ("..." if len(system_prompt) > 800 else ""))

    model = input(f"\nModel to Use [{DEFAULT_MODEL}]: ").strip() or DEFAULT_MODEL

    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_page_name = re.sub(r"[^\w_.)( -]", "", picked_page).strip()
    output_file = os.path.join(output_dir, f"{timestamp}_{safe_page_name}.md")

    print(f"\n📝 Saving conversation to: {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"--- SYSTEM PROMPT ---\n{system_prompt}")

    print("\nLaunching chat with Ollama.")
    try:
        while True:
            user_msg = input("\n> ").strip()
            if not user_msg:
                continue

            query_ollama_chat(model, system_prompt, user_msg, output_file=output_file)

            action_prompt = (
                "\nNext Action:\n  [C]ontinue Chat\n"
                + "  [S]tart Over (New Prompt)\n"
                + "  [E]xit\n> "
            )
            while True:
                next_action = input(action_prompt).strip().lower()
                if next_action in ["c", "s", "e"]:
                    break
                print("Invalid Choice. Please enter 'c', 's', or 'e'.")

            if next_action == "s":
                print("\n✨ Starting Over...")
                return  # Return to main loop to start over
            if next_action == "e":
                print("\nBye!")
                sys.exit(0)  # Exit program

    except (KeyboardInterrupt, EOFError):
        print("\nBye!")
        sys.exit(0)
    except requests.exceptions.RequestException as e:
        print(f"\n❌ API Error: {e}")
        print("Is the Ollama server running? Try: ollama serve")
        sys.exit(1)


def main():
    """Orchestrate the dynamic Ollama assistant."""
    print(f"\n{'-' * 10} Dynamic Ollama Assistant (Interactive, CSV) {'-' * 10}\n")
    print(f"CSV Folder: {CSV_DIR}")
    print(f"Default Model: {DEFAULT_MODEL}")

    data_by_sheet = load_csvs(CSV_DIR, CSV_GLOB)
    if not data_by_sheet:
        print(f"❌ No CSVs Found with Pattern '{CSV_GLOB}' in '{CSV_DIR}'.")
        sys.exit(1)

    while True:
        selection = _navigate_menus(data_by_sheet)
        if not selection:
            print("\nBye!")
            break

        row, picked_sheet, picked_sub = selection
        picked_page = row.get("Short Description (PAGE NAME)")
        _process_prompt(row, picked_sheet, picked_sub, picked_page)


if __name__ == "__main__":
    main()
