from transformers import AutoModelForCausalLM, AutoTokenizer, AutoProcessor
import torch
from PIL import Image
import time

print("Starting checks...")
if torch.cuda.is_available():
    print(f"CUDA is available. Device count: {torch.cuda.device_count()}")
else:
    print("CUDA is NOT available.")

model_path = 'Nanbeige/Nanbeige4.1-3B'

print(f"Loading processor/tokenizer for {model_path}...")
try:
    processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
    print("Processor loaded successfully.")
except Exception as e:
    print(f"Processor load failed: {e}. Falling back to tokenizer only.")
    processor = None
    tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=False, trust_remote_code=True)
    print("Tokenizer loaded.")

print(f"Loading model {model_path}...")
model = AutoModelForCausalLM.from_pretrained(
  model_path,
  torch_dtype='auto',
  device_map='auto',
  trust_remote_code=True
)
print("Model loaded.")

# Inputs from run_kimi.py
# image = Image.open("./i1.jpeg").convert("RGB")
# image = Image.open("./i2.png").convert("RGB")
image = Image.open("./i3.png").convert("RGB")
# image = Image.open("./i4.png").convert("RGB")

question = """
You are an HMI Panel OCR and Visual Understanding AI.

Rules:
- Ignore all browser metadata, tab titles, URLs, or any text outside the actual image.
- Only analyze the content inside the image.
- Do NOT translate Japanese text.
- Output MUST be clean Markdown only.
- Preserve all table structures exactly as seen, including row headers and column headers.
- If the screen is a panel, schematic, sensor network, or log table, extract it in Markdown sections.
- If a table exists, reconstruct it fully in Markdown.
- If switches or states appear, infer `ON` or `OFF` (only one state can be inferred per switch, if visually clear).
- If sensor values are shown, extract their values or identify the color of the sensors. 
- If something is unclear, write UNKNOWN.

Markdown structure (use only the sections that appear in the image):

# [Screen Title]

## [Section Title]
(Use bullet points for values)

## [Tables]
(Reconstruct all tables exactly in Markdown)

## [Notes]
(Any additional text)

"""

if image and processor:
    print("Running with Processor (VLM mode)...")
    messages = [
        {"role": "user", "content": [{"type": "image", "image": image}, 
        {"type": "text", "text": question}]}
    ]
    
    time_start = time.time()
    try:
        # text must be string for processor if we use processor logic for VLM
        text = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        inputs = processor(text=text, images=image, return_tensors="pt", padding=True, truncation=True)
        inputs = inputs.to(model.device)
        
        # Check if pixel_values exists, if not, maybe processor ignored image (text-only model)
        if 'pixel_values' not in inputs:
             print("Warning: Processor did not return pixel_values. Treating as text-only model.")
        
        print("Generating response...")
        generated_ids = model.generate(**inputs, max_new_tokens=2048) # reduced from 8096 for speed/memory safety
        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        response = processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        print(response)
        print("time:", time.time() - time_start)
    except TypeError as e:
        print(f"TypeError during VLM inference: {e}")
        if "pixel_values" in str(e) or "images" in str(e):
             print("Retrying generation without image inputs (text-only fallback)...")
             # Remove image inputs and retry
             if 'pixel_values' in inputs:
                 del inputs['pixel_values']
             if 'image_sizes' in inputs: # for some VLMs
                 del inputs['image_sizes']
                 
             try:
                 generated_ids = model.generate(**inputs, max_new_tokens=2048)
                 generated_ids_trimmed = [
                    out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
                 ]
                 response = processor.batch_decode(
                    generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
                 )[0]
                 print(response)
                 print("time:", time.time() - time_start)
             except Exception as e2:
                 print(f"Fallback generation also failed: {e2}")
        else:
             print("Unknown error, possibly model/processor mismatch.")
    except Exception as e:
        print(f"Error during VLM inference with processor: {e}")
        
elif image and not processor:
    print("Warning: Processor not available, cannot process image directly with this model using standard VLM API.")
    # Attempt text-only fallback if user just wants to see model work
    print("Attempting text-only query (image ignored)...")
    messages = [
        {'role': 'user', 'content': question + "\n(Note: Image content analysis requested but model may be text-only)"}
    ]
    prompt = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=False
    )
    input_ids = tokenizer(prompt, add_special_tokens=False, return_tensors='pt').input_ids
    input_ids = input_ids.to(model.device)
    
    print("Generating text-only response...")
    time_start = time.time()
    try:
        output_ids = model.generate(input_ids, max_new_tokens=512, eos_token_id=tokenizer.eos_token_id)
        resp = tokenizer.decode(output_ids[0][len(input_ids[0]):], skip_special_tokens=True)
        print(resp)
        print("time:", time.time() - time_start)
    except Exception as e:
         print(f"Error during text inference: {e}")

else:
    print("No image loaded or other setup issue.")
