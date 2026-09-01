import requests
from pathlib import Path


LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"


SYSTEM_PROMPT = """
You are CleanDrop's filename suggestion engine.

Your task is to suggest a useful human-readable filename.

Rules:

1. Use ONLY information provided in the input.
2. Never invent what a file contains.
3. Never assume a webpage title describes the downloaded file.
4. Prefer direct resource information over weak page context.
5. Remove meaningless hashes and random IDs.
6. Preserve important names, subjects, document types, versions and dates.
7. Do not change the file extension.
8. Use underscores between words.
9. Keep the filename concise.
10. If the evidence is insufficient, return the original filename.
11. Return ONLY the filename.
"""


def suggest_filename(context):

    prompt = build_prompt(context)

    payload = {

        "messages": [

            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },

            {
                "role": "user",
                "content": prompt
            }

        ],

        "temperature": 0.1,

        "max_tokens": 40,

        "stream": False

    }


    response = requests.post(

        LLAMA_URL,

        json=payload,

        timeout=30

    )


    response.raise_for_status()


    data = response.json()


    content = (
        data["choices"][0]
        ["message"]
        ["content"]
    )


    return clean_filename(
        content,
        context["filename"]
    )


def build_prompt(context):

    return f"""
Original filename:
{context.get("filename", "")}

MIME type:
{context.get("mime", "")}

Download URL:
{context.get("url", "")}

Referrer:
{context.get("referrer", "")}

Page title:
{context.get("page_title", "")}

Page description:
{context.get("page_description", "")}

Generate the best filename supported by this evidence.

Return ONLY the filename.
"""


def clean_filename(
    result,
    original_filename
):

    result = result.strip()

    result = result.replace(
        "```",
        ""
    ).strip()


    if "\n" in result:

        result = (
            result
            .splitlines()[0]
            .strip()
        )


    result = (
        result
        .strip('"')
        .strip("'")
        .strip()
    )


    if not result:

        return original_filename


    # Prevent the model from returning
    # an entirely different extension.

    original_ext = (
        Path(original_filename)
        .suffix
        .lower()
    )


    result_ext = (
        Path(result)
        .suffix
        .lower()
    )


    if result_ext != original_ext:

        result = (
            Path(result).stem
            + original_ext
        )


    # Windows-invalid characters.

    invalid = '<>:"/\\|?*'

    for char in invalid:

        result = result.replace(
            char,
            "_"
        )


    result = result.strip(
        " ."
    )


    if not result:

        return original_filename


    return result