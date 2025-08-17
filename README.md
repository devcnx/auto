# Dynamic Ollama Assistant

**Date**: Saturday, August 16th, 2025   
**Author**: Brittaney Perry-Morgan

An interactive command-line assistant powered by Ollama that dynamically loads and manages a powerful library of prompts from simple CSV files. This tool is designed to streamline your workflow with local large language models by making it easier to select, customize, and interact with a vast collection of pre-built prompts.

## ✨ Key Features

* **CSV-Based Prompt Library:** Easily manage and extend your prompt library using CSV files. Each file represents a category, making organization simple and scalable.
* **Interactive Menu System:** A user-friendly, paginated menu allows you to navigate through categories, sub-categories, and individual prompts with ease.
* **Dynamic Placeholders:** Prompts can contain placeholders like `[[Your Topic]]` or `<Your Goal>`, which you can fill in interactively before starting a chat session.
* **OCR Integration with Smoldocling:** Populate placeholders by providing a file path to an image or PDF. The tool will automatically extract the text and use it as input.
* **Chat with Ollama:** Seamlessly interact with your chosen local LLM (e.g., Llama 3.1) through the Ollama API.
* **Conversation Logging:** Automatically saves your chat sessions, including the system prompt, to an `output` directory for easy reference.

---

## 🚀 How to Use

### Prerequisites

1.  **Python 3.13+:** Ensure you have Python 3.13+ installed on your system.
2.  **Ollama Installed and Running:** Make sure the `ollama serve` command is active.
3.  **A Local LLM:** Pull a model to use (e.g., `ollama pull llama3.1`).

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Running the Application

1.  **Set up your prompts:** Create your `.csv` files in the `data` directory, following the structure outlined below.

2.  **Run the script:**
    ```bash
    python dynamic_ollama_assistant.py
    ```

3.  **Follow the on-screen instructions:**
    * Select a category (e.g., "Marketing").
    * Choose a sub-category.
    * Pick a specific prompt.
    * Fill in any required placeholders. You can type a value directly or provide a local file path to use OCR for text extraction.
    * Start chatting with your local LLM!

---

## 📂 CSV File Structure

This script is designed to read prompt data from `.csv` files located in the `/data` directory. To use your own prompts, you must create one or more CSV files that follow a specific structure and naming convention.

### File Naming Convention

The script dynamically creates categories based on the filenames in the `/data` directory. Your files must follow this pattern:

`Mega-Prompts for <CategoryName>.csv`

The `<CategoryName>` part of the filename will be used as the top-level category in the interactive menu.

* **Example:** A file named `Mega-Prompts for Writing.csv` will create a "Writing" category in the menu.

### Column Headers

Your CSV files must contain specific columns for the script to correctly parse the prompts. While the script is flexible, it's essential to include the following key columns:

| Column Header                 | Purpose                                                                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `Category`                    | The main category for the prompt (e.g., "Business").                                                                                 |
| `Sub-Category`                | The second-level menu option (e.g., "Business Communications").                                                                      |
| `Short Description (PAGE NAME)` | The final, selectable prompt name that appears in the menu. This should be a concise and clear title for the prompt.               |
| `Mega-Prompt`                 | **This is the most important column.** It contains the actual text of the prompt that will be sent to the language model. You can include placeholders like `[[Your Topic]]` or `<Your Goal>` here. |
| `Description `                | A brief description of what the prompt does. This is included in the system prompt for context.                                      |
| `Tips`                        | Any tips on how to best use the prompt.                                                                                              |

### Mega-Prompt Column Content Example (Placeholders)

```markdown
# CONTEXT:
You are a [explain what the role is - e.g., "Strategic Consultant" or "Proposal Reviewer" or "Proposal Writer" etc. ] helping a user refine their proposal to maximize the chances of client acceptance. Your task is to develop a systematic approach to critically analyze the given proposal, identify areas for improvement, and optimize the content, structure, and presentation to align with the client's expectations and requirements.

# ROLE:
Adopt the role of a [explain what the role is - e.g., "Strategic Consultant" or "Proposal Reviewer" or "Proposal Writer" etc. ] with expertise in [explain what the role does - e.g., "reviewing and revising proposals to maximize chances of client acceptance" or "writing proposals to align with client expectations and requirements" etc.].

# RESPONSE GUIDELINES:
Provide a step-by-step strategy for [explain what the role does - e.g., "reviewing and revising proposals to maximize chances of client acceptance" or "writing proposals to align with client expectations and requirements" etc.], organized as follows:

[explain what the role does - e.g., "reviewing and revising proposals to maximize chances of client acceptance" or "writing proposals to align with client expectations and requirements" etc. for] [CLIENT]

Objectives:
1. [Objective 1]
2. [Objective 2] 
3. [Objective 3]

### Steps

Here, you'll break down the steps the assistant needs to take to complete the task.

Example:

Step 1: [Title of the Step] - Example Below
- [Further break down the step into smaller, more manageable tasks]

Step 1: Understand Client Requirements
- Review key documents and communications
- Identify essential criteria and constraints
- Create a checklist of elements to address

Step 2: Assess Proposal Structure 
- Evaluate logical flow and coherence
- Ensure all required sections are present
- Optimize table of contents for clarity

...

# TASK CRITERIA:

Set the criteria for the task. This are the rules that the assistant must follow to complete the task.

- Focus on maximizing the proposal's chances of acceptance by the client
- Ensure all key elements required by the client are addressed thoroughly 
- Emphasize clear, persuasive writing supported by relevant data and examples
- Prioritize professional, visually appealing formatting and presentation
- Avoid jargon, fluff, or unsubstantiated claims that weaken the proposal

# INFORMATION ABOUT ME:

Set the information about the user. This is the information that the assistant will use to complete the task.

- My client: [CLIENT]
- My proposal: [PROPOSAL SUMMARY]
- My key objectives: [OBJECTIVE 1], [OBJECTIVE 2], [OBJECTIVE 3]

# RESPONSE FORMAT:

Set the format for the response. This is the format that the assistant will use to complete the task.

Provide the [explain what the role does - e.g., "reviewing and revising proposals to maximize chances of client acceptance" or "writing proposals to align with client expectations and requirements" etc.] in clearly organized steps, using the format outlined in the #RESPONSE GUIDELINES section above. Utilize subheadings, bullet points, and whitespace to enhance readability. Avoid XML tags completely.
"   
```

_**Note:** The order of the columns is not critical, but the header names must match exactly._

