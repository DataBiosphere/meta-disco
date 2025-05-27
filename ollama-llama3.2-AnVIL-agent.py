import sys
import json
import requests
import re

OLLAMA_HOST = "http://10.50.3.16:11434"
MODEL = "llama3.2"

def build_anvil_prompt(metadata_dict):
    return f"""
You are an expert NHGRI AnVIL genomics metadata agent.

Your job is to infer the **reference genome** used for each file based on the provided metadata fields:
- files.file_name
- datasets.title

Return a JSON list. Each object must follow this format:

{{
  "files.file_name": <string>,
  "files.data_modality": <string>, //e.g. genomic, transcriptomic 
  "files.reference_genome": <string>,           // e.g. GRCh38, GRCh37, T2T-CHM13, hg19, or "unknown"
  "files.determination_data_modality": "logic" | "llm",       // Use "logic" if obvious from name/title, otherwise "llm"
  "files.confidence_data_modality": <float>,                  // Between 0 and 1
  "files.justification_data_modality": <string>
}}


Here is the metadata input:
{json.dumps(metadata_dict, indent=2)}

Respond ONLY with the JSON list. Do NOT include explanations, markdown, or extra text.
"""

def main(index, jsonl_path="anvil_input.json"):
    with open(jsonl_path) as f:
        all_lines = f.readlines()
    metadata_dict = json.loads(all_lines[int(index)])
    prompt = build_anvil_prompt(metadata_dict)

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }

    response = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, stream=True)

    output_chunks = []
    for line in response.iter_lines():
        if line:
            try:
                parsed = json.loads(line.decode("utf-8"))
                if "message" in parsed and "content" in parsed["message"]:
                    output_chunks.append(parsed["message"]["content"])
            except json.JSONDecodeError as e:
                print("Stream decode error:", e)

    final_output = "".join(output_chunks).strip()
    clean_output = re.sub(r"^```(?:json)?\s*|\s*```$", "", final_output, flags=re.MULTILINE)

    try:
        parsed = json.loads(clean_output)
        outname = metadata_dict["files.file_name"].replace("/", "_")
        with open(f"ollama_response_{outname}.json", "w") as f:
            json.dump(parsed, f, indent=2)
        print(f"✅ Saved: ollama_response_{outname}.json")
    except json.JSONDecodeError as e:
        print("❌ Failed to parse JSON:", e)
        print("🔴 Raw response:\n", repr(clean_output))

if __name__ == "__main__":
    main(sys.argv[1])
