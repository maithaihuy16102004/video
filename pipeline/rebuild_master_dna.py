import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"d:\Agent\pipeline")

import studio_api


FULL_SHOWCASE_SCRIPT = """[COLD OPEN — BERLIN, 1945]
HITLER:
30 năm trước, tôi chỉ là một người lính mang thư trong chiến hào. Và lúc đó, mọi chuyện trông đơn giản hơn rất nhiều.

[HOOK — MUNICH, 1914]
NGƯỜI DẪN:
Munich năm 1914. Hitler 25 tuổi, tương lai mù mịt, rồi cả châu Âu lao vào một cuộc chiến tranh khổng lồ.
HITLER:
Người ta nói chiến tranh sẽ kết thúc trước Giáng sinh. Nghe cũng ổn.
NGƯỜI LÍNH:
Hóa ra họ không nói rõ Giáng sinh năm nào. Chúng tôi đã đánh giá tình hình hơi lạc quan.

[CẢNH — MẶT TRẬN PHÍA TÂY, 1914]
NGƯỜI DẪN:
Hitler được biên chế vào Trung đoàn Bộ binh Dự bị Bavaria số 16 và được đưa tới Mặt trận phía Tây. Nếu bạn đang tưởng tượng những đoàn quân hùng dũng, thực tế là bùn, chuột và pháo binh.
LÍNH 1:
Đây là chiến tranh vinh quang à?
LÍNH 2:
Chắc vậy. Bùn rất vinh quang.
SĨ QUAN:
Mang thông điệp này qua khu vực đang bị pháo kích.
HITLER:
Tôi phải đi qua đó? Có đường nào an toàn hơn không?
SĨ QUAN:
Không.
HITLER:
Tuyệt vời.

[CẢNH — TRẬN SOMME, 1916]
NGƯỜI DẪN:
Chiến tranh cứ tiếp tục kéo dài. Năm 1916, tại Trận Somme, Hitler bị mảnh đạn pháo làm bị thương ở chân.
BÁC SĨ:
Anh bị thương. Anh sẽ được đưa về Đức.
HITLER:
Tôi cũng vừa nhận ra.

[CẢNH — GẦN YPRES, THÁNG 10/1918]
NGƯỜI DẪN:
Tháng 10 năm 1918, gần Ypres Bỉ, Hitler bị trúng khí độc và tạm thời suy giảm thị lực.

[CẢNH — BỆNH VIỆN PASEWALK, 1918]
NGƯỜI LÍNH:
Chiến tranh kết thúc rồi. Đức đã ký đình chiến ngày 11 tháng 11.
HITLER:
Đức đầu hàng sao?

[CẢNH — MUNICH, 1919]
NGƯỜI DẪN:
Năm 1919, Hitler trở lại Munich giữa bạo loạn, đình công và khủng hoảng hậu chiến.

[CẢNH — MUNICH, 12/9/1919]
NGƯỜI DẪN:
Ngày 12 tháng 9 năm 1919, trong quán bia Sterneckerbräu ở Munich, Hitler tới quan sát Đảng Công nhân Đức.
THÀNH VIÊN DAP:
Anh chỉ tới đây để quan sát thôi đúng không?
HITLER:
Ban đầu là thế. Tôi có vài ý kiến."""


