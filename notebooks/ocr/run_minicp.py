import torch
from PIL import Image
from transformers import AutoModel
import time
model = AutoModel.from_pretrained(
    "openbmb/MiniCPM-o-4_5",
    trust_remote_code=True,
    attn_implementation="sdpa",  # or "flash_attention_2"
    torch_dtype=torch.bfloat16,
    init_vision=True,
    init_audio=False,
    init_tts=False,
)
model.eval().cuda()

image1 = Image.open("./i1.jpeg").convert("RGB")
image2 = Image.open("./i2.png").convert("RGB")
image3 = Image.open("./i3.png").convert("RGB")
image5 = Image.open("./i5.png").convert("RGB")
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
for img in [image1, image2, image3, image5]:
    msgs = [{"role": "user", "content": [img, question]}]
    time_start = time.time()
    res = model.chat(msgs=msgs, use_tts_template=False, enable_thinking=enable_thinking, stream=stream)
    enable_thinking=False # If `enable_thinking=True`, the thinking mode is enabled.
    stream=False # If `stream=True`, return string generator
    
    print(res)
    print("time:", time.time() - time_start)




