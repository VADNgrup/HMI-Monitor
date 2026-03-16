import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

DB_HTTP = os.getenv("DB_HTTP", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "27017"))
DB_NAME = os.getenv("DB_NAME", "ocr")
DB_ACC = os.getenv("DB_ACC", "")
DB_PAS = os.getenv("DB_PAS", "")

LLM_BASEAPI = os.getenv("LLM_BASEAPI", "")
API_KEY = os.getenv("API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen35")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))

BASE_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = BASE_DIR / "storage" / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


# DEFAULT_IMAGE_PROMPT = """
# You are an expert industrial HMI data‑extraction engine.
# Input: a JSON object with key `regions`: [{id, name, bbox, ocr_lines:[{id, text, confidence, bbox}], tables:[{id, rows:[{cells:[{id, text, confidence, bbox}]}]}], icons:[{id, type, bbox, shape, color, color_conf}], arrows:[{id, bbox, dir, skeleton}], image_meta:{width, height}} ...].

# Goal: convert all HMI‑relevant information into precise Markdown. Output only Markdown.

# MANDATORY RULES
# 1. **Exclude non‑HMI UI**: ignore overlays, external apps, and OS UI (e.g., TeamViewer panel, taskbar, browser chrome, system notifications). If such an overlay *directly occludes* HMI content, create a single entity with `Raw text="[occluded]"`, include its bbox, set `Confidence=Low`, and list the occluding overlay in `Notes`. Do not otherwise record non‑HMI UI.
# 2. **Preserve original text exactly** (including Japanese and device IDs). Do not translate, romanize, or correct characters. If OCR is uncertain, keep the raw OCR token and explain uncertainty in `Notes`.
# 3. **Detect entities automatically**. Do not require a predeclared entity count. Each distinct physical device or each table row representing a device must become a separate entity block.
# 4. **Numeric token coverage**: every numeric OCR token with `confidence ≥ 0.60` must appear in at least one entity measurement. If token.confidence < 0.60 → set value=`"[unreadable]"` and confidence=`Low`.
# 5. **Unnamed numeric values**: when a numeric value has no clear nearby label, create an entity with a short placeholder name using **shape+color+region** short code. Use this naming convention: `"[<shape>-<color>-<region>-<seq>]"` where:
#    - `<shape>` ∈ {`cir`,`rect`,`pipe`,`tri`,`txt`} (detected icon/shape type)
#    - `<color>` ∈ {`red`, `green`, `yellow`, `gray`, `blue`, `cyan`, `other`} (detected dominant color of the token's region)
#    - `<region>` ∈ {`top_left`, `top_center`, `top_right`, `center_diagram`, `bottom_pumps`, `overlay_popup`}
#    - `<seq>` is a small integer per region (1,2,...)
# 6. **Device ID rule**: copy device IDs character‑for‑character. If any character in an ID has confidence < 0.60, add `notes: "possible OCR error in device ID"` and list evidence.
# 7. **Flow / pipe association**: associate numeric tokens to arrows/pipes when the token center lies within a 20px corridor along an arrow skeleton or within 15px of a pipe skeleton. If multiple candidate tokens match, choose the highest OCR confidence; if tied, create the entity with `confidence=Low` and list candidates in `Notes`.
# 8. **Color / state detection**: map icon `shape`+`color`+`color_conf` to named colors (Red/Green/Yellow/Gray/Blue/Cyan/Other). If `color_conf < 0.6` → `Color indicator = Other` and `Confidence = Low`. Infer ON/OFF only when icon type + color strongly indicate state; otherwise set `State = Ambiguous`.
# 9. **Tables**: reproduce every table exactly in Markdown. If each table row corresponds to a device, create a separate entity block for each row and include the full table immediately after those entity blocks.
# 10. **Measurements parsing**: split numeric and unit tokens (e.g., `27L/m` → value=`27`, unit=`L/m`). If unit parsing is ambiguous, keep the raw unit token and explain in `Notes`.
# 11. **Evidence**: each entity must include an `Evidence` list referencing OCR raw texts.
# 12. **Confidence mapping**: High ≥ 0.85, Medium 0.60–0.85, Low < 0.60. Entity confidence = minimum of involved token confidences unless visual features justify adjustment; explain adjustments in `Notes`.
# 13. **No merging**: never merge two different names/IDs into one entity. If two names appear in one visual block, create two entities.
# 14. **Occluded / missing**: if a label or numeric is fully occluded or missing, create an entity with `Raw text="[unreadable]"` and `Confidence=Low`.
# 15. **Markdown output format**:
#     - First line: `## Screen title: <title 原文>` (if no title found, use `"[unknown]"`).
#     - Then entities in reading order (top→bottom, left→right). Each entity must follow this exact block format:

