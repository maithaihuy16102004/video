import sys, os, urllib.request, json, time, subprocess, hashlib
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = [
    {
        "id": "unseen_1_edo_courier",
        "title": "Bức Thư Không Được Phép Ướt",
        "genre": "Edo Historical Action & Comedy",
        "expected_locations": ["EDO_BRIDGE", "EDO_HOUSE"],
        "forbidden_archetypes": ["tech_founder", "polar_scientist"],
        "forbidden_props": ["tablet_computer", "scientific_scanner"],
        "script": """# BỨC THƯ KHÔNG ĐƯỢC PHÉP ƯỚT
*Truyện hư cấu lấy bối cảnh Nhật Bản thời Edo, khoảng năm 1800.*

**Nhân vật chính:** Haru — người đưa thư trẻ, 22 tuổi, nhanh nhẹn, đôi lúc hài hước.
**Nhân vật phụ:** Ông chủ trạm thư — nghiêm khắc. Aiko — cô gái trẻ, bình tĩnh, quyết đoán.

---

## CẢNH 1 — TRẠM THƯ LÚC CHIỀU MUỘN
**HARU (kể chuyện):**
Tôi tên Haru, làm nghề đưa thư ở Edo. Nhận thư, chạy thật nhanh và cố gắng không chết trên đường.
Chiều hôm ấy, ông chủ đưa cho tôi một phong thư bọc trong giấy dầu.

**ÔNG CHỦ TRẠM THƯ:**
“Đưa nó tới nhà Aiko trước khi chuông tối vang lên. Nhớ kỹ… tuyệt đối không được để ướt!”

## CẢNH 2 — CON PHỐ EDO DƯỚI CƠN MƯA
**HARU (kể chuyện):**
Chưa đầy năm phút sau, cả con phố biến thành dòng sông nhỏ.
Tôi chạy qua các cửa hàng gỗ, né xe kéo và suýt đâm vào người bán cá. Trong đầu tôi chỉ có một suy nghĩ: nếu thư ướt, ông chủ sẽ biến tôi thành cá khô.

## CẢNH 3 — CÂY CẦU GỖ
**HARU (kể chuyện):**
Đến cây cầu bắc qua con kênh, một tấm ván dưới chân bật tung.
Tôi ngã nhào, một tay bám chặt lan can gỗ, tay còn lại ôm khư khư bức thư vào ngực.

## CẢNH 4 — NGÔI NHÀ DƯỚI ÁNH ĐÈN LỒNG
**HARU (kể chuyện):**
Khi tới nơi, tôi trao bức thư khô nguyên cho Aiko. Aiko mở thư, đọc rất nhanh rồi đột nhiên bật cười.

## CẢNH 5 — NỘI DUNG BỨC THƯ
**AIKO:**
“Anh có biết trong thư viết gì không?”

**HARU:**
“Tôi chỉ biết nó không được phép ướt.”

**AIKO:**
“Aiko, nhớ mang ô. Chiều nay có thể mưa.”

**HARU (kể chuyện):**
Tôi nhìn đôi dép của mình... một chiếc đã mất từ lúc qua cầu. Hôm ấy tôi học được một bài học: Đôi khi thứ quan trọng nhất trong một bức thư... là biết nó viết cái gì trước khi mang đi.

**HẾT.**"""
    },
    {
        "id": "unseen_2_shanghai_1930",
        "title": "Tiếng Còi Tàu Lúc Nửa Đêm",
        "genre": "1930s Historical Mystery Noir",
        "expected_locations": ["RAIL_STATION"],
        "forbidden_archetypes": ["tech_founder", "polar_scientist"],
        "forbidden_props": ["tablet_computer", "scientific_scanner"],
        "script": """# TIẾNG CÒI TÀU LÚC NỬA ĐÊM
*Bối cảnh Thượng Hải năm 1930, sân ga xe lửa trung tâm trong sương mù đêm.*

**Nhân vật chính:** Thám tử Trần — điềm đạm, sắc bén, mặc áo măng-tô dài.
**Nhân vật phụ:** Người đưa tin — thiếu niên liên lạc mặc áo sơ mi len xám.

---

## CẢNH 1 — SÂN GA ĐÊM SƯƠNG MÙ
**THÁM TỬ TRẦN (kể chuyện):**
Thượng Hải, mùa đông năm 1930. Đèn dầu sân ga mờ ảo qua làn hơi nước bốc lên từ đầu máy xe lửa.
Tôi đứng chờ chuyến tàu đêm lúc 11 giờ 45.

**NGƯỜI ĐƯA TIN:**
“Thưa ông Trần, tài liệu ông yêu cầu đây. Chuyến tàu sắp khởi hành rồi.”

## CẢNH 2 — TRAO ĐỔI TÀI LIỆU
**THÁM TỬ TRẦN:**
“Có ai bám theo cậu không?”

**NGƯỜI ĐƯA TIN:**
“Tôi đã đi vòng qua ba dãy phố cổ trước khi tới ga.”

**THÁM TỬ TRẦN (kể chuyện):**
Tôi nhận phong bì niêm phong sáp đỏ, kiểm tra lại đồng hồ quả quýt.
Đúng lúc đó, tiếng còi tàu vang lên xé toạc màn sương. Sự thật cuối cùng cũng đã nằm trong tay tôi.

**HẾT.**"""
    },
    {
        "id": "unseen_3_vostok_antarctic",
        "title": "Bình Minh Trên Đỉnh Băng Vostok",
        "genre": "Polar Science Expedition",
        "expected_locations": ["ANTARCTIC"],
        "forbidden_archetypes": ["young_courier", "tech_founder"],
        "forbidden_props": ["letter_scroll_sealed", "walking_cane"],
        "script": """# BÌNH MINH TRÊN ĐỈNH BĂNG VOSTOK
*Bối cảnh Trạm nghiên cứu Vostok tại Nam Cực, nhiệt độ âm 65 độ C.*

**Nhân vật chính:** Tiến sĩ Elena — nhà khí hậu học trưởng, kiên cường.
**Nhân vật phụ:** Kỹ sư Tuấn — chuyên gia khoan băng vùng cực.

---

## CẢNH 1 — TRẠM NGHIÊN CỨU GIỮA BÃO TUYẾT
**TIẾN SĨ ELENA (kể chuyện):**
Nam Cực không có chỗ cho sai lầm. Ở độ sâu ba nghìn mét dưới lớp băng vĩnh cửu, chúng tôi đang tìm kiếm mẫu khí quyển nguyên thủy bốn trăm nghìn năm trước.

**KỸ SƯ TUẤN:**
“Elena, mũi khoan đã chạm tới tầng băng mục tiêu! Mẫu lõi đã sẵn sàng thu hồi.”

## CẢNH 2 — QUẢNG TRƯỜNG TUYẾT VÀ CỰC QUANG
**TIẾN SĨ ELENA:**
“Kích hoạt cảm biến quang phổ, chuẩn bị quét phân tích ngay.”

**TIẾN SĨ ELENA (kể chuyện):**
Khi cánh cửa phòng thí nghiệm mở ra, bão tuyết vừa dứt.
Phía chân trời Nam Cực, dải cực quang xanh lục uốn lượn rực rỡ như một dải lụa phát sáng. Chúng tôi đã thành công.

**HẾT.**"""
    }
]

