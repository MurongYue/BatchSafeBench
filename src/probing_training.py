import json
import torch
from torch.utils.data import DataLoader, Dataset
import torch.nn as nn
from transformers import LlamaModel, AutoTokenizer, AdamW
import os
from pathlib import Path
import time
from datetime import datetime
from transformers import get_scheduler
import numpy as np
import pdb

cur_time = datetime.now().strftime('%Y-%m-%d-%H%M%S')

class JsonDataset(Dataset):
    def __init__(self, data, tokenizer, max_length=512):
        self.data = data
        self.tokenizer = tokenizer
        self.max_length = max_length
        print(f"Initializing dataset with {len(data)} samples")

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        text = self.make2llama_prompt(self.data[idx]['text'])
        label = self.data[idx]['label']
        encoded = self.tokenizer(
            text,
            truncation=True,
            padding='max_length',
            max_length=self.max_length,
            return_tensors='pt'
        )
        return {
            'input_ids': encoded['input_ids'].squeeze(0),
            'attention_mask': encoded['attention_mask'].squeeze(0),
            'label': torch.tensor(label, dtype=torch.long)
        }

    def make2llama_prompt(self, prompt):
        # return f""""<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n",
        #     "You are a helpful assistant.<|eot_id|>\n",  # The system prompt is optional
        #     "<|start_header_id|>user<|end_header_id|>\n\n",
        #     "{prompt}<|eot_id|>\n",
        #     "<|start_header_id|>assistant<|end_header_id|>\n\n"
        # """
        return prompt


class ProbingLayer(nn.Module):
    def __init__(self, hidden_size, num_classes):
        super(ProbingLayer, self).__init__()
        self.linear = nn.Linear(hidden_size, num_classes)
        print(f"Initializing probing layer with hidden size {hidden_size} and {num_classes} classes")

    def forward(self, x):
        return self.linear(x)


class LlamaWithProbingLayer(nn.Module):
    def __init__(self, llama_model, num_classes):
        super(LlamaWithProbingLayer, self).__init__()
        print("Initializing LlamaWithProbingLayer model...")
        self.llama = llama_model
        hidden_size = llama_model.config.hidden_size  # Dynamically get the hidden size
        self.probing_layer = ProbingLayer(hidden_size, num_classes)
        self.convert_to_float16()
        print("Model initialization completed")

    def forward(self, input_ids, attention_mask=None):
        # print(input_ids)
        with torch.no_grad():  # Freeze Llama model
            outputs = self.llama(input_ids, attention_mask=attention_mask)
        # print(outputs)
        last_hidden_state = outputs.last_hidden_state
        cls_token_state = last_hidden_state[:, -1, :]
        return self.probing_layer(cls_token_state), cls_token_state

    def convert_to_float16(self):
        """Ensure that the probing layer parameters are in float16."""
        self.probing_layer = self.probing_layer.to(dtype=torch.float16)


def load_tokenizer_and_model(model_path):
    """
    Load tokenizer and model with GPU support
    """
    try:
        start_time = time.time()
        model_path = str(Path(model_path))
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting to load tokenizer and model from: {model_path}")

        # Check GPU availability
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {device}")

        if not os.path.exists(model_path):
            raise ValueError(f"Model path does not exist: {model_path}")

        print("Loading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            use_fast=True,
            local_files_only=True
        )

        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            print("Set pad_token to eos_token")

        print("Loading LLaMA model...")
        llama_model = LlamaModel.from_pretrained(
            model_path,
            local_files_only=True,
            torch_dtype=torch.float16  # Use float16 for efficiency
        ).to(device)  # Move model to GPU

        elapsed_time = time.time() - start_time
        print(f"Model loading completed in {elapsed_time:.2f} seconds")
        return tokenizer, llama_model, device

    except Exception as e:
        print(f"Error loading tokenizer and model: {str(e)}")
        raise


