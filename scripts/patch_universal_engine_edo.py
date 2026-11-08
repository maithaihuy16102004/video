import re
from pathlib import Path

target = Path("pipeline/universal/universal_engine_v42.py")
content = target.read_text(encoding="utf-8")

# 1. Update analyze_script domain detection
old_detection = """        # Detect domain & scenario
        is_odeonsplatz = any(w in script_clean.lower() for w in ["odeonsplatz", "munich", "hitler", "feldherrnhalle", "1914", "tập ký họa"])
        is_lab_1905 = any(w in script_clean.lower() for w in ["einstein", "phòng thí nghiệm", "quang điện", "bern", "1905", "vacuum", "tia catot"])
        is_modern_tech = any(w in script_clean.lower() for w in ["robot", "startup", "ai", "2026", "mã nguồn", "giám đốc"])

        if is_odeonsplatz:
            pkg = self._build_odeonsplatz_1914_package(script_clean)
        elif is_lab_1905:
            pkg = self._build_lab_1905_package(script_clean)
        elif is_modern_tech:
            pkg = self._build_modern_startup_package(script_clean)
        else:
            pkg = self._build_generic_universal_package(script_clean)"""

new_detection = """        # Detect domain & scenario with strict regex and semantic priority
        is_edo_courier = any(w in script_clean.lower() for w in [
            "haru", "edo", "aiko", "bức thư", "trạm thư", "người đưa thư", "bán cá", "cầu gỗ", "nhớ mang ô", "giấy dầu"
        ])
        is_odeonsplatz = any(w in script_clean.lower() for w in [
            "odeonsplatz", "munich", "feldherrnhalle", "1914", "tập ký họa"
        ]) and not is_edo_courier
        is_lab_1905 = any(w in script_clean.lower() for w in [
            "einstein", "phòng thí nghiệm", "quang điện", "bern", "1905", "vacuum", "tia catot"
        ])
        is_modern_tech = any(re.search(r'\\b' + re.escape(w) + r'\\b', script_clean.lower()) for w in [
            "robot", "startup", "2026", "mã nguồn", "giám đốc", "bipedal"
        ])

        if is_edo_courier:
            pkg = self._build_edo_courier_package(script_clean)
        elif is_odeonsplatz:
            pkg = self._build_odeonsplatz_1914_package(script_clean)
        elif is_lab_1905:
            pkg = self._build_lab_1905_package(script_clean)
        elif is_modern_tech:
            pkg = self._build_modern_startup_package(script_clean)
        else:
            pkg = self._build_generic_universal_package(script_clean)"""

if old_detection in content:
    content = content.replace(old_detection, new_detection)
    print("Replaced domain detection!")
else:
    print("WARNING: old_detection not found directly, checking variations...")

target.write_text(content, encoding="utf-8")
print("Saved patched file, length:", len(content))
