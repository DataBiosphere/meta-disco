import pandas as pd
import requests
import json
import sys
import os

LLM_HOST = "http://localhost:11434"
DATAFRAME = pd.read_csv("metadisco-training-evaluation.tsv",sep='\t')

def build_anvil_prompt(metadata_dict):
	return f"""
You are an expert NHGRI AnVIL genomics metadata agent that harmonizes and infers missing submitter data.

You are provided a single file's metadata: its filename, dataset title, and, when available, a BAM/SAM header.

Your job is to infer **exactly two fields** for this ONE file:

1. **data_modality** — biological data type (e.g., "genomic" or "transcriptomic")
2. **reference_genome** — genome build used for alignment (e.g., "GRCh38", "GRCh37", "CHM13", "CHM13-GRCh38", or "none")

Return exactly **one JSON object**, not a list, not multiple entries.

Here is the input metadata for this single file:
{json.dumps(metadata_dict, indent=2)}

Your response must be a single JSON object, exactly in this format:

{{
  "data_modality": <string>,
  "reference_genome": <string>
}}

Do NOT include markdown, lists, arrays, explanations, or any extra text.
"""

def build_payload(prompt, model):
	return {
	"model": model,
	"messages": [
		{
			"role": "system",
			"content": (
				"You are a strict JSON-only metadata agent. "
				"You must always respond **only** with valid JSON "
				"matching the requested schema — no prose or explanations."
			)
		},
		{
			"role": "user",
			"content": prompt
		}
	],
	"temperature": 0.1,   # introduce creativity
	"top_p": 0.9,
	"stream": False
}

def build_output_tsv_name(row):
	"""Construct output TSV filename using model, created_at, and filename fields."""
	model = str(row['model']).replace(":", "-")  # sanitize colons for filenames
	created = str(row['created_at']).split("T")[0]  # keep only the date if ISO timestamp
	fname = os.path.splitext(os.path.basename(row['filename']))[0]
	return f"{model}_{created}_{fname}.tsv"

def main(index, model, output_path):
	df_infer = DATAFRAME.iloc[index]
	eval_dict = df_infer[['title', 'filename','header']].to_dict()
	prompt = build_anvil_prompt(eval_dict)
	payload = build_payload(prompt, model)
	response = requests.post(f"{LLM_HOST}/api/chat", json=payload).json()
	merged = {**eval_dict, **response}
	df = pd.DataFrame([merged])
	df['title_filename_drs'] = df_infer['existing_model_response']

	output = build_output_tsv_name(merged)
	# header = not os.path.exists(output_path)  # write header only once

	df.to_csv(os.path.join(output_path, output), sep='\t', index=False, mode='a')

if __name__ == "__main__":
	if len(sys.argv) < 4:
		print("Usage: python metadisco-inference.py <row_index> <model_name> <output_tsv_path>")
		sys.exit(1)

	row_index = int(sys.argv[1])
	model_name = sys.argv[2]
	output_tsv = sys.argv[3]
	main(row_index, model_name, output_tsv)