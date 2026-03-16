import transformers
import torch
from PIL import Image
import time

model_name = "nvidia/Cosmos-Reason2-8B"
try:
    # Try importing Qwen3VLForConditionalGeneration directly if possible (transformers update)
    from transformers import Qwen3VLForConditionalGeneration
    force_manual = False
except ImportError:
    force_manual = True

if not force_manual:
    print("Using transformers.Qwen3VLForConditionalGeneration")
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_name, dtype=torch.float16, device_map="auto", attn_implementation="sdpa", trust_remote_code=True
    )
else:
    # If not in transformers, use AutoModel to get module, then instantiate correct class
    print("Qwen3VLForConditionalGeneration not in transformers, trying to find it manually via AutoModel + dynamic import")
    # Load base model to trigger download/cache and module import
    base_model = transformers.AutoModel.from_pretrained(
        model_name, dtype=torch.float16, device_map="auto", attn_implementation="sdpa", trust_remote_code=True
    )
    # Get the module
    module_name = type(base_model).__module__
    import sys
    import importlib
    
    # Reload module or get it
    if module_name in sys.modules:
        mod = sys.modules[module_name]
    else:
        mod = importlib.import_module(module_name)
        
    # Get the class
    if hasattr(mod, "Qwen3VLForConditionalGeneration"):
        params = base_model.config
        # We need to reload using the correct class to get weights properly (including head)
        del base_model
        import gc
        gc.collect()
        torch.cuda.empty_cache()
        
        cls = getattr(mod, "Qwen3VLForConditionalGeneration")
        print(f"Found class: {cls}")
        model = cls.from_pretrained(
             model_name, dtype=torch.float16, device_map="auto", attn_implementation="sdpa", trust_remote_code=True
        )
    else:
        raise ValueError(f"Could not find Qwen3VLForConditionalGeneration in {module_name}")

processor = transformers.AutoProcessor.from_pretrained(model_name, trust_remote_code=True)

# Input setup from run_minicp.py
image1 = Image.open("./i1.jpeg").convert("RGB")
image2 = Image.open("./i2.png").convert("RGB")
image3 = Image.open("./i3.png").convert("RGB")
image5 = Image.open("./i5.png").convert("RGB")

question = """

Rules:
- Extract the name of the screen/monitor screenshot.
- Analyze the content inside the image.
- Do NOT translate Japanese text.
- Preserve all table structures exactly as seen, including row headers and column headers.
- If the screen is a panel, schematic, sensor network, or log table, extract it in Markdown sections.
- If the screen is heat pump pipeline or watter flow, extract the flow values and directions of elements.
- If a table exists, reconstruct it fully in Markdown.
- If switches appear, you must always check their status `ON` or `OFF`.
- If sensor appear, extract their values or identify the color of the sensors.

"""

question = "What information showed in this HMI screen? Please answer in Markdown format following the rules below:\n\n" + question
question = "What information showed in this HMI screen? Extract the information in Markdown format "
for img in [image1, image2, image3, image5]:
    messages = [
        {"role": "user", "content": [
                {"type": "image", "image": img},
                {"type": "text", "text": question},
            ]
        },
    ]

    time_start = time.time()

    # Process inputs
    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)

    # Run inference
    generated_ids = model.generate(**inputs, max_new_tokens=4096)
    generated_ids_trimmed = [
        out_ids[len(in_ids) :]
        for in_ids, out_ids in zip(inputs.input_ids, generated_ids, strict=False)
    ]
    output_text = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )

    print(output_text[0])
    print("time:", time.time() - time_start)
