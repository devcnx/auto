#!/usr/bin/env python3
"""
Dynamic, interactive Ollama assistant loader (CSV-based, IDE-friendly).

WHAT'S NEW
- Uses a folder of CSV files (one per original sheet), e.g.:
    Mega-Prompts for Business.csv
    Mega-Prompts for Marketing.csv
    Mega-Prompts for Productivity.csv
    Mega-Prompts for Sales.csv
    Mega-Prompts for Writing.csv
- Each CSV is treated like a "sheet"; we derive a Sheet name from the filename.
- No CLI args; prompts you to pick Category → Sub-Category → Page, then fill placeholders, 
then chat via Ollama.

Prereqs: 
  pip install pandas requests
  ollama serve
  ollama pull llama3.1   # or your preferred model
"""

import glob
import json
import os
import re
import sys
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
    if not isinstance(text, str):
        return text

    def repl_square(match):
        key = match.group(1).strip()
        return values.get(key, match.group(0))

    def repl_angle(match):
        key = match.group(1).strip()
        return values.get(key, match.group(0))

    text = re.sub(r"\[\[([^\]]+)\]\]", repl_square, text)
    text = re.sub(r"<([^>]+)>", repl_angle, text)
    return text


def load_csvs(csv_dir: str, pattern: str) -> Dict[str, pd.DataFrame]:
    """Load all CSVs and return {sheet_name: DataFrame} where sheet_name is derived from filename."""
    out = {}
    # Prefer predictable order
    paths = sorted(glob.glob(os.path.join(csv_dir, pattern)))
    for p in paths:
        try:
            df = pd.read_csv(p)
        except UnicodeDecodeError:
            # Try Excel-compatible encoding fallback
            df = pd.read_csv(p, encoding="utf-8-sig")

        # Derive "sheet" from filename, e.g. 'Mega-Prompts for Marketing.csv' -> 'Marketing'
        base = os.path.basename(p)
        name = base.replace("Mega-Prompts for ", "").replace(".csv", "").strip()
        out[name] = df
    return out


def pick_from_menu(
    title: str, options: List[str], page_size: int = 15, can_go_back: bool = False
) -> str:
    """Display a paginated, searchable menu and return the user's choice."""
    print(f"\n{title}")
    if not options:
        return ""

    # Deduplicate and filter out invalid options
    seen = set()
    unique = []
    for item in options:
        key = str(item).strip()
        if key and key not in seen and key != "_" and key.lower() != "nan":
            seen.add(key)
            unique.append(key)

    if not unique:
        return ""

    page = 0
    while True:
        # Display current page
        start_idx = page * page_size
        end_idx = start_idx + page_size
        current_page_options = unique[start_idx:end_idx]

        for i, opt in enumerate(current_page_options, start=start_idx + 1):
            print(f"  {i}. {opt}")

        # Navigation and input prompt
        prompt_msg = f"Choose 1-{len(unique)}"
        nav_parts = []
        if len(unique) > page_size:
            nav_parts.extend([f"Page {page + 1}/{len(unique) // page_size + 1}", "N/P for next/prev"])

        if can_go_back:
            nav_parts.append("'B' for back")

        nav_parts.extend(["'E' to exit", "or type to search"])
        prompt = f"{prompt_msg} ({', '.join(nav_parts)}): "

        choice = input(prompt).strip().lower()

        if choice in ("e", "exit", "q", "quit"):
            return "__EXIT__"

        if choice == "n":
            if end_idx < len(unique):
                page += 1
            else:
                print("Already on the last page.")
            continue
        elif choice == "p":
            if page > 0:
                page -= 1
            else:
                print("Already on the first page.")
            continue
        elif choice == "b" and can_go_back:
            return "__BACK__"

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(unique):
                return unique[idx - 1]

        # Search logic
        matches = [u for u in unique if choice in u.lower()]
        if len(matches) == 1:
            print(f"→ '{matches[0]}'")
            return matches[0]
        elif len(matches) > 1:
            print(
                f"Found {len(matches)} matches. Please be more specific or choose from the list."
            )
            # Temporarily display search results in a paginated way
            for i, m in enumerate(matches, 1):
                print(f"  {i}. {m}")
            temp_choice = input("Choose a number from the search results: ").strip()
            if temp_choice.isdigit() and 1 <= int(temp_choice) <= len(matches):
                return matches[int(temp_choice) - 1]
        else:
            print("No match found. Please try again.")


def build_system_prompt(
    row: pd.Series, fill_values: Dict[str, str]
) -> Tuple[str, Dict[str, str]]:
    """Build the system prompt with clear formatting."""
    mega = row.get("Mega-Prompt", "")
    prompt_name = row.get("Prompt Name", "")
    desc = row.get("Description ", "") or row.get("Description", "")
    what = row.get("What This Mega-Prompt Does", "")
    tips = row.get("Tips", "")
    how = row.get("How to Use ", "") or row.get("How to Use", "")
    addl = row.get("Additional Tips", "")

    placeholder_fields = [mega, desc, what, tips, how, addl]
    needed = []
    for t in placeholder_fields:
        needed.extend(find_placeholders(t))
    needed = sorted(set(needed))

    unresolved = {k: None for k in needed if k not in fill_values}

    def maybe(s):
        s = str(s).strip()
        return s if s != "_" else ""

    prompt_parts = []
    if maybe(prompt_name):
        prompt_parts.append(f"# {prompt_name}\n")
    if maybe(desc):
        prompt_parts.append(
            f"## Description\n{replace_placeholders(desc, fill_values)}\n"
        )
    if maybe(what):
        prompt_parts.append(
            f"## What This Mega-Prompt Does\n{replace_placeholders(what, fill_values)}\n"
        )
    if maybe(tips):
        prompt_parts.append(f"## Tips\n{replace_placeholders(tips, fill_values)}\n")
    if maybe(how):
        prompt_parts.append(
            f"## How to Use\n{replace_placeholders(how, fill_values)}\n"
        )
    if maybe(addl):
        prompt_parts.append(
            f"## Additional Tips\n{replace_placeholders(addl, fill_values)}\n"
        )

    header_text = "\n".join(prompt_parts)
    core = replace_placeholders(str(mega), fill_values).strip()

    system_prompt = f"{header_text}\n---\n\n{core}" if header_text else core

    return system_prompt, unresolved


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