def train_model(train_data, model_path, num_classes, num_epochs=1, batch_size=32, learning_rate=1e-3,
                warmup_steps=500, save_path=f"trained_model_{cur_time}.pth"):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting training process")
    print(f"Configuration: epochs={num_epochs}, batch_size={batch_size}, learning_rate={learning_rate}")

    # Load tokenizer and model
    tokenizer, llama_model, device = load_tokenizer_and_model(model_path)

    # Prepare dataset and dataloader
    print("Preparing training dataset...")
    train_dataset = JsonDataset(train_data, tokenizer)
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=1,
        pin_memory=True
    )
    print(f"Created DataLoader with {len(train_loader)} batches")

    # Initialize model and optimizer
    print("Initializing model and optimizer...")
    model = LlamaWithProbingLayer(llama_model, num_classes)
    model = model.to(device)
    model.train()

    loss_fn = nn.CrossEntropyLoss().to(device)
    optimizer = AdamW(model.probing_layer.parameters(), lr=learning_rate)

    # Calculate total steps for scheduler
    total_steps = len(train_loader) * num_epochs
    scheduler = get_scheduler(
        "linear", optimizer=optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps
    )
    print("Model and optimizer initialized with learning rate scheduler")

    # Training loop
    total_start_time = time.time()
    cls_token_states_list = []
    labels_list = []
    for epoch in range(num_epochs):
        epoch_start_time = time.time()
        total_loss = 0
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting epoch {epoch + 1}/{num_epochs}")

        for batch_idx, batch in enumerate(train_loader):
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            labels = batch['label'].to(device)
            labels_list.extend(labels.cpu().numpy())

            outputs, cls_token_state = model(input_ids, attention_mask=attention_mask)
            cls_token_states_list.extend(cls_token_state.cpu().numpy())

            loss = loss_fn(outputs, labels)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            scheduler.step()  # Update learning rate

            # Log batch progress
            batch_loss = loss.item()
            total_loss += batch_loss

            if batch_idx % 10 == 0:
                progress = (batch_idx + 1) / len(train_loader) * 100
                print(
                    f"Epoch {epoch + 1}/{num_epochs} [{batch_idx}/{len(train_loader)} ({progress:.1f}%)] - Batch Loss: {batch_loss:.4f}")

        # Log epoch summary
        avg_loss = total_loss / len(train_loader)
        epoch_time = time.time() - epoch_start_time
        print(f"Epoch {epoch + 1} Summary:")
        print(f"Average Loss: {avg_loss:.4f}")
        print(f"Time taken: {epoch_time:.2f} seconds")
        print("-" * 50)

    cls_token_states_path = "/scratch/myue/safety_saved/npy/cls_token_states_v9.npy"
    labels_path = "/scratch/myue/safety_saved/npy/labels_v9.npy"
    np.save(cls_token_states_path, np.array(cls_token_states_list))
    np.save(labels_path, np.array(labels_list))
    print(f"Saved cls_token_state embeddings to {cls_token_states_path}")
    print(f"Saved labels to {labels_path}")

    # Save model
    save_dir = os.path.dirname(save_path)
    if save_dir and not os.path.exists(save_dir):
        os.makedirs(save_dir)
        print(f"Created directory: {save_dir}")

    print(f"Saving model to {save_path}")
    torch.save(model.state_dict(), save_path)

    total_time = time.time() - total_start_time
    print(f"Training completed in {total_time:.2f} seconds")
    return model, device


# def test_model(test_data, model, model_path, num_classes, device, batch_size=32):
#     print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting testing process")
#
#     # Load tokenizer
#     print("Loading tokenizer for testing...")
#     tokenizer, _, _ = load_tokenizer_and_model(model_path)
#
#     # Prepare test dataset
#     print("Preparing test dataset...")
#     test_dataset = JsonDataset(test_data, tokenizer)
#     test_loader = DataLoader(
#         test_dataset,
#         batch_size=batch_size,
#         num_workers=4,
#         pin_memory=True
#     )
#     print(f"Created test DataLoader with {len(test_loader)} batches")
#
#     model.eval()
#     total_correct = 0
#     total_samples = 0
#     total_loss = 0
#     loss_fn = nn.CrossEntropyLoss().to(device)
#
#     print("Starting evaluation...")
#     test_start_time = time.time()
#
#     with torch.no_grad():
#         for batch_idx, batch in enumerate(test_loader):
#             # Move batch to GPU
#             input_ids = batch['input_ids'].to(device)
#             attention_mask = batch['attention_mask'].to(device)
#             labels = batch['label'].to(device)
#
#             outputs, _ = model(input_ids, attention_mask=attention_mask)
#             loss = loss_fn(outputs, labels)
#             total_loss += loss.item()
#
#             predictions = torch.argmax(outputs, dim=1)
#             total_correct += (predictions == labels).sum().item()
#             total_samples += labels.size(0)
#
#             if batch_idx % 10 == 0:
#                 progress = (batch_idx + 1) / len(test_loader) * 100
#                 print(f"Testing progress: [{batch_idx}/{len(test_loader)} ({progress:.1f}%)]")
#
#     accuracy = total_correct / total_samples
#     avg_loss = total_loss / len(test_loader)
#     test_time = time.time() - test_start_time
#
#     print("\nTest Results:")
#     print(f"Accuracy: {accuracy * 100:.2f}%")
#     print(f"Average Loss: {avg_loss:.4f}")
#     print(f"Testing completed in {test_time:.2f} seconds")
#     return accuracy

