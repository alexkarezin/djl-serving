import requests
import argparse
import subprocess as sp
import logging
import re
import os
import math
import json
from random import randrange
import numpy as np
from datetime import datetime
from io import BytesIO
import hashlib

logging.basicConfig(level=logging.INFO)
parser = argparse.ArgumentParser(description="Build the LLM configs")
parser.add_argument("handler", help="the handler used in the model")
parser.add_argument("model", help="The name of model")
parser.add_argument("--engine",
                    required=False,
                    type=str,
                    choices=["deepspeed", "huggingface", "fastertransformer"],
                    help="The engine used for inference")
parser.add_argument("--dtype",
                    required=False,
                    type=str,
                    help="The model data type")
parser.add_argument("--tensor_parallel",
                    required=False,
                    type=int,
                    help="The model tensor parallel degree")
parser.add_argument("--batch_size",
                    required=False,
                    type=int,
                    help="The batch size of inference requests")
parser.add_argument("--in_tokens",
                    required=False,
                    type=int,
                    help="The sequence length for input tokens")
parser.add_argument("--out_tokens",
                    required=False,
                    type=int,
                    help="The sequence length for output tokens")
parser.add_argument("--count",
                    required=False,
                    type=int,
                    help="Number of requests sent")
parser.add_argument("--cpu_memory",
                    required=False,
                    default=0,
                    type=int,
                    help="CPU Memory footprint")
args = parser.parse_args()


def compute_model_name_hash(model_name):
    # This mirrors the Utils.hash implementation from DJL Core
    m = hashlib.sha256()
    m.update(model_name)
    return m.hexdigest()[:40]


ds_raw_model_spec = {
    "gpt-j-6b": {
        "max_memory_per_gpu": [6.0, 6.0, 6.0, 6.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128, 256],
        "use_pipeline": True
    },
    "bloom-7b1": {
        "max_memory_per_gpu": [7.0, 7.0, 8.0, 9.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128, 256],
        "use_pipeline": False
    },
    "opt-30b": {
        "max_memory_per_gpu": [16.0, 16.0, 16.0, 16.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128, 256],
        "use_pipeline": False
    }
}

hf_model_spec = {
    "gpt-neo-2.7b": {
        "max_memory_per_gpu": [8.0, 8.0, 9.0, 17.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128, 256],
        "worker": 2
    },
    "gpt-j-6b": {
        "max_memory_per_gpu": [8.0, 9.0, 9.0, 21.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128, 256],
        "worker": 2
    },
    "bloom-7b1": {
        "max_memory_per_gpu": [7.0, 7.0, 8.0, 9.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128]
    },
    "bigscience/bloom-3b": {
        "max_memory_per_gpu": [5.0, 6.0],
        "batch_size": [1, 4],
        "seq_length": [16, 32],
        "worker": 1,
        "stream_output": True,
    },
    "t5-large": {
        "max_memory_per_gpu": [5.0],
        "batch_size": [1],
        "seq_length": [32],
        "worker": 1,
        "stream_output": True,
    },
    "no-code/nomic-ai/gpt4all-j": {
        "max_memory_per_gpu": [10.0, 12.0],
        "batch_size": [1, 4],
        "seq_length": [16, 32],
        "worker": 1,
        "model_name": compute_model_name_hash(b"nomic-ai/gpt4all-j"),
    },
    "no-code/databricks/dolly-v2-7b": {
        "max_memory_per_gpu": [10.0, 12.0],
        "batch_size": [1, 4],
        "seq_length": [16, 32],
        "worker": 2,
        "model_name": compute_model_name_hash(b"databricks/dolly-v2-7b"),
    },
    "no-code/google/flan-t5-xl": {
        "max_memory_per_gpu": [7.0, 7.0],
        "batch_size": [1, 4],
        "seq_length": [16, 32],
        "worker": 2,
        "model_name": compute_model_name_hash(b"google/flan-t5-xl")
    }
}

ds_model_spec = {
    "gpt-j-6b": {
        "max_memory_per_gpu": [9.0, 10.0, 11.0, 12.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128, 256],
        "worker": 2
    },
    "bloom-7b1": {
        "max_memory_per_gpu": [7.0, 8.0, 8.0, 9.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128, 256]
    },
    "opt-13b": {
        "max_memory_per_gpu": [17.0, 18.0, 19.0, 22.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128, 256],
        "worker": 2
    },
    "gpt-neo-1.3b": {
        "max_memory_per_gpu": [4.0, 5.0],
        "batch_size": [1, 4],
        "seq_length": [16],
        "worker": 1,
        "stream_output": True,
    }
}