def main():
    print("=== Dynamic Ollama Assistant (Interactive, CSV) ===")
    print(f"CSV folder: {CSV_DIR}")
    print(f"Model: {DEFAULT_MODEL}")

    # Load CSVs
    data_by_sheet = load_csvs(CSV_DIR, CSV_GLOB)
    if not data_by_sheet:
        print(f"❌ No CSVs found with pattern '{CSV_GLOB}' in '{CSV_DIR}'.")
        sys.exit(1)

    # --- Main Loop ---
    while True:
        # --- Menu Navigation State ---
        picked_sheet = None
        picked_sub = None
        picked_page = None

        # 1. Pick a sheet (Category)
        sheet_names = list(data_by_sheet.keys())
        picked_sheet = pick_from_menu("Pick a Category:", sheet_names)
        if picked_sheet == "__EXIT__" or not picked_sheet:
            print("\nBye!")
            return

        # --- Sub-Category Loop ---
        while True:
            df = data_by_sheet[picked_sheet]
            sub_categories = list(df["Sub-Category"].unique())
            picked_sub = pick_from_menu(
                f"Pick a Sub-Category in '{picked_sheet}':",
                sub_categories,
                can_go_back=True,
            )

            if picked_sub == "__BACK__":
                break  # Go back to sheet selection
            if picked_sub == "__EXIT__" or not picked_sub:
                print("\nBye!")
                return

            # --- Page Loop ---
            while True:
                df_sub = df[df["Sub-Category"] == picked_sub]
                pages = list(df_sub["Short Description (PAGE NAME)"].unique())
                picked_page = pick_from_menu(
                    f"Pick a Page in '{picked_sub}':", pages, can_go_back=True
                )

                if picked_page == "__BACK__":
                    break  # Go back to sub-category selection
                if picked_page == "__EXIT__" or not picked_page:
                    print("\nBye!")
                    return

                # --- Found a page, break out of menu loops ---
                goto_chat = True
                break  # Exit page loop

            if locals().get("goto_chat"):
                break  # Exit sub-category loop

        if not locals().get("goto_chat"):
            continue  # Go back to the main loop for category selection

        # --- Process the selected page ---
        row = df.loc[
            (df["Sub-Category"] == picked_sub)
            & (df["Short Description (PAGE NAME)"] == picked_page)
        ].iloc[0]

        print(f"\n✅ Loaded Prompt: {row.get('Short Description (PAGE NAME)')}")
        print(f"   From: {picked_sheet} > {picked_sub}")

        # Fill placeholders interactively
        fill_values: Dict[str, str] = {}
        system_prompt, unresolved = build_system_prompt(row, fill_values)

        if unresolved:
            print(
                "\nThis prompt needs a few details. Press Enter to leave any value blank (will keep placeholder)."
            )
            for k in list(unresolved.keys()):
                if val := input(f"  • {k}: ").strip():
                    fill_values[k] = val
            system_prompt, unresolved = build_system_prompt(row, fill_values)

        # Preview
        print("\n— System prompt preview (first 800 chars) —")
        print(system_prompt[:800] + ("..." if len(system_prompt) > 800 else ""))

        # Let user override model if desired
        model = input(f"\nModel to use [{DEFAULT_MODEL}]: ").strip() or DEFAULT_MODEL

        # --- Setup Output File ---
        output_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize page name for filename
        safe_page_name = re.sub(r"[^\w_.)( -]", "", picked_page).strip()
        output_file = os.path.join(output_dir, f"{timestamp}_{safe_page_name}.txt")

        print(f"\n📝 Saving conversation to: {output_file}")

        # Write system prompt to the file initially
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"--- SYSTEM PROMPT ---\n{system_prompt}")

        print("\nLaunching chat with Ollama.")
        try:
            # Main chat loop
            while True:
                user_msg = input("\n> ").strip()
                if not user_msg:
                    continue

                query_ollama_chat(
                    model, system_prompt, user_msg, output_file=output_file
                )

                # Ask for next action
                action_prompt = "\nNext action:\n  [C]ontinue chat\n  [S]tart over (new prompt)\n  [E]xit\n> "
                while True:
                    next_action = input(action_prompt).strip().lower()
                    if next_action in ["c", "s", "e"]:
                        break
                    print("Invalid choice. Please enter 'c', 's', or 'e'.")

                if next_action == "s":
                    print("\n✨ Starting over...")
                    break  # break inner chat loop to start over
                elif next_action == "e":
                    print("\nBye!")
                    return  # exit program
                # if 'c', just continue to the next iteration of the loop

        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            return  # Exit cleanly
        except requests.exceptions.RequestException as e:
            print(f"\n❌ API Error: {e}")
            print("Is the Ollama server running? Try: ollama serve")
            sys.exit(1)


if __name__ == "__main__":
    main()
