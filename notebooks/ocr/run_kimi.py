from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

model_path = "moonshotai/Kimi-VL-A3B-Instruct"
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    torch_dtype="auto",
    device_map="auto",
    trust_remote_code=True,
)
processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)

# image = Image.open("./i1.jpeg").convert("RGB")
image = Image.open("./i2.png").convert("RGB")
# image = Image.open("./i3.png").convert("RGB")
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
- If switches or states appear, infer `ON` or `OFF` based on the red point.
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

messages = [
    {"role": "user", "content": [{"type": "image", "image": image}, 
    {"type": "text", "text": question}]}
]
import time 
time_start = time.time()
text = processor.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
inputs = processor(images=image, text=text, return_tensors="pt", padding=True, truncation=True).to(model.device)
generated_ids = model.generate(**inputs, max_new_tokens=8096)
generated_ids_trimmed = [
    out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
]
response = processor.batch_decode(
    generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
)[0]
print(response)
print("time:", time.time() - time_start)
