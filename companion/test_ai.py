import requests
import json


URL = "http://127.0.0.1:8080/v1/chat/completions"


payload = {
    "messages": [
        {
            "role": "system",
            "content": "You are a filename generator. Return only the filename."
        },
        {
            "role": "user",
            "content": """
The downloaded file is an image of a cannonball jellyfish.

Create a concise filename using underscores.
Do not include the extension.

Answer:
/no_think
"""
        }
    ],

    "temperature": 0.7,
    "top_p": 0.8,
    "max_tokens": 50,
    "stream": False
}


response = requests.post(
    URL,
    json=payload,
    timeout=60
)


print("HTTP STATUS:")
print(response.status_code)

print()
print("RAW RESPONSE:")
print(response.text)

print()

try:

    data = response.json()

    print("PARSED JSON:")
    print(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        )
    )

except Exception as error:

    print("JSON ERROR:")
    print(error)