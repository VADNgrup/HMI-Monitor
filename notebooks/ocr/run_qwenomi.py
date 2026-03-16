import time
import torch
import soundfile as sf
import os
from PIL import Image

# Import provided utilities - check your path
try:
    from transformers import Qwen3OmniMoeForConditionalGeneration, Qwen3OmniMoeProcessor
    from qwen_omni_utils import process_mm_info
except ImportError as e:
    print(f"Import Error: {e}")
    print("Please ensure transformers, torch, soundfile, and qwen_omni_utils are available.")
    # Exit if critical imports fail
    # exit(1)

# Configuration
MODEL_PATH = "Qwen/Qwen3-Omni-30B-A3B-Instruct"
# IMAGE_PATH = "./i4.png"
IMAGE_PATH = "/home/ducanh/IPU/ocr/i4.png" # Recommend absolute path

def main():
    print(f"Loading model from {MODEL_PATH}...")
    try:
        model = Qwen3OmniMoeForConditionalGeneration.from_pretrained(
            MODEL_PATH,
            dtype="auto",
            device_map="auto",
            attn_implementation="flash_attention_2",
        )

        processor = Qwen3OmniMoeProcessor.from_pretrained(MODEL_PATH)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Failed to load model: {e}")
        return

    # Prepare Image
    if not os.path.exists(IMAGE_PATH):
        print(f"Warning: Image file {IMAGE_PATH} not found. Please check path.")
        return

    # Define the OCR Prompt
    ocr_prompt = """
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

    # Construct Conversation
    conversation = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": IMAGE_PATH},
                {"type": "text", "text": ocr_prompt}
            ],
        },
    ]

    # Set whether to use audio in video
    USE_AUDIO_IN_VIDEO = False

    print("Processing inputs...")
    time_start = time.time()

    try:
        # Preparation for inference
        text_input = processor.apply_chat_template(conversation, add_generation_prompt=True, tokenize=False)
        audios, images, videos = process_mm_info(conversation, use_audio_in_video=USE_AUDIO_IN_VIDEO)
        
        inputs = processor(
            text=text_input, 
            audio=audios, 
            images=images, 
            videos=videos, 
            return_tensors="pt", 
            padding=True, 
            use_audio_in_video=USE_AUDIO_IN_VIDEO
        )
        
        inputs = inputs.to(model.device).to(model.dtype)

        print("Generating response...")
        # Inference
        text_ids, audio_out = model.generate(
            **inputs, 
            speaker="Ethan", 
            thinker_return_dict_in_generate=True,
            use_audio_in_video=USE_AUDIO_IN_VIDEO,
            max_new_tokens=2048
        )

        generated_text = processor.batch_decode(
            text_ids.sequences[:, inputs["input_ids"].shape[1] :],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False
        )

        elapsed_time = time.time() - time_start
        
        print("\n" + "="*50)
        print("OCR Result:")
        print("="*50)
        # Handle batch output
        if isinstance(generated_text, list) and len(generated_text) > 0:
            print(generated_text[0])
        else:
            print(generated_text)
        print("="*50)
        print(f"Time taken: {elapsed_time:.4f} seconds")

        if audio_out is not None:
             sf.write(
                "output_ocr.wav",
                audio_out.reshape(-1).detach().cpu().numpy(),
                samplerate=24000,
            )
             print("Audio response saved to ./output_ocr.wav")

    except Exception as e:
        print(f"Error during inference: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
