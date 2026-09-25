import requests
from pathlib import Path
from config import get_llm_url


SYSTEM_PROMPT = """
You are CleanDrop's filename suggestion engine.

Your task is to suggest a useful human-readable filename.

Rules:

1. Use ONLY information provided in the input.
2. Never invent what a file contains.
3. The page description is usually your most reliable signal — it is
   written specifically to describe the page's content, unlike a page
   title, which is often just a site or brand name (e.g. "Wikipedia",
   "Google Search"). Prefer the description over the title whenever
   the description contains specific, relevant information, even if
   the title itself is short, generic, or unhelpful.
4. A generic or short page title does NOT by itself mean there isn't
   enough evidence — check the page description and URL before
   concluding that.
5. Never assume a webpage title describes the downloaded file if the
   title looks like a generic site/brand name rather than specific
   content.
6. Prefer specific, concrete details (a descriptive URL path, a named
   subject, a specific document title) over vague or generic branding.
7. Remove meaningless hashes and random IDs.
8. Preserve important names, subjects, document types, versions and dates.
9. Do not change the file extension.
10. Use underscores between words.
11. Keep the filename concise.
12. Only fall back to the original filename if NONE of the provided
    fields (title, description, URL, referrer) contain any specific,
    relevant information — a generic or empty title alone is not
    sufficient reason to give up if the description is informative.
13. Return ONLY the filename.
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


    # This call now happens synchronously during download
    # naming (onDeterminingFilename), so it must fail fast
    # rather than risk stalling a download indefinitely.
    # Measured p95 latency on real hardware is ~1.9s; 6s
    # gives comfortable margin without risking a long hang.
    response = requests.post(

        get_llm_url(),

        json=payload,

        timeout=6

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

    return (
        f"DESCRIPTION: {context.get('page_description', '')}\n"
        f"TITLE: {context.get('page_title', '')}\n"
        f"URL: {context.get('url', '')}\n"
        f"ORIGINAL: {context.get('filename', '')}\n"
        "OUTPUT:"
    )


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


    # The prompt ends with "OUTPUT:" as a completion cue — small
    # models occasionally echo the label back rather than just
    # continuing past it.
    if result.upper().startswith("OUTPUT:"):

        result = result[len("OUTPUT:"):].strip()


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