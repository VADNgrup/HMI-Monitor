from transformers import AutoProcessor
from vllm import LLM, SamplingParams

import requests
import time
from PIL import Image


def extract_thinking_and_summary(text: str, bot: str = "◁think▷", eot: str = "◁/think▷") -> str:
    # Handle cases where thinking tags are missing or malformed gracefully
    if bot in text and eot in text:
        try:
             start = text.index(bot) + len(bot)
             end = text.index(eot)
             return text[start:end].strip(), text[end + len(eot) :].strip()
        except ValueError:
             pass
    return "", text

OUTPUT_FORMAT = "--------Thinking--------\n{thinking}\n\n--------Summary--------\n{summary}"

def main():
    model_path = "moonshotai/Kimi-VL-A3B-Thinking-2506"
    llm = LLM(
        model_path,
        trust_remote_code=True,
        max_num_seqs=8,
        max_model_len=131072, # Increased for larger context if needed
        limit_mm_per_prompt={"image": 1},
    )

    processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)

    sampling_params = SamplingParams(max_tokens=32768, temperature=0.8)

    # Image loading logic from run_kimi.py
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
        {"role": "user", "content": [{"type": "image", "image": ""}, {"type": "text", "text": question}]}
    ]

    time_start = time.time()
    # Use tokenize=False to get the raw prompt string for vllm
    text = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)

    outputs = llm.generate([{"prompt": text, "multi_modal_data": {"image": image}}], sampling_params=sampling_params)
    generated_text = outputs[0].outputs[0].text

    thinking, summary = extract_thinking_and_summary(generated_text)
    print(OUTPUT_FORMAT.format(thinking=thinking, summary=summary))
    print("time:", time.time() - time_start)

if __name__ == "__main__":
    main()