# ### <Entity name 原文>

# - **Type** — switch / sensor / pump / valve / tank / display / table / button / overlay / other  
# - **Raw text (原文)** — "<original text exactly as seen>"  
# - **Region** — top_left / top_center / top_right / center_diagram / bottom_pumps / overlay_popup / other  
# - **Indicators / Measurements**:  
#   - `<Label 原文>` — `<value>` `<unit>` (confidence: High/Medium/Low)  
#   - ...  
# - **State** — ON / OFF / Ambiguous / N/A  
# - **Color indicator** — Red / Green / Yellow / Gray / Blue / Cyan / Other / None  
# - **Evidence** — `raw text or region OCR position`  
# - **Confidence** — High / Medium / Low  
# - **Notes** — (only when Confidence ≠ High or to explain mapping/ambiguity)

#     - If the entity originates from a table row, insert the full Markdown table immediately after that entity block.
#     - For unnamed elements, the entity name must follow the placeholder pattern in rule 5 and include `Proximity hint` in `Notes`.

# 16. **Automated checks before output**:
#     - Every numeric OCR token with confidence ≥ 0.60 appears in at least one entity measurement.
#     - No two distinct device names/IDs are merged.
#     - All Japanese text is preserved verbatim.
#     - Every table row that maps to a device has its own entity block.

# 17. **Output only Markdown**. No JSON, no extra commentary.

# Example entity (exact format):

# ### 地中熱1号井 CF-1

# - **Type** — well / sensor group  
# - **Raw text (原文)** — "地中熱1号井 CF-1"  
# - **Region** — top_left  
# - **Indicators / Measurements**:  
#   - **温度** — `-100.0` **°C** (confidence: Medium)  
#   - **流量** — `27` **L/m** (confidence: High)  
# - **State** — N/A  
# - **Color indicator** — None  
# - **Evidence** — `["raw text or region OCR position"]`  
# - **Confidence** — Medium  
# - **Notes** — "Temperature token confidence 0.52; value may be sensor error or OCR artifact."
# """.strip()

