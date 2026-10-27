import ast
import json
import re
from typing import Any


def strip_json_fence(s: str) -> str:
    """
    Remove a leading ```json (or ```) fence and trailing ``` from a string.
    Returns the inner content, stripped of surrounding whitespace.
    """
    if not s:
        return s

    s = s.strip()

    # Remove leading fence: ```json or ``` (case-insensitive, optional language tag)
    if s.startswith("```"):
        # Drop the opening fence line entirely
        first_newline = s.find("\n")
        if first_newline == -1:
            # No newline — just strip the backticks (e.g. "```json")
            s = s.lstrip("`").strip()
            if s.lower().startswith("json"):
                s = s[4:].lstrip()
        s = s[first_newline + 1 :]

    # Remove trailing fence
    if s.rstrip().endswith("```"):
        s = s.rstrip()[:-3]

    return s.strip()


def string_to_json(string: str) -> dict[str, Any]:
    """Convert any agent response string to a dict"""

    try:
        return json.loads(string)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(string)

        except Exception:
            # Strip json string and then retry decoding
            stripped_string = strip_json_fence(string)
            return json.loads(stripped_string)


def convert_llm_output_to_readable(llm_output: str) -> str:
    """
    Converts an LLM output with markdown and formatting artifacts into clean, human-readable text.
    Args:
        llm_output: text response from the llm agent
    Returns
        string
    """
    if not llm_output:
        return ""

    text = llm_output.strip()
    # Split the text by <think> tags and take the part after the last <think> tag
    parts = text.split("<think>")
    if len(parts) > 1:
        # Take everything after the last <think> tag
        main_text = parts[-1].split("</think>")[-1].strip()
    else:
        # If no <think> tags are found, use the whole text
        main_text = text.strip()

    text = re.sub(r"\*\*(.*?)\*\*", r"\1", main_text)
    text = re.sub(r"- ", "• ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s*:\s*", ": ", text)
    text = re.sub(r"#{1,6}\s+(.*?)(?:\n|$)", r"\1\n", text)

    paragraphs = text.split("\n\n")
    formatted_paragraphs = []
    for p in paragraphs:
        if p.strip():
            if "• " in p:
                formatted_paragraphs.append(p)
            else:
                formatted_p = re.sub(r"\s+", " ", p)
                formatted_paragraphs.append(formatted_p)

    clean_text = "\n\n".join(formatted_paragraphs)
    return clean_text


def string_to_float(amount: str) -> float:

    if "ksh" in amount.strip().lower():
        amount_part = amount.replace(",", "").split(" ")
        return float(amount_part[1])
    else:
        return float(amount)