ft_model_spec = {
    "bigscience/bloom-3b": {
        "batch_size": [1, 2],
        "seq_length": [64, 128],
        "max_memory_per_gpu": [6.0, 6.0, 6.0, 6.0]
    },
    "flan-t5-xxl": {
        "batch_size": [1, 2],
        "seq_length": [64, 128],
        "max_memory_per_gpu": [15.0, 15.0, 15.0, 15.0]
    }
}

ft_raw_model_spec = {
    "t5-small": {
        "batch_size": [1, 2],
        "max_memory_per_gpu": 2
    },
    "gpt2-xl": {
        "batch_size": [1, 2],
        "max_memory_per_gpu": 7.0
    },
    "facebook/opt-6.7b": {
        "batch_size": [1, 2],
        "max_memory_per_gpu": 6.0
    },
    "bigscience/bloom-3b": {
        "batch_size": [1, 2],
        "max_memory_per_gpu": 6.0
    },
    "flan-t5-xxl": {
        "batch_size": [1, 2],
        "max_memory_per_gpu": 15.0
    }
}

sd_model_spec = {
    "stable-diffusion-v1-5": {
        "max_memory_per_gpu": 8.0,
        "size": [256, 512],
        "num_inference_steps": [50, 100]
    },
    "stable-diffusion-2-1-base": {
        "max_memory_per_gpu": 8.0,
        "size": [256, 512],
        "num_inference_steps": [50, 100],
        "workers": 2
    },
    "stable-diffusion-2-depth": {
        "max_memory_per_gpu": 8.0,
        "size": [512],
        "num_inference_steps": [50],
        "depth": True
    },
    "stable-diffusion-2.1-base-neuron": {
        "worker": 2,
        "size": [512],
        "num_inference_steps": [50, 100]
    }
}

ds_aot_model_spec = {
    "opt-6.7b": {
        "max_memory_per_gpu": [12.0, 12.0, 12.0, 12.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128, 256],
        "use_pipeline": True
    },
    "bloom-7b1": {
        "max_memory_per_gpu": [12.0, 12.0, 12.0, 12.0],
        "batch_size": [1, 2, 4, 8],
        "seq_length": [64, 128, 256],
        "use_pipeline": False
    }
}

transformers_neuronx_raw_model_spec = {"gpt2": {"seq_length": [64, 128]}}

transformers_neuronx_model_spec = {
    "gpt2": {
        "worker": 1,
        "seq_length": [128, 256],
        "batch_size": [4]
    },
    "opt-1.3b": {
        "worker": 3,
        "seq_length": [128, 256],
        "batch_size": [4]
    },
    "gpt-j-6b": {
        "worker": 1,
        "seq_length": [128, 256, 512],
        "batch_size": [4]
    },
    "opt-1.3b-streaming": {
        "worker": 3,
        "seq_length": [16, 32],
        "batch_size": [1],
        "stream_output": True,
    },
}


def check_worker_number(desired, model_name="test"):
    endpoint = f"http://127.0.0.1:8080/models/{model_name}"
    res = requests.get(endpoint).json()
    if desired == len(res[0]["models"][0]["workerGroups"]):
        return
    elif desired == len(res[0]["models"][0]["workerGroups"][0]["workers"]):
        return
    else:
        raise AssertionError(
            f"Worker number does not meet requirements! {res}")


def send_json(data, model_name="test"):
    headers = {'content-type': 'application/json'}
    endpoint = f"http://127.0.0.1:8080/predictions/{model_name}"
    resp = requests.post(endpoint, headers=headers, json=data)

    if resp.status_code >= 300:
        logging.exception(f"HTTP error: {resp}")
        raise ValueError("Failed to send reqeust to model server")
    return resp


def send_image_json(img_url, data, model_name="test"):
    multipart_form_data = {
        'data': BytesIO(requests.get(img_url, stream=True).content),
        'json': (None, json.dumps(data), 'application/json')
    }
    endpoint = f"http://127.0.0.1:8080/predictions/{model_name}"
    resp = requests.post(endpoint, files=multipart_form_data)

    if resp.status_code >= 300:
        logging.exception(f"HTTP error: {resp}")
        raise ValueError("Failed to send reqeust to model server")
    return resp


