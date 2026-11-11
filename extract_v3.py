import json

log_path = r"C:\Users\Administrator\.gemini\antigravity\brain\b3c6d5da-cda7-4b22-b5fa-c4117e17e8a4\.system_generated\logs\transcript_full.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        if obj.get("source") == "USER_EXPLICIT":
            content = obj.get("content", "")
            if "MASTER PROMPT V3.0" in content:
                print(f"Found at step: {obj.get('step_index')}")
                with open("v3_prompt_extracted.txt", "w", encoding="utf-8") as out:
                    out.write(content)
                break