def test_single_script(sc_idx, sc_data):
    print(f"\n==================================================================")
    print(f"RUNNING ACCEPTANCE TEST [{sc_idx+1}/3]: {sc_data['title']}")
    print(f"Genre: {sc_data['genre']} | Expected Locations: {sc_data['expected_locations']}")
    print(f"==================================================================")

    # 1. Plan request via http://127.0.0.1:4173/api/plan
    plan_payload = json.dumps({
        "script": sc_data["script"],
        "voice": "vieneu-Thiện Minh",
        "energy": "dynamic",
        "multiVoice": True
    }).encode("utf-8")

    req = urllib.request.Request("http://127.0.0.1:4173/api/plan", data=plan_payload, headers={"Content-Type": "application/json"})
    plan_resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
    
    print(f"[Plan Verification]")
    print(f"  Title: {plan_resp.get('title')}")
    print(f"  Scenes: {len(plan_resp.get('scenes', []))}")
    print(f"  Duration: {plan_resp.get('duration')}s")
    
    cast = plan_resp.get("cast", [])
    locations = plan_resp.get("locations", [])
    
    detected_loc = locations[0].get("category") if locations else "UNKNOWN"
    print(f"  Detected Location: {detected_loc}")
    assert detected_loc in sc_data["expected_locations"], f"Location mismatch: expected {sc_data['expected_locations']}, got {detected_loc}"
    print(f"  [PASS] Location category matches expected grounding: {detected_loc}")

    for c in cast:
        arch = c.get("archetypeId")
        print(f"  Actor {c.get('name')}: archetype={arch}, voice={c.get('voice')}")
        for fb in sc_data["forbidden_archetypes"]:
            assert arch != fb, f"FORBIDDEN archetype '{fb}' assigned to {c.get('name')} in {sc_data['title']}"
    print(f"  [PASS] All character archetypes are strictly compatible (zero forbidden archetypes)!")

    # 2. Render request via http://127.0.0.1:8787/api/render
    render_payload = json.dumps({
        "script": sc_data["script"],
        "voice": "vieneu-Thiện Minh",
        "energy": "dynamic",
        "quality": "fast",
        "multiVoice": True,
        "aspectRatio": "16:9",
        "plan": plan_resp,
        "multiDraft": True
    }).encode("utf-8")

    r2 = urllib.request.Request("http://127.0.0.1:8787/api/render", data=render_payload, headers={"Content-Type": "application/json"})
    job_info = json.loads(urllib.request.urlopen(r2, timeout=15).read().decode("utf-8"))
    job_id = job_info["id"]
    print(f"\n[Render Triggered] Job ID: {job_id}")

    # 3. Poll for completion
    start_t = time.time()
    final_status = None
    for step in range(120):
        time.sleep(3)
        s_resp = urllib.request.urlopen(f"http://127.0.0.1:8787/api/status?id={job_id}")
        st = json.loads(s_resp.read().decode("utf-8"))
        msg = st.get("message", "")
        status_code = st.get("status", "")
        elapsed = time.time() - start_t
        print(f"  [{elapsed:.1f}s] Status: {status_code} | {msg[:70]}...")
        if status_code in ("review_required", "done", "failed"):
            final_status = st
            break

    assert final_status and final_status.get("status") in ("review_required", "done"), f"Render job {job_id} failed: {final_status}"
    variants = final_status.get("variants", [])
    assert len(variants) == 3, f"Expected 3 drafts, got {len(variants)}"
    print(f"\n[Render Completed] Generated {len(variants)} drafts in {time.time() - start_t:.1f}s")

    # 4. Verify each draft
    job_dir = ROOT / "output" / "studio-jobs" / job_id
    verification_results = []
    for v in variants:
        idx = v["index"] + 1
        mp4_path = job_dir / f"draft-{idx}.mp4"
        assert mp4_path.exists() and mp4_path.stat().st_size > 500000, f"Draft MP4 missing or too small: {mp4_path}"
        
        # Check True Peak
        ebur_cmd = ["ffmpeg", "-nostats", "-i", str(mp4_path), "-filter_complex", "ebur128=peak=true", "-f", "null", "-"]
        ebur_res = subprocess.run(ebur_cmd, capture_output=True, text=True, errors="replace")
        peak_val = -99.0
        in_true_peak = False
        for line in ebur_res.stderr.splitlines():
            if "True peak:" in line:
                in_true_peak = True
                continue
            if in_true_peak and "Peak:" in line and "dBFS" in line:
                try:
                    peak_val = float(line.split("Peak:")[1].replace("dBFS", "").strip())
                    break
                except Exception:
                    pass

        # Check resolution & framerate
        probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", str(mp4_path)]
        probe_res = json.loads(subprocess.run(probe_cmd, capture_output=True, text=True).stdout)
        stream_info = probe_res["streams"][0]

        verif = {
            "draft_index": idx,
            "mp4_file": mp4_path.name,
            "size_bytes": mp4_path.stat().st_size,
            "resolution": f"{stream_info['width']}x{stream_info['height']}",
            "fps": stream_info["r_frame_rate"],
            "true_peak_dbfs": peak_val,
            "true_peak_passed": peak_val <= -1.5,
            "gdrive_url": v.get("gdriveUrl") or v.get("video")
        }
        verification_results.append(verif)
        print(f"  Draft #{idx}: {verif['resolution']} @ {verif['fps']}fps, True-Peak: {peak_val:.2f} dBFS (PASS <= -1.5), Size: {verif['size_bytes']/1024/1024:.2f} MB")
        assert verif["true_peak_passed"], f"Draft #{idx} True Peak exceeded: {peak_val} dBFS"

    # Verify render hash divergence between variants
    import hashlib
    d1_file = job_dir / "draft-1.mp4"
    d2_file = job_dir / "draft-2.mp4"
    d3_file = job_dir / "draft-3.mp4"
    h1 = hashlib.sha256(d1_file.read_bytes()).hexdigest()
    h2 = hashlib.sha256(d2_file.read_bytes()).hexdigest()
    h3 = hashlib.sha256(d3_file.read_bytes()).hexdigest()
    assert h2 != h1, f"Duplicate render detected: draft-2 hash ({h2}) matches draft-1 ({h1})"
    assert h3 != h1, f"Duplicate render detected: draft-3 hash ({h3}) matches draft-1 ({h1})"
    print(f"  [PASS] Render hash divergence verified: draft-2 ({h2[:12]}...) and draft-3 ({h3[:12]}...) differ from draft-1 ({h1[:12]}...)")
    assert verif["resolution"] == "1920x1080", f"Resolution invalid: {verif['resolution']}"

    return {
        "job_id": job_id,
        "script_id": sc_data["id"],
        "title": sc_data["title"],
        "detected_location": detected_loc,
        "cast": cast,
        "verification": verification_results
    }

def main():
    print("==================================================================")
    print("V5.1 FINAL STABILIZATION SPRINT — HONEST ACCEPTANCE TEST SUITE")
    print("Target: 3 Previously Unseen Scripts End-to-End Through Production Pipeline")
    print("Zero source code modifications permitted during test.")
    print("==================================================================")

    suite_results = []
    for i, sc in enumerate(SCRIPTS):
        res = test_single_script(i, sc)
        suite_results.append(res)

    report_path = ROOT / "output" / "v51_drafts" / "acceptance_test_suite_results.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(suite_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n==================================================================")
    print(f"ALL 3 ACCEPTANCE TESTS PASSED WITH 100% SUCCESS!")
    print(f"Results report saved to: {report_path}")
    print("==================================================================")

if __name__ == "__main__":
    main()
