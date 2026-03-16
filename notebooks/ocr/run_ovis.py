#!/usr/bin/env python3
"""
Inference script for AIDC-AI/Ovis2.6-30B-A3B with a targeted patch
to avoid "Cannot copy out of meta tensor; no data!" by overriding the
actual embeddings module used at runtime.
Adjust image_path and question as needed.
"""

import time
import types
from typing import Optional

from PIL import Image
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoModelForCausalLM

# -------------------------
# User config
# -------------------------
# Select one local image
# image_path = "./i1.jpeg"
# image_path = "./i2.png"
# image_path = "./i3.png"
image_path = "./i4.png"

enable_thinking = True
enable_thinking_budget = True

max_new_tokens = 2048
thinking_budget = 1024

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

# -------------------------
# Safe embeddings forward (targeted fix)
# -------------------------
def _safe_embeddings_forward(self, pixel_values: torch.FloatTensor, grid_thws: Optional[torch.LongTensor] = None) -> torch.Tensor:
    """
    Replacement forward for the Siglip2VisionEmbeddings-like module.
    Ensures no assignment between meta tensors and real tensors.
    """
    # Determine dtype/device
    try:
        target_dtype = self.patch_embedding.weight.dtype
        target_device = self.patch_embedding.weight.device
    except Exception:
        target_dtype = pixel_values.dtype if pixel_values is not None else torch.float32
        target_device = pixel_values.device if pixel_values is not None else torch.device("cpu")

    # Patch embeddings
    if isinstance(self.patch_embedding, nn.Linear):
        patch_embeds = self.patch_embedding(pixel_values.to(dtype=target_dtype, device=target_device))
    elif isinstance(self.patch_embedding, nn.Conv2d):
        pixel_values = pixel_values.view(
            -1,
            self.config.num_channels * getattr(self.config, "temporal_patch_size", 1),
            self.patch_size,
            self.patch_size,
        )
        patch_embeds = self.patch_embedding(pixel_values.to(dtype=target_dtype, device=target_device))
        patch_embeds = patch_embeds.reshape(-1, self.embed_dim)
    else:
        raise RuntimeError("Unsupported patch_embedding type in patched forward")

    # Reconstruct positional embeddings safely if required
    if getattr(self, "preserve_original_pe", False):
        assert grid_thws is not None, "grid_thws is required when preserve_original_pe is True"

        pos_embed_new = torch.zeros_like(patch_embeds, device=patch_embeds.device, dtype=patch_embeds.dtype)

        ori_h = ori_w = getattr(self, "position_embedding_size", None)
        if ori_h is None:
            num_emb = getattr(self.position_embedding, "num_embeddings", None)
            if num_emb is not None:
                side = int(num_emb ** 0.5)
                ori_h = ori_w = side
            else:
                ori_h = ori_w = 1

        positional_embeddings = (
            self.position_embedding.weight.reshape(ori_h, ori_w, -1)
            .unsqueeze(0)
            .permute(0, 3, 1, 2)
            .to(device=patch_embeds.device, dtype=patch_embeds.dtype)
        )

        cnt = 0
        if isinstance(grid_thws, torch.Tensor):
            grid_iter = grid_thws.tolist()
        else:
            grid_iter = list(grid_thws)

        hidden_stride = getattr(self, "hidden_stride", 1)

        for triple in grid_iter:
            t, h, w = map(int, triple)
            thw = t * h * w

            pe = F.interpolate(positional_embeddings, size=(h, w), mode="bicubic", align_corners=False)
            pe = pe.permute(0, 2, 3, 1).reshape(1, h * w, -1)
            pe = pe[0].repeat(t, 1)
            pe = pe.reshape(t, h // hidden_stride, hidden_stride, w // hidden_stride, hidden_stride, -1)
            pe = pe.permute(0, 1, 3, 2, 4, 5).reshape(thw, -1)

            # Materialize pe on real device/dtype if it's meta
            if pe.device.type == "meta":
                pe = torch.zeros((thw, pos_embed_new.shape[-1]), device=pos_embed_new.device, dtype=pos_embed_new.dtype)
            else:
                pe = pe.to(device=pos_embed_new.device, dtype=pos_embed_new.dtype)

            pos_embed_new[cnt:cnt + thw] = pe
            cnt += thw

        if pos_embed_new.shape == patch_embeds.shape:
            patch_embeds = patch_embeds + pos_embed_new

    return patch_embeds

# -------------------------
# Load model
# -------------------------
model = AutoModelForCausalLM.from_pretrained(
    "AIDC-AI/Ovis2.6-30B-A3B",
    torch_dtype=torch.bfloat16,
    trust_remote_code=True,
    device_map="auto",
)

# -------------------------
# Patch the exact embeddings module found in your logs
# -------------------------
# This is the module name you reported: visual_tokenizer.vit.vision_model.embeddings
try:
    target = model.visual_tokenizer.vit.vision_model.embeddings
    target.forward = types.MethodType(_safe_embeddings_forward, target)
    print("Patched target:", "visual_tokenizer.vit.vision_model.embeddings")
except Exception as exc:
    # If this fails, print available modules that have patch_embedding for debugging
    print("Failed to patch target directly:", repr(exc))
    print("Listing modules with 'patch_embedding' attribute:")
    for name, module in model.named_modules():
        if hasattr(module, "patch_embedding"):
            print(" -", name, type(module))

# -------------------------
# Prepare messages with user's image and question
# -------------------------
image = Image.open(image_path).convert("RGB")

messages = [
    {
        "role": "user",
        "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": question},
        ],
    }
]

# -------------------------
# Preprocess inputs and move to device
# -------------------------
input_ids, pixel_values, grid_thws = model.preprocess_inputs(
    messages=messages,
    add_generation_prompt=True,
    enable_thinking=enable_thinking,
)

if torch.cuda.is_available():
    input_ids = input_ids.cuda()
    pixel_values = pixel_values.cuda() if pixel_values is not None else None
    grid_thws = grid_thws.cuda() if grid_thws is not None else None

# -------------------------
# Generate and decode
# -------------------------
time_start = time.time()
try:
    outputs = model.generate(
        inputs=input_ids,
        pixel_values=pixel_values,
        grid_thws=grid_thws,
        enable_thinking=enable_thinking,
        enable_thinking_budget=enable_thinking_budget,
        max_new_tokens=max_new_tokens,
        thinking_budget=thinking_budget,
    )
    response = model.text_tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(response)
except Exception as e:
    print("Generation failed with exception:", repr(e))
print("time:", time.time() - time_start)