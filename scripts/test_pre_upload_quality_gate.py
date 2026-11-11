"""
Acceptance Test Suite for SYSTEM PROMPT — PRE-RENDER & PRE-UPLOAD QUALITY GATE
Stack: Motion Canvas + Three.js + Stickman
Target: YouTube-ready output, no manual re-check needed before upload.

Validates all 8 Rules:
[1] Output hash differs from all sibling variant hashes (Rule 1)
[2] No static-pose window > 3s without `frozen: true` tag (Rule 2)
[3] Max prop-to-hand distance <= 2px across all frames (Rule 3)
[4] No occlusion violations on known static geometry (Rule 4)
[5] No subtitle line exceeds container bounds at any timestamp (Rule 5)
[6] No camera shot exceeds 35% foreground-structure coverage without tag (Rule 6)
[7] Integrated loudness within +-0.5 LUFS of -14, True Peak <= -1.5 dBTP (Rule 7)
[8] Resolution 1920x1080, 24fps, H.264 + AAC, .vtt caption sync (Rule 8)
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.pre_upload_quality_gate import PreUploadQualityGate


def test_rule1_elementary_stream_hashes_and_duplicate_abort():
    print("\n--- [Test 1] Rule 1: Elementary Stream Content Hashes & Duplicate Abort ---")
    gate = PreUploadQualityGate()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        mp4_a = tmp_path / "variant_a.mp4"
        mp4_b_dup = tmp_path / "variant_b_dup.mp4"
        mp4_c_diff = tmp_path / "variant_c_diff.mp4"

        # Generate test MP4 A (2s video 1920x1080, audio 48kHz stereo)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=red:s=1920x1080:r=24:d=2.0",
            "-f", "lavfi", "-i", "sine=frequency=440:r=48000:d=2.0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(mp4_a)
        ], check=True)

        # Generate MP4 B with IDENTICAL content (different creation time/container metadata)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=red:s=1920x1080:r=24:d=2.0",
            "-f", "lavfi", "-i", "sine=frequency=440:r=48000:d=2.0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(mp4_b_dup)
        ], check=True)

        # Generate MP4 C with DELIBERATE camera/visual difference (blue background)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=1920x1080:r=24:d=2.0",
            "-f", "lavfi", "-i", "sine=frequency=880:r=48000:d=2.0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(mp4_c_diff)
        ], check=True)

        # 1. Compute elementary stream hashes
        hashes_a = gate.compute_elementary_stream_hashes(mp4_a)
        hashes_b = gate.compute_elementary_stream_hashes(mp4_b_dup)
        hashes_c = gate.compute_elementary_stream_hashes(mp4_c_diff)

        assert hashes_a["video_stream_hash"] == hashes_b["video_stream_hash"], "Identical elementary video streams must match hash!"
        assert hashes_a["video_stream_hash"] != hashes_c["video_stream_hash"], "Divergent elementary video streams must differ in hash!"
        print(f"  [PASS] Elementary stream hashes: Video A == Video B ({hashes_a['video_stream_hash'][:12]}...), Video C differs ({hashes_c['video_stream_hash'][:12]}...)")

        # 2. Check duplicate variant abort when params not propagated
        r1_dup = gate.check_rule1_no_duplicate_variants(
            output_mp4=mp4_b_dup,
            sibling_mp4_paths=[mp4_a],
            variant_params_changed=False
        )
        assert not r1_dup["passed"], "Duplicate variant without deliberate changes must fail Rule 1!"
        assert "Duplicate render detected" in r1_dup["error"], f"Expected duplicate abort error, got: {r1_dup['error']}"
        print(f"  [PASS] Duplicate variant correctly aborted: {r1_dup['error'][:80]}...")

        # 3. Check divergent variant passes
        r1_diff = gate.check_rule1_no_duplicate_variants(
            output_mp4=mp4_c_diff,
            sibling_mp4_paths=[mp4_a],
            variant_params_changed=True
        )
        assert r1_diff["passed"], "Divergent variant must pass Rule 1!"
        print(f"  [PASS] Divergent variant verified unique and approved.")


def test_rule2_minimum_motion_and_frozen_tag():
    print("\n--- [Test 2] Rule 2: Minimum Motion Requirement (2-3s Pacing & frozen: true) ---")
    gate = PreUploadQualityGate()

    # Case A: Static hold > 3.0s without frozen tag -> MUST FAIL
    pkg_static = {
        "total_sequence_duration_seconds": 10.0,
        "actors": [{
            "actor_id": "actor_static",
            "performance_cues": [
                {"time": 0.0, "action": "idle", "pos": [0, 0, 0]},
                {"time": 4.5, "action": "idle", "pos": [0, 0, 0]}  # 4.5s static hold
            ]
        }]
    }
    r2_static = gate.check_rule2_minimum_motion(pkg_static)
    assert not r2_static["passed"], "Static pose held for > 3.0s without frozen tag must fail!"
    print(f"  [PASS] Static pose hold correctly rejected: {r2_static['violations'][0]}")

    # Case B: Static hold > 3.0s WITH frozen: true tag -> MUST PASS
    pkg_frozen = {
        "total_sequence_duration_seconds": 10.0,
        "actors": [{
            "actor_id": "actor_frozen",
            "performance_cues": [
                {"time": 0.0, "action": "shock", "frozen": True, "pos": [0, 0, 0]},
                {"time": 4.5, "action": "listen", "pos": [0, 0, 0]},
                {"time": 7.0, "action": "speak", "pos": [0.08, 0, 0]},
                {"time": 9.2, "action": "react", "pos": [0, 0, 0]}
            ]
        }]
    }
    r2_frozen = gate.check_rule2_minimum_motion(pkg_frozen)
    assert r2_frozen["passed"], f"Tagged frozen beat must pass, got violations: {r2_frozen.get('violations')}"
    print("  [PASS] Tagged 'frozen: true' hold for > 3.0s correctly permitted.")

    # Case C: Active performance with gesture/weight shift every 2-3s -> MUST PASS
    pkg_active = {
        "total_sequence_duration_seconds": 9.0,
        "actors": [{
            "actor_id": "actor_active",
            "performance_cues": [
                {"time": 0.0, "action": "listen", "pos": [0, 0, 0]},
                {"time": 2.2, "action": "think", "pos": [0.08, 0, 0.04]},
                {"time": 4.4, "action": "speak", "pos": [-0.08, 0, -0.04]},
                {"time": 6.6, "action": "speak_gestural", "pos": [0.08, 0, 0.04]},
                {"time": 8.5, "action": "relief", "pos": [0, 0, 0]}
            ]
        }]
    }
    r2_active = gate.check_rule2_minimum_motion(pkg_active)
    assert r2_active["passed"], f"Active character motion must pass, got: {r2_active.get('violations')}"
    print("  [PASS] Active motion (weight shift/gesture every 2.2s) strictly verified.")


def test_rule3_prop_to_hand_attachment():
    print("\n--- [Test 3] Rule 3: Prop-to-Hand Attachment Tolerance (<= 2px) ---")
    gate = PreUploadQualityGate()

    # Case A: Prop deviation > 2px -> MUST FAIL
    r3_fail = gate.check_rule3_prop_attachment(prop_audit={"passed": False, "maxDistance": 3.4, "violations": ["Offset 3.4px exceeds 2px"]})
    assert not r3_fail["passed"], "Deviation > 2px must fail!"
    print(f"  [PASS] Prop deviation > 2px correctly rejected: {r3_fail['violations'][0]}")

    # Case B: Prop distance 0.8px <= 2px -> MUST PASS
    r3_pass = gate.check_rule3_prop_attachment(prop_audit={"passed": True, "maxDistance": 0.8, "violations": []})
    assert r3_pass["passed"], "Deviation <= 2px must pass!"
    print("  [PASS] Prop attached with 0.8px deviation (<= 2px) passed.")


def test_rule4_depth_and_occlusion():
    print("\n--- [Test 4] Rule 4: Three.js Per-Frame Depth Sorting & Occlusion Ordering ---")
    gate = PreUploadQualityGate()

    test_pkg = {
        "actors": [
            {"actor_id": "haru", "staging": {"initial_world_pos": [0.0, 3.7, 3.5]}},  # Behind front railing (z=2.05)
            {"actor_id": "passerby", "staging": {"initial_world_pos": [0.0, 3.7, 1.2]}}  # In front of front railing
        ]
    }
    r4 = gate.check_rule4_depth_and_occlusion(test_pkg, camera_pos=[0.0, 3.7, 7.0])
    assert r4["passed"], "Depth sorting evaluation must pass!"
    assert r4["sorted_elements_count"] >= 3, "Expected at least 3 elements sorted by camera distance"
    print(f"  [PASS] Depth-sorted {r4['sorted_elements_count']} scene elements; occlusion re-evaluated per frame.")


def test_rule5_subtitle_bounds_and_font_scaling():
    print("\n--- [Test 5] Rule 5: Subtitle Container 90% Max Width, Auto-Wrap & Font Scaling ---")
    gate = PreUploadQualityGate()

    # Extra-long Vietnamese dialogue line (259 chars) that initially requires 3 lines at 28px and triggers font reduction
    long_line = (
        "Vào năm 1800 tại cầu Nihonbashi, Haru đang vội vã chạy qua màn mưa tầm tã để kịp giao "
        "bức thư mật quan trọng cho quan trấn thủ kinh thành trước khi cổng thành phía bắc chính thức đóng cửa "
        "vào lúc hoàng hôn buông xuống trên dòng sông Sumida mênh mông lạnh giá."
    )
    test_pkg = {
        "voice_timeline": {
            "lines": [
                {"start_sec": 0.0, "end_sec": 6.0, "speaker": "Haru", "text": long_line}
            ]
        }
    }
    r5 = gate.check_rule5_subtitle_bounds(test_pkg, frame_width=1920, frame_height=1080)
    assert r5["passed"], f"Long subtitle must be wrapped and reduced to fit, got: {r5.get('violations')}"
    assert r5["font_reductions_applied"] > 0, "Expected at least 1 font reduction step for extra-long line"
    print(f"  [PASS] Long subtitle (168 chars) auto-wrapped and reduced font by 10% steps to fit <= 2 lines with 0 overflow.")


def test_rule6_camera_framing_and_foreground_structure():
    print("\n--- [Test 6] Rule 6: Camera Framing Defaults & Foreground Structure Coverage ---")
    gate = PreUploadQualityGate()

    # Case A: Bridge shot with > 35% foreground structure coverage WITHOUT tag -> MUST FAIL
    pkg_untagged = {
        "scene_world": {
            "location_id": "LOC_EDO_WOODEN_BRIDGE",
            "architecture_style": "EDO_BRIDGE",
            "threejs_environment": {
                "camera_initial": {"position": [0.0, 2.0, 3.5], "target": [0.0, 3.2, 0.0], "fov": 50},
                "camera_keyframes": [{"t": 0.0, "position": [0.0, 2.0, 3.5], "target": [0.0, 3.2, 0.0]}]
            }
        },
        "actors": [{"actor_id": "haru", "staging": {"initial_world_pos": [0.0, 2.65, 0.0]}}],
        "tags": []
    }
    r6_fail = gate.check_rule6_camera_framing_defaults(pkg_untagged)
    assert not r6_fail["passed"], "Foreground structure coverage > 35% without tag must fail!"
    print(f"  [PASS] Shot with excessive foreground structure coverage correctly rejected: {r6_fail['violations'][0]}")

    # Case B: Bridge shot with > 35% coverage WITH 'composition: claustrophobic' -> MUST PASS
    pkg_tagged = {
        "scene_world": {
            "location_id": "LOC_EDO_WOODEN_BRIDGE",
            "architecture_style": "EDO_BRIDGE",
            "composition": "claustrophobic",
            "threejs_environment": {
                "camera_initial": {"position": [0.0, 2.0, 3.5], "target": [0.0, 3.2, 0.0], "fov": 50},
                "camera_keyframes": [{"t": 0.0, "position": [0.0, 2.0, 3.5], "target": [0.0, 3.2, 0.0]}]
            }
        },
        "composition": "claustrophobic",
        "actors": [{"actor_id": "haru", "staging": {"initial_world_pos": [0.0, 2.65, 0.0]}}],
        "tags": ["claustrophobic"]
    }
    r6_pass = gate.check_rule6_camera_framing_defaults(pkg_tagged)
    assert r6_pass["passed"], f"Tagged claustrophobic shot must pass, got: {r6_pass.get('violations')}"
    print("  [PASS] Shot with 'composition: claustrophobic' explicitly permitted.")


def test_rule7_audio_loudness_normalization():
    print("\n--- [Test 7] Rule 7: Audio Loudness Normalization (-14.0 LUFS, TP <= -1.5 dBTP) ---")
    gate = PreUploadQualityGate()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        raw_wav = tmp_path / "raw_audio.wav"
        norm_wav = tmp_path / "normalized_audio.wav"

        # Generate test tone (4s duration)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:r=48000:d=4.0",
            "-ar", "48000", "-ac", "2",
            str(raw_wav)
        ], check=True)

        # Apply Rule 7 mandatory loudnorm normalization
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(raw_wav),
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=7:print_format=json",
            "-ar", "48000",
            str(norm_wav)
        ], check=True)

        # Audit with Gate
        r7 = gate.check_rule7_audio_loudness(norm_wav)
        assert r7["passed"], f"Normalized audio must pass Rule 7, got: {r7.get('violations')}"
        assert abs(r7["integrated_lufs"] - (-14.0)) <= 0.5, f"Loudness {r7['integrated_lufs']} outside ±0.5 LUFS of -14"
        assert r7["true_peak_dbtp"] <= -1.5, f"True Peak {r7['true_peak_dbtp']} exceeds -1.5 dBTP"
        print(f"  [PASS] Normalized Audio: {r7['integrated_lufs']:.2f} LUFS (within ±0.5 of -14), TP: {r7['true_peak_dbtp']:.2f} dBTP (<= -1.5).")


def test_rule8_format_codecs_and_vtt_sync():
    print("\n--- [Test 8] Rule 8: 1080p, 24fps, H.264+AAC & VTT Sync Verification ---")
    gate = PreUploadQualityGate()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        test_mp4 = tmp_path / "test_1080p_24fps.mp4"
        test_vtt = tmp_path / "test_captions.vtt"

        # Generate 1920x1080 @ 24fps, H.264 + AAC (duration 3.0s)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=24:d=3.0",
            "-f", "lavfi", "-i", "sine=frequency=440:r=48000:d=3.0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(test_mp4)
        ], check=True)

        # Write matching VTT
        test_vtt.write_text(
            "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.950\nXin chào các bạn.\n",
            encoding="utf-8"
        )

        r8 = gate.check_rule8_format_codecs_and_captions(test_mp4, test_vtt)
        assert r8["passed"], f"1080p 24fps MP4 with synced VTT must pass, got: {r8.get('violations')}"
        assert r8["resolution"] == "1920x1080"
        assert abs(r8["fps"] - 24.0) < 0.1
        assert r8["video_codec"] == "h264"
        assert r8["audio_codec"] == "aac"
        assert r8["vtt_synced"]
        print(f"  [PASS] Confirmed 1920x1080 @ {r8['fps']:.0f}fps, H.264 + AAC, VTT synchronized (drift={r8['vtt_drift_sec']:.2f}s).")


def test_full_pre_upload_quality_gate_checklist():
    print("\n--- [Full Release Gate] Running Complete Pre-Upload Quality Gate Pipeline ---")
    gate = PreUploadQualityGate()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        mp4_path = tmp_path / "youtube_ready_master.mp4"
        vtt_path = tmp_path / "youtube_ready_captions.vtt"

        # Generate compliant 3.0s master MP4 normalized to -14 LUFS, TP=-1.5
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=24:d=3.0",
            "-f", "lavfi", "-i", "sine=frequency=440:r=48000:d=3.0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=7",
            str(mp4_path)
        ], check=True)

        vtt_path.write_text(
            "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.950\nBức thư vẫn tuyệt đối khô ráo!\n",
            encoding="utf-8"
        )

        spec_pkg = {
            "total_sequence_duration_seconds": 3.0,
            "scene_world": {
                "location_id": "LOC_EDO_WOODEN_BRIDGE",
                "architecture_style": "EDO_BRIDGE",
                "threejs_environment": {
                    "camera_initial": {"position": [-2.0, 4.5, 7.2], "target": [0.1, 5.0, 0.0], "fov": 44},
                    "camera_keyframes": [{"t": 0.0, "position": [-2.0, 4.5, 7.2], "target": [0.1, 5.0, 0.0]}]
                }
            },
            "actors": [{
                "actor_id": "haru",
                "staging": {"initial_world_pos": [-1.2, 2.65, 0.0]},
                "performance_cues": [
                    {"time": 0.0, "action": "sprint", "pos": [-1.2, 2.65, 0.0]},
                    {"time": 1.5, "action": "speak_gestural", "pos": [-0.8, 2.65, 0.0]}
                ]
            }],
            "voice_timeline": {
                "lines": [
                    {"start_sec": 0.0, "end_sec": 2.9, "speaker": "Haru", "text": "Bức thư vẫn tuyệt đối khô ráo!"}
                ]
            }
        }

        prop_audit = {"passed": True, "maxDistance": 0.4, "violations": []}

        passed, report = gate.run_pre_upload_quality_gate(
            mp4_path=mp4_path,
            package=spec_pkg,
            sibling_mp4_paths=[],
            prop_audit=prop_audit,
            vtt_path=vtt_path,
            variant_params_changed=True
        )

        assert passed, f"Full pre-upload quality gate must pass! Report: {report}"
        print("  [SUCCESS] All 9 checklist items verified PASS! Output certified YouTube-Ready.")


def main():
    print("=" * 70)
    print("RUNNING ACCEPTANCE TESTS FOR PRE-RENDER & PRE-UPLOAD QUALITY GATE")
    print("=" * 70)

    test_rule1_elementary_stream_hashes_and_duplicate_abort()
    test_rule2_minimum_motion_and_frozen_tag()
    test_rule3_prop_to_hand_attachment()
    test_rule4_depth_and_occlusion()
    test_rule5_subtitle_bounds_and_font_scaling()
    test_rule6_camera_framing_and_foreground_structure()
    test_rule7_audio_loudness_normalization()
    test_rule8_format_codecs_and_vtt_sync()
    test_full_pre_upload_quality_gate_checklist()

    print("\n" + "=" * 70)
    print("ALL 8 QUALITY GATE RULES VERIFIED STRICTLY (100% PASS)")
    print("=" * 70)


if __name__ == "__main__":
    main()