def test_model(test_data, model, model_path, num_classes, device, batch_size=32, output_file="test_results_llama.json"):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting testing process")

    # Load tokenizer
    print("Loading tokenizer for testing...")
    tokenizer, _, _ = load_tokenizer_and_model(model_path)

    # Prepare test dataset
    print("Preparing test dataset...")
    test_dataset = JsonDataset(test_data, tokenizer)
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        num_workers=4,
        pin_memory=True
    )
    print(f"Created test DataLoader with {len(test_loader)} batches")

    model.eval()
    total_correct = 0
    total_samples = 0
    total_loss = 0
    loss_fn = nn.CrossEntropyLoss().to(device)

    results = []  # 用于存储每个样本的预测结果

    print("Starting evaluation...")
    test_start_time = time.time()

    with torch.no_grad():
        for batch_idx, batch in enumerate(test_loader):
            # Move batch to GPU
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            labels = batch['label'].to(device)

            outputs, _ = model(input_ids, attention_mask=attention_mask)
            loss = loss_fn(outputs, labels)
            total_loss += loss.item()

            predictions = torch.argmax(outputs, dim=1)
            total_correct += (predictions == labels).sum().item()
            total_samples += labels.size(0)

            # 记录每个样本的预测结果
            for i in range(len(input_ids)):
                results.append({
                    "input_text": tokenizer.decode(input_ids[i].tolist(), skip_special_tokens=True),
                    "true_label": labels[i].item(),
                    "predicted_label": predictions[i].item()
                })

            if batch_idx % 10 == 0:
                progress = (batch_idx + 1) / len(test_loader) * 100
                print(f"Testing progress: [{batch_idx}/{len(test_loader)} ({progress:.1f}%)]")

    accuracy = total_correct / total_samples
    avg_loss = total_loss / len(test_loader)
    test_time = time.time() - test_start_time

    print("\nTest Results:")
    print(f"Accuracy: {accuracy * 100:.2f}%")
    print(f"Average Loss: {avg_loss:.4f}")
    print(f"Testing completed in {test_time:.2f} seconds")

    # 保存结果到 JSON 文件
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print(f"Test predictions saved to {output_file}")

    return accuracy



if __name__ == '__main__':
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting script execution")

    # Set up paths
    train_json_file = Path('./src/data/train_probing_data.json')
    test_json_file = Path('./src/data/test_probing_data.json')
    model_path = Path("./Meta_Llama-3.2-3B-Instruct")
    save_path = Path(f'./trained_model_meta_id_{cur_time}.pth')

    # Check files
    print("Checking file paths...")
    if not train_json_file.exists():
        raise FileNotFoundError(f"Training file not found: {train_json_file}")
    if not test_json_file.exists():
        raise FileNotFoundError(f"Test file not found: {test_json_file}")
    print("All required files found")

    # Load data
    print("Loading JSON data...")
    with open(train_json_file, 'r') as f:
        train_data = json.load(f)
    with open(test_json_file, 'r') as f:
        test_data = json.load(f)
    print(f"Loaded {len(train_data)} training samples and {len(test_data)} test samples")

    # Train model
    trained_model, device = train_model(
        train_data,
        str(model_path),
        num_classes=2,
        save_path=str(save_path),
        warmup_steps=50,
        learning_rate=1e-4,
        num_epochs=1
    )

    # Test model
    test_model(
        test_data,
        trained_model,
        str(model_path),
        num_classes=2,
        device=device
    )

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Script execution completed")