DEFAULT_IMAGE_PROMPT = """
You are an expert industrial HMI data‑extraction engine.
Input: a JSON object with key `regions`: [{id, name, bbox, ocr_lines:[{id, text, confidence, bbox}], tables:[{id, rows:[{cells:[{id, text, confidence, bbox}]}]}], icons:[{id, type, bbox, shape, color, color_conf}], arrows:[{id, bbox, dir, skeleton}], image_meta:{width, height}} ...].

Goal: convert all HMI‑relevant information into precise Markdown. Output only Markdown.

MANDATORY RULES (updated to avoid duplicates and speed up output)
1. **Exclude non‑HMI UI**: ignore overlays, external apps, and OS UI (TeamViewer panel, taskbar, browser chrome, logs). If such an overlay directly occludes HMI content, create a single entity with `Raw text="[occluded]"`, include its bbox, set `Confidence=Low`, and list the occluding overlay in `Notes`. Do not otherwise record non‑HMI UI.
2. **Preserve original text exactly** (including Japanese and device IDs). Do not translate, romanize, or correct characters. If OCR is uncertain, keep the raw OCR token and explain uncertainty in `Notes`.
3. **Detect entities automatically**. Do not require a predeclared entity count. Each distinct physical device or each table row representing a device must become a separate entity block **unless** merging rules (rule 6) apply.
4. **Numeric token coverage**: every numeric OCR token with `confidence ≥ 0.60` must appear in at least one entity measurement. If token.confidence < 0.60 → set value=`"[unreadable]"` and confidence=`Low`.
5. **Unnamed numeric values**: when a numeric value has no clear nearby label, create an entity with a short placeholder name using **shape+color+region** short code: `"[<shape>-<color>-<region>-<seq>]"` where `<shape>` ∈ {`cir`,`rect`,`pipe`,`tri`,`txt`}, `<color>` ∈ {`red`,`green`,`yellow`,`gray`,`blue`,`cyan`,`other`}, `<region>` ∈ {`top_left`,`top_center`,`top_right`,`center_diagram`,`bottom_pumps`,`overlay_popup`}, `<seq>` is a small integer per region.
6. **Merging / identity matching across multiple locations (avoid duplicates)**:
   - Treat two occurrences as the same entity if any of these hold:
     - Exact text match of `main_entity_name` (character-for-character).
     - Exact match of a device ID token present in both occurrences.
     - Strong proximity/label match: same Japanese name with only minor whitespace/punctuation differences.
   - **When merging**:
     - Create a single entity object and populate `regions` with **all regions** where the entity appears. The **first** element must be the primary region (prefer table region as primary when entity appears both in a table and in a diagram).
     - **Aggregate** all indicators from all occurrences into the single entity.
     - **Do not** create separate entities for repeated setpoint rows or repeated diagram labels for the same device; instead aggregate them (see rule 7).
     - Preserve provenance by adding each source as a separate `evidence` item for the relevant indicator (but limit evidence items per indicator to **at most 3** concise entries).
7. **Setpoint / schedule handling (prevent per-time-slot duplication)**:
   - If a device has multiple time‑range setpoints (e.g., 9:00–12:00, 12:00–15:00, ...), represent them as a single indicator named `"schedule"` with value = a Markdown table or an array of schedule rows:
     - Each schedule row: `{time_range, value_raw, value_number, unit, confidence, evidence}`.
   - **Do not** create a separate entity per time slot. Only create separate entities for distinct physical devices.
8. **Conflict resolution for repeated indicators**:
   - If the same indicator label appears with identical `value_raw` across sources, keep one indicator entry, merge evidence lists (deduplicate), and set `confidence` to the highest confidence among sources.
   - If the same indicator label appears with different `value_raw` values:
     - Use the value from the source with the **highest confidence** as the primary `value_raw` and parse `value_number` from that source if numeric.
     - Add conflict details to the indicator's `evidence` list (e.g., `"conflict: '14.2°C' from table A vs '14.0°C' from diagram B"`).
     - Set `confidence` to the lower of the involved confidences if the conflict remains unresolved; include a short `Notes` line recommending human review.
     - If two sources have equal confidence and different values, prefer the higher‑precision numeric value; if precision equal, prefer the source that appears later in the Markdown and set `confidence: "Low"`.
9. **Flow / pipe association**: associate numeric tokens to arrows/pipes when the token center lies within a 20px corridor along an arrow skeleton or within 15px of a pipe skeleton. If multiple candidate tokens match, choose the highest OCR confidence; if tied, create the indicator with `confidence=Low` and list candidates in `Notes`.
10. **Color / state detection**: map icon `shape`+`color`+`color_conf` to named colors (Red/Green/Yellow/Gray/Blue/Cyan/Other). If `color_conf < 0.6` → `Color indicator = Other` and `Confidence = Low`. Infer ON/OFF only when icon type + color strongly indicate state; otherwise set `State = Ambiguous`.
11. **Tables**: reproduce every table exactly in Markdown. If each table row corresponds to a device, create a separate entity block for each row **unless** that row is a duplicate of another device already merged per rule 6. For setpoint schedules, produce a single schedule indicator (rule 7) rather than separate entities per time slot.
12. **Measurements parsing**: split numeric and unit tokens (e.g., `27L/m` → value=`27`, unit=`L/m`). If unit parsing is ambiguous, keep the raw unit token and explain in `Notes`.
13. **Evidence**: each indicator must include up to **3** concise evidence items referencing OCR raw texts or table cells (e.g., `"from Markdown: '14.2°C' (section '熱源タンク温度設定')"`). If more provenance is required, store full provenance externally (not in the main output).
14. **Confidence mapping**: High ≥ 0.85, Medium 0.60–0.85, Low < 0.60. Entity confidence = minimum of involved token confidences unless visual features justify adjustment; explain adjustments in `Notes`.
15. **No merging of distinct devices**: never merge two different names/IDs into one entity. If two names appear in one visual block, create two entities.
16. **Occluded / missing**: if a label or numeric is fully occluded or missing, create an entity with `Raw text="[unreadable]"` and `Confidence=Low`.
17. **Markdown output format**:
    - First line: `## Screen title: <title 原文>` (if no title found, use `"[unknown]"`).
    - Then entities in reading order (top→bottom, left→right). Each entity must follow this exact block format:

### <Entity name 原文>

- **Type** — switch / sensor / pump / valve / tank / display / table / button / overlay / other  
- **Raw text (原文)** — "<original text exactly as seen>"  
- **Regions** — `["top_left","center_diagram"]` (primary region first)  
- **Indicators / Measurements**:  
  - `<Label 原文>` — `<value>` `<unit>` (confidence: High/Medium/Low)  
  - **schedule** — (if present) include a Markdown table or array of `{time_range, value_raw, value_number, unit, confidence}` (confidence per row)  
- **State** — ON / OFF / Ambiguous / N/A  
- **Color indicator** — Red / Green / Yellow / Gray / Blue / Cyan / Other / None  
- **Evidence** — `["from Markdown: '14.2°C' (table 'HT-1-3 row 1 cell 2')", "from diagram: 'HT-1-3 14.2°C (top_right)'], 'the red needle head points to ON/OFF'` (max 2 items per indicator)  
- **Confidence** — High / Medium / Low  
- **Notes** — (only when Confidence ≠ High or to explain mapping/ambiguity; keep concise)

    - If the entity originates from a table row, insert the full Markdown table immediately after that entity block (but do not repeat identical table rows as separate entities if merged).
    - For unnamed elements, the entity name must follow the placeholder pattern in rule 5 and include `Proximity hint` in `Notes`.

18. **Automated checks before output**:
    - Every numeric OCR token with confidence ≥ 0.60 appears in at least one entity measurement.
    - No two distinct device names/IDs are merged (unless merged by rule 6).
    - All Japanese text is preserved verbatim.
    - Every table row that maps to a device has its own entity block unless it is a duplicate merged per rule 6.
19. **Performance / brevity rules**:
    - Do not produce long explanatory paragraphs. Only include `Notes` when `confidence = Low` or when conflicts exist.
    - Limit `Evidence` to at most 3 concise items per indicator.
    - Deduplicate identical indicators (same label + same value_raw) across sources.
20. **Output only Markdown**. No JSON, no extra commentary.

Example merged entity (illustrative):

### 男内湯

- **Type** — display  
- **Raw text (原文)** — "男内湯"  
- **Regions** — `["top_center","center_diagram"]`  
- **Indicators / Measurements**:  
  - **浴槽現在溫度** — `41.6` **°C** (confidence: High)  
  - **熱交換出口溫度** — `51.6` **°C** (confidence: High)  
  - **三方弁開度表示** — `40` **%** (confidence: High)  
  - **温度** — `-100.0` **°C** (confidence: Medium)  
  - **流量** — `27` **L/m** (confidence: High) 
  - **schedule** — (table)  
    | time_range | temp | confidence | evidence |  
    |------------|------|------------|----------|  
    | 9:00–12:00 | 41.5°C | High | from Markdown: '9:00～12:00 41.5°C' |  
    | 12:00–15:00 | 41.5°C | High | from Markdown: '12:00～15:00 41.5°C' |  
- **State** — N/A  
- **Color indicator** — Green  
- **Evidence** — `["from Markdown table '男內湯 (Current Temp)': '浴槽現在溫度: 41.6°C'","from schedule table: '9:00～12:00 41.5°C'"]`  
- **Confidence** — High

Return only the Markdown output that follows these rules. No extra text.
""".strip()

