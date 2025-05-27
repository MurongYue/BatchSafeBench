import os
import glob
from multiprocessing.pool import ThreadPool
from typing import Any
import json
import anthropic
from openai import OpenAI
import os
import time
from openai import AzureOpenAI
from tqdm import tqdm
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential

# openai_client = OpenAI.client(
#     api_key=os.getenv('OPENAI_API_KEY')
# )

def save_json(data, file_name):
    try:
        with open(file_name, 'w') as file:
            json.dump(data, file, indent=4)
        print(f'Data saved to {file_name} successfully.')
    except Exception as e:
        print(f'Error: {e}')


def read_json(file_name):
    with open(file_name, 'r') as file:
        data = json.load(file)
    return data


def load_json(data_path):
    # f = open(data_path, encoding="utf-8")
    f = open(data_path)
    allData = json.load(f)
    print("data amount:", len(allData))
    return allData


def read_jsonl(file_path):
    """
    Read a JSONL file and return a list of dictionaries.

    Args:
        file_path (str): The path to the JSONL file.

    Returns:
        list: A list of dictionaries, each representing a JSON object from the file.
    """
    data = []
    with open(file_path, 'r') as f:
        for line in f:
            json_data = json.loads(line)
            data.append(json_data)
    return data


def get_gpt4omini_reply(user_prompt):
    client = OpenAI(
        api_key=os.getenv('OPENAI_API_KEY'))
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"You are a helpful assistant.",
            },
            {
                "role": "user",
                "content": f"{user_prompt}",
            },
        ],
        temperature=0,
        max_tokens=4096,
        top_p=1
    )
    return completion.choices[0].message.content


def get_gpt4o_reply(user_prompt):
    client = OpenAI(
        api_key=os.getenv('OPENAI_API_KEY'))

    completion = client.chat.completions.create(
        model="gpt-4o-20240806",
        messages=[
            {
                "role": "system",
                "content": f"You are a helpful assistant.",
            },
            {
                "role": "user",
                "content": f"{user_prompt}",
            },
        ],
        temperature=0,
        max_tokens=4096
    )
    return completion.choices[0].message.content


def get_anthropic_sonnet_reply(message):
    client = anthropic.Anthropic(
        api_key=os.getenv('ANTHROPIC_API_KEY'),
    )
    message = client.messages.create(
        model="claude-3-5-sonnet",
        max_tokens=4096,
        messages=[
            {"role": "user", "content": f"{message}"}
        ]
    )
    return message.content[0].text


def get_o1_reply(user_prompt):
    client = AzureOpenAI(
        api_key=os.getenv('OPENAI_API_KEY'))

    completion = client.chat.completions.create(
        model="o1-20241217",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_prompt
                    },
                ],
            }
        ],
    )
    return completion.choices[0].message.content


def map_with_progress(f: callable, xs: list[Any], num_threads: int = 50):
    """
    Apply f to each element of xs, using a ThreadPool, and show progress.
    """
    if os.getenv("debug"):
        return list(map(f, tqdm(xs, total=len(xs))))
    else:
        with ThreadPool(min(num_threads, len(xs))) as pool:
            return list(tqdm(pool.imap(f, xs), total=len(xs)))
