# Efficient but Vulnerable: Benchmarking and Defending LLM Batch Prompting Attack
This repository provides dataset for our paper [Efficient but Vulnerable: Benchmarking and Defending LLM Batch Prompting Attack](https://arxiv.org/abs/2503.15551). If find this repository useful for your work, please cite our paper.


```bibtex
@article{yue2025efficient,
  title={Efficient but Vulnerable: Benchmarking and Defending LLM Batch Prompting Attack},
  author={Yue, Murong and Yao, Ziyu},
  journal={arXiv preprint arXiv:2503.15551},
  year={2025}
}
```

## Overview
Batch prompting, which combines a batch of multiple queries sharing the same context in one inference, 
has emerged as a promising solution to reduce inference costs. However, our study reveals a significant security vulnerability in batch prompting: malicious users can inject attack instructions into a batch, leading to unwanted interference across all queries, which can result in the inclusion of harmful content, such as phishing links, or the disruption of logical reasoning. In this paper, we constructed BatchSafeBench and evaluated multiple LLMs. We found that all of them suffer from the batch prompting attack. We also developed the probing method to detect this type of attack.
![Overview](overview.png)

## Dataset

The full training and testing datasets can be found [here](https://huggingface.co/datasets/MurongYue/BatchSafeBench).

## Data Generation

The data generation process involves creating evaluation instances for both GSM8K and HotpotQA datasets. The code supports:

1. **GSM8K Dataset Generation**:
   - Generates evaluation instances with both benign and malicious prompts
   - Supports batch processing with configurable batch sizes
   - Includes both textual and numerical reasoning attacks
   - Creates evaluation prompts to assess attack effectiveness

2. **HotpotQA Dataset Generation**:
   - Constructs evaluation instances using supporting facts and context
   - Generates both benign and malicious prompts
   - Supports various attack types including textual and reasoning attacks
   - Creates evaluation prompts to measure attack success

To generate the datasets, use the following command:
```bash
python src/data_generation.py
```

## Evaluation

The evaluation framework supports multiple LLM models and provides comprehensive assessment of batch prompting attacks:

1. **Supported Models**:
   - Openai models
   - Claude models
   - Custom models through vLLM. For learning deploying vllm api, please refer to [vllm] (https://docs.vllm.ai/en/latest/)

2. **Evaluation Process**:
   - Compares responses between benign and malicious prompts
   - Uses GPT-4o as an evaluator to assess attack success
   - Supports both single and batch processing
   - Saves detailed results including:
     - Original responses
     - Attacked responses
     - Evaluation results

3. **Usage**:
```bash
python src/eval.py --llm_name [model_name] --data_file [path_to_data] --save_folder [output_path]
```

Optional arguments:
- `--use_vllm`: Use vLLM instead of OpenAI API
- `--vllm_host`: Specify vLLM server host
- `--multiprocessing`: Enable multiprocessing (default: True)
- `--debug`: Enable debug mode
- `--save_step`: Number of steps between saves

The evaluation results are saved in JSON format with timestamps for easy tracking and analysis.