def get_gpu_memory():
    command = "nvidia-smi --query-gpu=memory.used --format=csv"
    memory_free_info = sp.check_output(
        command.split()).decode('ascii').split('\n')[:-1][1:]
    return [int(x.split()[0]) for i, x in enumerate(memory_free_info)]


def fake_tokenizer(prompt, in_tokens):
    tokenized = re.findall(r"[\w']+|[.,!?;]", prompt)
    index_pointer = 0
    token_count = 0
    for token in tokenized:
        target = token[-1]
        index_pointer = prompt.find(target, index_pointer) + 1
        token_count += 1
        if token_count == in_tokens:
            break
    return prompt[:index_pointer]


def prompt_generation(in_tokens):
    with open(os.path.join(os.getcwd(), 'prompts.txt')) as f:
        result = '\n'.join(f.readlines())
    rot = result.find('. ', randrange(len(result))) + 2
    result = result[rot:] + result[:rot]

    return fake_tokenizer(result, in_tokens)


def batch_generation(batch_size):
    if args.in_tokens:
        input_sentences = [
            prompt_generation(args.in_tokens),
            prompt_generation(args.in_tokens),
            prompt_generation(args.in_tokens),
            prompt_generation(args.in_tokens),
            prompt_generation(args.in_tokens),
            prompt_generation(args.in_tokens),
            prompt_generation(args.in_tokens),
            prompt_generation(args.in_tokens)
        ]
    else:
        input_sentences = [
            "DeepSpeed is a machine learning framework",
            "He is working on",
            "He has a",
            "He got all",
            "Everyone is happy and I can",
            "The new movie that got Oscar this year",
            "In the far far distance from our galaxy,",
            "Peace is the only way",
        ]
    if batch_size > len(input_sentences):
        # dynamically extend to support larger bs by repetition
        input_sentences *= math.ceil(batch_size / len(input_sentences))
    return input_sentences[:batch_size]


def t5_batch_generation(batch_size):
    input_sentences = [
        "translate English to German: The house is wonderful.",
        "summarize: state authorities dispatched emergency crews tuesday to survey the damage after an onslaught \
             of severe weather in mississippi…",
    ]
    if batch_size > len(input_sentences):
        input_sentences *= math.ceil(batch_size / len(input_sentences))
    return input_sentences[:batch_size]


def get_total_memory(memory_snapshot):
    memory_footprint = 0
    for memory in memory_snapshot:
        memory_footprint += float(memory)
    return memory_footprint


def build_metric_label():
    sanitized_model_name = args.model.split("/")[-1]
    dtype = f"{args.dtype}"
    tp = f"tp-{args.tensor_parallel}" if args.tensor_parallel else ""
    batch_size = f"batch-{args.batch_size}" if args.batch_size else ""
    in_tokens = f"{args.in_tokens}-in-tokens" if args.in_tokens else ""
    out_tokens = f"{args.out_tokens}-out-tokens" if args.out_tokens else ""
    output = [
        sanitized_model_name, dtype, tp, batch_size, in_tokens, out_tokens
    ]
    while "" in output:
        output.remove("")
    return "_".join(output)


def log_metrics(response_times):
    required_args = ["batch_size", "out_tokens"]
    for arg in required_args:
        if arg not in args:
            raise ValueError(
                f"Logging metrics requires the following arguments: {required_args}"
            )

    p50 = np.percentile(response_times, 50)
    p90 = np.percentile(response_times, 90)
    p99 = np.percentile(response_times, 99)
    throughput = 1000 / (sum(response_times) / len(response_times))
    tps = throughput * args.out_tokens * args.batch_size
    max_memory = get_total_memory(get_gpu_memory())

    outputs = []
    metric_stem = build_metric_label()
    outputs.append({
        "MetricName": f"{metric_stem}_p50",
        "Unit": "Milliseconds",
        "Value": p50
    })
    outputs.append({
        "MetricName": f"{metric_stem}_p90",
        "Unit": "Milliseconds",
        "Value": p90
    })
    outputs.append({
        "MetricName": f"{metric_stem}_p99",
        "Unit": "Milliseconds",
        "Value": p99
    })
    outputs.append({
        "MetricName": f"{metric_stem}_throughput",
        "Unit": "Count/Second",
        "Value": throughput
    })
    outputs.append({
        "MetricName": f"{metric_stem}_tokens-per-second",
        "Unit": "Count/Second",
        "Value": tps
    })
    outputs.append({
        "MetricName": f"{metric_stem}_gpu-memory",
        "Unit": "Megabytes",
        "Value": max_memory
    })
    if args.cpu_memory > 0:
        outputs.append({
            "MetricName": f"{metric_stem}_cpu-memory",
            "Unit": "Kilobytes",
            "Value": args.cpu_memory
        })
    with open("llm/metrics.log", "w") as f:
        f.write(str(outputs))
        f.close()