MARKDOWN_TO_JSON_PROMPT = """
You are a senior industrial data engineer.
Task: From a provided HMI **Markdown** file (treated as authoritative), produce **one complete, valid JSON object only** that fully describes all visible HMI devices and indicators according to the schema below. Output **exactly one JSON object** and nothing else.

INPUT: a Markdown file describing an HMI screen. Preserve all original text (including Japanese) exactly as written.

OUTPUT SCHEMA (must match exactly)
{
  "screen_title": "string (exact title in original language or \"[unknown]\")",
  "entity_count": integer,
  "entities": [
    {
      "main_entity_name": "string (exact identifier as shown)",
      "type": "switch | sensor | pump | valve | tank | display | button | table | other",
      "regions": ["top_left" | "top_center" | "top_right" | "center_diagram" | "bottom_pumps" | "overlay_popup" | "other"],
      "indicators": [
        {
          "label": "string (exact label or placeholder)",
          "metric": "string (semantic metric: temperature | flow_rate | power | status | color | pressure | time | other)",
          "value_raw": "string | null (exact text as seen, e.g. '37.7℃', 'ON', '[unreadable]')",
          "value_number": number | null,
          "unit": "string | null",
          "value_type": "number | color | bool | text",
          "confidence": "High | Medium | Low",
          "evidence": ["string (concise evidence from Markdown)"]
        }
      ],
      "table_value": {
        "headers": ["string", ...],
        "rows": [["string", ...], ...]
      }  /* optional; include only for table entities */
    }
  ]
}

MANDATORY RULES (apply strictly)

1. Use the Markdown as authoritative. If Markdown is ambiguous, infer minimally and set indicator `confidence: "Low"` with evidence explaining the inference.

2. Preserve all original text exactly (do not translate or alter Japanese or device IDs).

3. Exclude non‑HMI UI (TeamViewer panels, OS taskbar, browser chrome, logs) entirely. If such overlay **occludes** HMI content, create a single entity with `value_raw: "[occluded]"`, include its `regions` and bbox/evidence, and set `confidence: "Low"`.

4. One JSON entity per physically distinct device or per table row that represents a device. Do not merge distinct devices unless identity matching rules (rule 6) apply.

5. Every numeric token visible in the Markdown with clear value must appear in at least one entity indicator. If a numeric token is unreadable or Markdown shows uncertainty, set `value_raw: "[unreadable]"`, `value_number: null`, `confidence: "Low"`.

6. **Merging / identity matching across multiple locations**:
   - Treat two occurrences as the same entity if any of these hold:
     - Exact text match of `main_entity_name` (character‑for‑character).
     - Exact match of a device ID token present in both occurrences.
     - Strong proximity/label match: same Japanese name with only minor whitespace/punctuation differences.
   - When merging:
     - Populate the entity's `regions` array with **all regions** where the entity appears. The first element in `regions` must be the **primary region** (prefer table region as primary when entity appears both in a table and in a diagram). Additional regions follow in reading order.
     - Aggregate all indicators from all occurrences into the single entity.
     - Preserve provenance by adding each source as a separate `evidence` item for the relevant indicator.
     - Limit `evidence` items per indicator to **at most 3** concise entries (keep full provenance externally if needed).

7. **Time token preservation**:
   - Any OCR token that matches a time range pattern (e.g., contains `～`, `-`, or matches `\d{1,2}:\d{2}` ranges) must be preserved verbatim.
   - Time tokens must appear as indicator `label` values (see rule 8) when they are schedule/setpoint rows, or as `value_raw`/`label` if they are standalone timestamps.
   - Do not normalize or drop original time text; if normalization is performed, also keep the original verbatim string in `evidence`.

8. **Schedule / setpoint handling (each schedule row becomes an indicator)**:
   - Do **not** store the schedule as a single table indicator. Instead, **split every schedule row into its own indicator** under the device.
   - Each schedule row indicator must include:
     - **label** — the exact `time_range` verbatim (e.g., `9:00～12:00`).
     - **metric** — `temperature` (or other semantic metric if explicit).
     - **value_raw** — exact text of the setpoint (e.g., `41.5°C`).
     - **value_number** — parsed numeric value when possible (e.g., `41.5`) or `null`.
     - **unit** — parsed unit (e.g., `°C`) or `null` if ambiguous.
     - **value_type** — `number`.
     - **confidence** — High/Medium/Low per token confidences.
     - **evidence** — concise source(s) (e.g., `"from Markdown: '9:00～12:00 41.5°C' (section '男露天 (Set Temp)')"`).
   - Preserve every original schedule row exactly as a separate indicator. If the same `time_range`+`value_raw` appears in multiple sources, deduplicate by exact `time_range`+`value_raw` and merge evidence (limit to 3 items).
   - If the same `time_range` has conflicting `value_raw` across sources, apply conflict resolution (rule 9).

9. **Conflict resolution for repeated indicators**:
   - If the same indicator label appears with identical `value_raw` across sources, keep one indicator entry, merge evidence lists, and set `confidence` to the highest confidence among sources.
   - If the same indicator label appears with different `value_raw` values:
     - Use the value from the source with the **highest confidence** as the primary `value_raw` and parse `value_number` from that source if numeric.
     - Add conflict details to the indicator's `evidence` list (e.g., `"conflict: '14.2°C' from table A vs '14.0°C' from diagram B"`).
     - Set `confidence` to the lower of the involved confidences if the conflict remains unresolved; include a `notes` evidence item recommending human review.
     - If two sources have equal confidence and different values, prefer the higher‑precision numeric value; if precision equal, prefer the source that appears later in the Markdown (treat later as more recent) and set `confidence: "Low"`.

10. Unnamed numeric values: create a short placeholder name using **shape-color-region** pattern: `"<shape>-<color>-<region>-<seq>"` where shape ∈ {cir, rect, pipe, tri, txt}, color ∈ {r,g,y,gr,b,c,o}, region ∈ {tl,tc,tr,cd,bp,ov}, seq is a small integer. Put that placeholder in `main_entity_name` and include `label` = original OCR token in `indicators` and a `Proximity hint` inside `evidence`.

11. Parse numeric values into `value_number` when possible. Split units into `unit`. If parsing fails, keep `value_raw` as-is and set `value_number: null` and `confidence: "Low"`.

12. Map ON/OFF, RUN/STOP, OPEN/CLOSE to `value_type: "bool"`, `value_raw: "ON"/"OFF"`, and `value_number: 1/0`.

13. Color indicators → `value_type: "color"`, `metric: "color"`, `value_raw` = color name. If color ambiguous in Markdown, set `confidence: "Low"`.

14. For each indicator include `evidence` items like `"from Markdown: '14.2°C' (section '熱源タンク温度設定')"` or `"from table: 'HT-1-3 row 1 cell 2'"`. When an indicator is aggregated from multiple sources, list each source separately (up to 3).

15. Confidence mapping: High ≥ clear and unambiguous in Markdown; Medium = somewhat ambiguous; Low = inferred or unreadable. Use these exact strings.

16. `entity_count` must equal the length of the `entities` array.

17. Final checks before output: JSON valid, `entity_count` correct, all Japanese preserved, no merged distinct devices (unless merged by the identity matching rules in rule 6), every schedule row preserved as an indicator, and every numeric/time token with confidence ≥ 0.60 appears in at least one indicator.

18. Return only the single JSON object that conforms exactly to the schema above. No extra text.

Notes on implementation expectations
- When merging, always preserve provenance: never drop the original source lines/cells; include them in `evidence` (limit to 3 concise items per indicator).
- If an entity appears in a table and also as a diagram block, prefer the table for structured fields (headers → labels) but still aggregate diagram values and include them as evidence.
- If timestamps or schedule rows exist, split them into separate indicators (Label = exact time_range) under the relevant entity.
- Deduplicate identical indicators (same label + same value_raw) by merging evidence lists.

Return only the single JSON object that conforms exactly to the schema above. No extra text.

""".strip()