def main() -> None:
    job_id = "52d57a1cf6"
    folder = studio_api.JOBS / job_id
    req_path = folder / "request.json"
    payload = json.loads(req_path.read_text(encoding="utf-8"))
    payload["script"] = FULL_SHOWCASE_SCRIPT
    payload["aspectRatio"] = "16:9"
    payload["plan"]["scenes"] = []
    req_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for p in (folder / "dialogue-voice.wav", folder / "dialogue-voice.json"):
        if p.exists():
            p.unlink()

    print("1. Running prepare_voice() with Natural Contextual Voice Pacing (no fast speed-up) & 8 Unique Voices...")
    voice, subtitles, segments, cast = studio_api.prepare_voice(payload, folder, job_id=job_id)
    voices = [c["voice"] for c in (cast or [])]
    print(f"CAST ({len(cast or [])} characters, {len(set(voices))} unique voices):")
    for c in (cast or []):
        print(f"  - {c['name']} ({c['character']}): {c['voice']} [{c.get('voiceId')}] rate={c.get('rate')} pitch={c.get('pitch')}")
    assert len(voices) == len(set(voices)), f"Duplicate voices detected: {voices}"

    duration = studio_api.voice_duration(voice)
    print(f"Total audio duration (natural relaxed cadence): {duration:.2f}s")

    print("2. Running Cinematic Director Engine 16:9 (Beat Analyzer -> Comedy/Emotion/History -> Shot Sequence Planner)...")
    spec_render = studio_api.render_spec(payload, duration, folder, subtitles, 0, "render-props.json", segments, cast)
    spec_master = studio_api.render_spec(payload, duration, folder, subtitles, 0, "master-props.json", segments, cast)

    props_data = json.loads(spec_master.read_text(encoding="utf-8"))
    ret_dir = props_data.get("retentionDirector", {})
    print(f"RETENTION DIRECTOR WAVE: {ret_dir.get('emotionWaveCurve')}")
    for row in ret_dir.get("beatTable", []):
        print(
            f"  [{row['beat']}] {row['emotionWave']} {row['type']:<18} "
            f"CURIOSITY={row['curiosity']} COMEDY={row['comedy']} SIG={row.get('signatureMoment')} "
            f"STATE={row.get('stateChange')}"
        )
    all_subs = [ss for sc in props_data.get("scenes", []) for ss in sc.get("subShots", [])]
    redirected_cnt = sum(1 for ss in all_subs if str(ss.get("validator_action", "")).startswith("REDIRECTED"))
    max_sim_after = max((float(ss.get("visual_similarity_score", 0.0)) for ss in all_subs), default=0.0)
    print(f"SHOT SIMILARITY VALIDATOR: total_shots={len(all_subs)} redirected_shots={redirected_cnt} max_similarity={max_sim_after:.2f} (threshold <= 0.72)")
    for sc in props_data.get("scenes", [])[:10]:
        print(
            f"  [{sc['id']}] loc={sc.get('location')} beat={sc.get('beatType')} "
            f"subShots={[(x.get('shot_size'), x.get('perspective_type'), x.get('pose_family'), x.get('visual_similarity_score')) for x in sc.get('subShots', [])]}"
        )

    target_voice = studio_api.ENGINE / "public" / "ricks-draft" / "audio" / "voice.wav"
    target_voice.parent.mkdir(parents=True, exist_ok=True)
    target_voice.write_bytes(voice.read_bytes())

    render_master = "--master" in sys.argv
    out = folder / ("master-1080p.mp4" if render_master else "draft.mp4")
    mode = "final" if render_master else "preview"
    print(f"3. Rendering 16:9 ({mode}) Drafts for preview (lightweight filesize, Master skipped until approved)...")
    for i, label in enumerate(["High retention", "Dry Historical Comedy", "Cinematic Documentary"]):
        v_spec = studio_api.render_spec(payload, duration, folder, subtitles, i, f"variant-{i + 1}.json", segments, cast)
        v_out = folder / f"draft-{i + 1}.mp4"
        studio_api.command([
            sys.executable,
            str(studio_api.ROOT / "pipeline" / "fast_video_draft.py"),
            "--mode",
            "preview",
            "--spec",
            str(v_spec),
            "--out",
            str(v_out),
        ])
    shutil.copy2(folder / "draft-1.mp4", folder / "draft.mp4")
    if render_master:
        studio_api.command([
            sys.executable,
            str(studio_api.ROOT / "pipeline" / "fast_video_draft.py"),
            "--mode",
            "final",
            "--spec",
            str(spec_master),
            "--out",
            str(out),
        ])

    print("4. Running automated QA gate & generating 12-frame contact sheet...")
    qa_report = folder / "master-quality-report.json"
    contact = folder / "master-quality-contact.png"
    subprocess.run(
        [
            sys.executable,
            str(studio_api.ROOT / "pipeline" / "video_quality_gate.py"),
            "--video",
            str(out),
            "--spec",
            str(spec_master),
            "--report",
            str(qa_report),
            "--contact",
            str(contact),
        ],
        cwd=studio_api.ROOT,
        check=True,
    )
    qa = json.loads(qa_report.read_text(encoding="utf-8"))
    print("QA GATE SCORE:", qa.get("score"), "STATUS:", qa.get("status"))


if __name__ == "__main__":
    main()