def test_handler(model, model_spec):
    if model not in model_spec:
        raise ValueError(
            f"{args.model} is not one of the supporting models {list(model_spec.keys())}"
        )
    spec = model_spec[args.model]
    if "worker" in spec:
        check_worker_number(spec["worker"],
                            model_name=spec.get("model_name", "test"))
    for i, batch_size in enumerate(spec["batch_size"]):
        for seq_length in spec["seq_length"]:
            if "t5" in model:
                req = {"inputs": t5_batch_generation(batch_size)}
            else:
                req = {"inputs": batch_generation(batch_size)}
            params = {"max_new_tokens": seq_length}
            req["parameters"] = params
            logging.info(f"req {req}")
            res = send_json(req, model_name=spec.get("model_name", "test"))
            if spec.get("stream_output", False):
                logging.info(f"res: {res.content}")
                result = res.content.decode().split("\n")[:-1]
                assert len(
                    result
                ) <= seq_length, "generated more takens than max_new_tokens"
                result_0 = json.loads(result[0])['outputs']
                assert len(
                    result_0
                ) == batch_size, "batch size number of tokens are not generated"
            else:
                res = res.json()
                logging.info(f"res {res}")

                result = [item['generated_text'] for item in res]
                assert len(result) == batch_size
            memory_usage = get_gpu_memory()
            logging.info(memory_usage)
            for memory in memory_usage:
                assert float(memory) / 1024.0 < spec["max_memory_per_gpu"][i]


def test_ds_raw_model(model, model_spec):
    if model not in model_spec:
        raise ValueError(
            f"{args.model} is not one of the supporting models {list(model_spec.keys())}"
        )
    spec = model_spec[args.model]
    for i, batch_size in enumerate(spec["batch_size"]):
        for seq_length in spec["seq_length"]:
            req = {
                "batch_size": batch_size,
                "text_length": seq_length,
                "use_pipeline": spec["use_pipeline"]
            }
            logging.info(f"req: {req}")
            res = send_json(req)
            res = res.json()
            logging.info(f"res: {res}")
            assert len(res["outputs"]) == batch_size
            memory_usage = get_gpu_memory()
            logging.info(memory_usage)
            for memory in memory_usage:
                assert float(memory) / 1024.0 < spec["max_memory_per_gpu"][i]


def test_performance():
    response_times = []
    for i in range(args.count):
        req = {"inputs": batch_generation(args.batch_size)}
        params = {"max_new_tokens": args.out_tokens}
        req["parameters"] = params
        logging.info(f"req: {req}")
        start = datetime.now()
        res = send_json(req)
        delta = (datetime.now() - start).total_seconds() * 1000
        response_times.append(delta)
        res = res.json()
        logging.info(f"res: {res}")
    log_metrics(response_times)


def test_sd_handler(model, model_spec):
    from PIL import Image

    if model not in model_spec:
        raise ValueError(
            f"{model} is not one of the supporting models {list(sd_model_spec.keys())}"
        )
    spec = sd_model_spec[model]
    if "worker" in spec:
        check_worker_number(spec["worker"])
    for size in spec["size"]:
        for step in spec["num_inference_steps"]:
            if "depth" in spec:
                req = {"prompt": "two tigers"}
                params = {
                    "negative_prompt": "bad, deformed, ugly, bad anotomy",
                    "strength": 0.7
                }
                url = "http://images.cocodataset.org/val2017/000000039769.jpg"
                req["parameters"] = params
                logging.info(f"req: {req}")
                res = send_image_json(url, req)
            else:
                req = {"prompt": "A bird and cat flying through space"}
                params = {
                    "height": size,
                    "width": size,
                    "num_inference_steps": step
                }
                req["parameters"] = params
                logging.info(f"req: {req}")
                res = send_json(req)
            try:
                Image.open(BytesIO(res.content)).convert("RGB")
            except Exception as e:
                raise IOError("failed to deserialize image from response", e)
            if "max_memory_per_gpu" in spec:
                memory_usage = get_gpu_memory()
                logging.info(memory_usage)
                for memory in memory_usage:
                    assert float(memory) / 1024.0 < spec["max_memory_per_gpu"]