EXTRACT_FROM_SCHEMA_PROMPT = """
You are a precise industrial data extraction engine.  
Input: (A) an HMI Markdown file (authoritative) and (B) a REQUIRED SCHEMA listing exact entities and indicators to extract.

Task: Output **one JSON object only** matching the REQUIRED SCHEMA structure below, filling each required indicator with extracted values from the Markdown.

REQUIRED OUTPUT SCHEMA (JSON only)
{
  "screen_title": "string",
  "entities": [
    {
      "main_entity_name": "string (from schema)",
      "type": "string (from schema)",
      "regions": ["string", ...], 
      "indicators": [
        {
          "label": "string (from schema)",
          "metric": "string (from schema)",
          "value_type": "number | color | bool | text (from schema)",
          "value_raw": "string | null (extract from Markdown or '[unreadable]')",
          "value_number": number | null,
          "unit": "string | null",
          "confidence": "High | Medium | Low",
          "evidence": ["string"]
        }
      ]
    }
  ]
}

STRICT RULES
1. Extract **only** the entities and indicators listed in the REQUIRED SCHEMA. Do not add or invent entities or indicators.
2. For each required indicator, locate its value in the Markdown and fill `value_raw`, parse `value_number` and `unit` when applicable, set `confidence`, and list concise `evidence` (e.g., `"from Markdown: '40.0°C' (section '熱源タンク温度設定')"`).
3. If a required indicator is not visible or unreadable in the Markdown, set `value_raw: "[unreadable]"`, `value_number: null`, and `confidence: "Low"`.
4. Preserve all original text exactly for `main_entity_name` and any labels (do not translate).
5. Use `value_type` exactly as provided by the schema for each indicator.
6. Support multiple `regions` for an entity if specified in the Markdown or schema.
7. Output must be strictly valid JSON matching the schema. No extra text, no markdown fences, no explanation.

Return only the single JSON object.
""".strip()
