import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.test_episode01_preflight import audit_script

# Read the currently loaded script from sites/ai-clip-studio/app/page.tsx
with open(r'd:\Agent\sites\ai-clip-studio\app\page.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

# Extract sample string
start = code.find('const sample = `') + len('const sample = `')
end = code.find('`;\n\nexport default function Home()')
current_fe_script = code[start:end]

print("=== AUDIT OF CURRENTLY LOADED SCRIPT IN FRONTEND ===")
rep = audit_script(current_fe_script)
print("Overall Passed:", rep["overall_passed"])
print("Blockers:")
for b in rep["blocking_reasons"]:
    print(" -", b)
print("\nMetrics:")
print(f"Total Words: {rep['rule_3_word_counts']['total_words']}")
print(f"Dialogue Words: {rep['rule_3_word_counts']['dialogue_words']}")
print(f"Metadata Words: {rep['rule_3_word_counts']['metadata_words']}")
print(f"Scene Count: {rep['rule_1_scenes']['count']} (Passed: {rep['rule_1_scenes']['passed']})")
print(f"Character Count: {rep['rule_2_characters']['count']} (Passed: {rep['rule_2_characters']['passed']})")
print(f"Meme Cues: {rep['rule_5_meme_cues']['meme_scenes']} (Passed: {rep['rule_5_meme_cues']['passed']})")