def test_ft_handler(model, model_spec):
    if model not in model_spec:
        raise ValueError(
            f"{model} is not one of the supporting models {list(ft_raw_model_spec.keys())}"
        )
    spec = model_spec[model]
    for batch_size in spec['batch_size']:
        logging.info(
            f"testing ft_handler with model: {model}, batch_size: {batch_size} "
        )
        if "t5" in model:
            req = {"inputs": t5_batch_generation(batch_size)}
        else:
            req = {"inputs": batch_generation(batch_size)}
        res = send_json(req)
        res = res.json()
        logging.info(res)
        assert len(res) == batch_size
        memory_usage = get_gpu_memory()
        logging.info(memory_usage)
        for memory in memory_usage:
            assert float(memory) / 1024.0 < spec["max_memory_per_gpu"]


def test_transformers_neuronx_raw(model, model_spec):
    if model not in model_spec:
        raise ValueError(
            f"{model} is not one of the supporting models {list(model_spec.keys())}"
        )
    spec = model_spec[model]
    for seq_length in spec["seq_length"]:
        print(
            f"testing transformers_neuronx_handler with model: {model}, seq_length: {seq_length} "
        )
        text = "Hello, I'm a language model,"
        compiled_batch_size = 4
        req = {
            "seq_length": seq_length,
            "text": text,
        }
        res = send_json(req)
        res = res.json()
        logging.info(res)
        assert len(res["outputs"]) == compiled_batch_size
        assert all([text in t for t in res["outputs"]])


def test_transformers_neuronx_handler(model, model_spec):
    if model not in model_spec:
        raise ValueError(
            f"{args.model} is not one of the supporting models {list(model_spec.keys())}"
        )
    spec = model_spec[args.model]
    if "worker" in spec:
        check_worker_number(spec["worker"])
    for batch_size in spec["batch_size"]:
        for seq_length in spec["seq_length"]:
            req = {"inputs": batch_generation(batch_size)}
            params = {"max_length": seq_length}
            req["parameters"] = params
            logging.info(f"req {req}")
            res = send_json(req)
            if spec.get("stream_output", False):
                logging.info(f"res: {res.content}")
                result = res.content.decode().split("\n")[:-1]
                assert len(
                    result
                ) <= seq_length, "generated more takens than max_new_tokens"
            else:
                res = res.json()
                logging.info(f"res {res}")
                result = res
                assert len(result) == batch_size


if __name__ == "__main__":
    if args.handler == "deepspeed_raw":
        test_ds_raw_model(args.model, ds_raw_model_spec)
    elif args.handler == "huggingface":
        test_handler(args.model, hf_model_spec)
    elif args.handler == "deepspeed":
        test_handler(args.model, ds_model_spec)
    elif args.handler == "stable-diffusion":
        test_sd_handler(args.model, sd_model_spec)
    elif args.handler == "fastertransformer":
        test_handler(args.model, ft_model_spec)
    elif args.handler == "fastertransformer_raw":
        test_ft_handler(args.model, ft_raw_model_spec)
    elif args.handler == "deepspeed_aot":
        test_ds_raw_model(args.model, ds_aot_model_spec)
    elif args.handler == "deepspeed_handler_aot":
        test_handler(args.model, ds_aot_model_spec)
    elif args.handler == "transformers_neuronx":
        test_transformers_neuronx_handler(args.model,
                                          transformers_neuronx_model_spec)
    elif args.handler == "transformers_neuronx_raw":
        test_transformers_neuronx_raw(args.model,
                                      transformers_neuronx_raw_model_spec)
    elif args.handler == "performance":
        test_performance()
    else:
        raise ValueError(
            f"{args.handler} is not one of the supporting handler")
