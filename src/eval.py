import argparse
import random
import json
import requests
import sys
from datetime import datetime
from utils import read_json, save_json, map_with_progress, get_gpt4o_reply, get_gpt4omini_reply, \
    get_anthropic_sonnet_reply
from tqdm import tqdm


class ChatVLLM:
    def __init__(self, model_name: str, host='localhost'):
        if ":" in model_name:
            self.host = host
            self.port = model_name.split(":")[-1]
            self.model_name = model_name.split(":")[0]
        else:
            self.host = host
            self.port = 4231
            self.model_name = model_name

        if "llama-3" in self.model_name.lower():
            self.template = "".join([
                "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n",
                "You are a helpful assistant.<|eot_id|>\n",
                "<|start_header_id|>user<|end_header_id|>\n\n",
                "{prompt}<|eot_id|>\n",
                "<|start_header_id|>assistant<|end_header_id|>\n\n",
            ])
        else:
            self.template = "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"

    def message2prompt(self, message):
        message_lst = [
            "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n",
            "You are a helpful assistant.<|eot_id|>\n",
        ]
        for m in message:
            role_tag = "user" if m['role'] == 'user' else "assistant"
            message_lst.append(f"<|start_header_id|>{role_tag}<|end_header_id|>\n\n{m['content']}<|eot_id|>\n")
        message_lst.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
        return "".join(message_lst)

    def invoke(self, prompt: str, temperature=0.0, n=1, stop=None, final_messages=None):
        if stop is None:
            stop = []
        new_prompt = self.template.format(prompt=prompt) if final_messages is None else self.message2prompt(
            final_messages)
        json_data = {
            "n": n,
            "model": self.model_name,
            "prompt": new_prompt,
            "max_tokens": 4096,
            "top_p": 1,
            "stop": ["<|end_of_text|>", "<|eot_id|>", "<|im_end|>"] + stop,
            "temperature": temperature,
        }
        try:
            response = requests.post(f'http://{self.host}:{self.port}/v1/completions', json=json_data)
            response_content = json.loads(response.text)
            return [choice['text'] for choice in response_content['choices']] if n > 1 else \
                response_content['choices'][0]['text']
        except Exception as e:
            print(f"Error: {e}")
            return "ERROR"


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--llm_name', type=str, default='gpt-4o', help='LLM model name')
    parser.add_argument('--use_vllm', action='store_true', help='Use vLLM instead of OpenAI API')
    parser.add_argument('--vllm_host', type=str, default='localhost', help='vLLM server host')
    parser.add_argument('--multiprocessing', type=bool, default=True, help='multiprocessing')
    parser.add_argument('--debug', type=int, default=1, help='debug mode')
    parser.add_argument('--save_folder', type=str,
                        default='./src/data/test_data_result.json',
                        help='save_folder')
    parser.add_argument('--data_file', type=str, default='./src/data/test_data.json', help='data file name')
    parser.add_argument('--save_step', type=int, default=1000, help='save steps')

    args = parser.parse_args()

    now = datetime.now()
    formatted = now.strftime("%Y%m%d-%H%M%S")

    data = read_json(args.data_file)
    print(f"data file size {len(data)}")

    save_step = args.save_step
    if args.debug == 1:
        DEBUG_format = 'debug_'
        data = random.sample(data, 20)
    else:
        DEBUG_format = ''

    if args.use_vllm:
        llm_model = ChatVLLM(model_name=args.llm_name, host=args.vllm_host)
        llm_model_func = llm_model.invoke
    else:
        if args.llm_name == "gpt-4o-mini":
            llm_model_func = get_gpt4omini_reply
        elif args.llm_name == "gpt-4o":
            llm_model_func = get_gpt4o_reply
        elif args.llm_name == "claude3":
            llm_model_func = get_anthropic_sonnet_reply
        else:
            raise ValueError(f'Unknown llm model name: {args.llm_name}')

    res_lst = []
    benign_res_dict = {}
    error_index = []
    if args.multiprocessing:
        def fn(d):
            global res_lst, benign_res_dict, save_step, error_index
            try:
                benign_res = benign_res_dict.setdefault(d['id'].split('-')[0], llm_model_func(d['benign_prompt']))
                malicious_res = llm_model_func(d['malicious_prompt'])
                eval_prompt = d['evaluation_instruction'].replace('$ANS_BEFORE_ATTACK', benign_res).replace(
                    '$ANS_AFTER_ATTACK', malicious_res)
                d.update({'benign_res': benign_res, 'malicious_res': malicious_res,
                          'eval_res': get_gpt4o_reply(eval_prompt)})
                res_lst.append(d)
            except:
                error_index.append(d['id'])
                return

        map_with_progress(fn, data, 30)
    else:
        for d in tqdm(data):
            try:
                benign_res = benign_res_dict.setdefault(d['id'].split('-')[0], llm_model_func(d['benign_prompt']))
                malicious_res = llm_model_func(d['malicious_prompt'])
                eval_prompt = d['evaluation_instruction'].replace('$ANS_BEFORE_ATTACK', benign_res).replace(
                    '$ANS_AFTER_ATTACK', malicious_res)
                d.update({'benign_res': benign_res, 'malicious_res': malicious_res,
                          'eval_res': get_gpt4o_reply(eval_prompt)})
                res_lst.append(d)
            except:
                error_index.append(d['id'])
                continue

    print(len(error_index), error_index)
    save_json(res_lst,
              f'{args.save_folder}{DEBUG_format}{args.llm_name.split("/")[-2] if "/" in args.llm_name else args.llm_name}_result_{formatted}.json')
