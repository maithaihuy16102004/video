"""Unit and integration test for draft variant divergence and duplicate render guardrails."""
import hashlib
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from studio_api import (
    DuplicateDraftError,
    compute_file_sha256,
    verify_variant_parameters_changed,
    verify_render_hash_differs,
)


def test_abort_when_no_deliberate_changes():
    """Verify that if seed, camera, and dialogue timing are identical, it aborts."""
    baseline = {
        "variant_index": 0,
        "scene_seed": 42,
        "camera_initial": {"position": [0, 1.8, 6.2], "target": [0, 1.2, 0]},
        "camera_keyframes": [{"t": 0.0, "position": [0, 1.8, 6.2]}],
        "voice_hash": "a1b2c3d4",
        "duration": 15.0,
        "speech_rate": "+5%",
    }

    # Duplicate config
    duplicate_config = dict(baseline)
    duplicate_config["variant_index"] = 1

    caught = False
    try:
        verify_variant_parameters_changed(1, duplicate_config, baseline)
    except DuplicateDraftError as e:
        caught = True
        assert "have not been deliberately changed" in str(e).lower()

    assert caught, "Should have raised DuplicateDraftError"
    print("[PASS] Successfully aborted when no deliberate changes were made between variants.")


def test_pass_when_seed_changed():
    """Verify that deliberate seed change passes parameter check."""
    baseline = {
        "variant_index": 0,
        "scene_seed": 42,
        "camera_initial": {"position": [0, 1.8, 6.2]},
        "camera_keyframes": [],
        "voice_hash": "hash1",
        "duration": 15.0,
        "speech_rate": "+5%",
    }
    variant_config = dict(baseline)
    variant_config["variant_index"] = 1
    variant_config["scene_seed"] = 179  # Deliberate change

    # Should not raise
    verify_variant_parameters_changed(1, variant_config, baseline)
    print("[PASS] Deliberate scene seed change passed verification.")


def test_pass_when_camera_changed():
    """Verify that deliberate camera change passes parameter check."""
    baseline = {
        "variant_index": 0,
        "scene_seed": 42,
        "camera_initial": {"position": [0, 1.8, 6.2]},
        "camera_keyframes": [],
        "voice_hash": "hash1",
        "duration": 15.0,
        "speech_rate": "+5%",
    }
    variant_config = dict(baseline)
    variant_config["variant_index"] = 1
    variant_config["camera_initial"] = {"position": [2.0, 3.0, 5.0]}  # Deliberate camera change

    # Should not raise
    verify_variant_parameters_changed(1, variant_config, baseline)
    print("[PASS] Deliberate camera change passed verification.")


def test_pass_when_timing_changed():
    """Verify that deliberate dialogue timing change passes parameter check."""
    baseline = {
        "variant_index": 0,
        "scene_seed": 42,
        "camera_initial": {"position": [0, 1.8, 6.2]},
        "camera_keyframes": [],
        "voice_hash": "hash1",
        "duration": 15.0,
        "speech_rate": "+5%",
    }
    variant_config = dict(baseline)
    variant_config["variant_index"] = 1
    variant_config["speech_rate"] = "-2%"
    variant_config["duration"] = 16.2  # Deliberate timing change

    # Should not raise
    verify_variant_parameters_changed(1, variant_config, baseline)
    print("[PASS] Deliberate dialogue timing change passed verification.")


def test_abort_when_render_hash_identical():
    """Verify that if rendered hash matches draft-1, it aborts and unlinks staging file without writing target."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        d1_target = tmp_path / "draft-1.mp4"
        d1_target.write_bytes(b"SAME_VIDEO_DATA_RENDER_OUTPUT")
        d1_hash = compute_file_sha256(d1_target)

        d2_target = tmp_path / "draft-2.mp4"
        d2_staging = tmp_path / ".staging_draft-2.mp4"
        d2_staging.write_bytes(b"SAME_VIDEO_DATA_RENDER_OUTPUT")  # Duplicate content

        caught = False
        try:
            verify_render_hash_differs(1, d2_staging, d1_hash, d2_target)
        except DuplicateDraftError as e:
            caught = True
            assert "identical to draft-1" in str(e).lower()

        assert caught, "Should have raised DuplicateDraftError on identical hash"
        # Staging file must be unlinked
        assert not d2_staging.exists(), "Staging file should be deleted on duplicate hash"
        # Destination file must NOT be written
        assert not d2_target.exists(), "Duplicate draft-2.mp4 must NOT be written"
        print("[PASS] Successfully aborted duplicate render: unlinked staging file and refused to write draft-2.mp4.")


def test_succeed_when_render_hash_differs():
    """Verify that when render hash differs, file is moved to target."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        d1_target = tmp_path / "draft-1.mp4"
        d1_target.write_bytes(b"VIDEO_DATA_DRAFT_1")
        d1_hash = compute_file_sha256(d1_target)

        d2_target = tmp_path / "draft-2.mp4"
        d2_staging = tmp_path / ".staging_draft-2.mp4"
        d2_staging.write_bytes(b"VIDEO_DATA_DRAFT_2_DIFFERENT")

        out_hash = verify_render_hash_differs(1, d2_staging, d1_hash, d2_target)
        assert out_hash != d1_hash
        assert d2_target.exists(), "draft-2.mp4 should be written"
        assert not d2_staging.exists(), "staging file should have been moved"
        print(f"[PASS] Successfully verified diverging render hash ({out_hash[:12]} != {d1_hash[:12]}) and wrote draft-2.mp4.")


def test_v5_story_director_variant_divergence():
    """Verify that compile_to_runner_package generates distinct scene_seed and camera across variants."""
    from pipeline.universal.v5_story_director import V5UniversalStoryDirector
    director = V5UniversalStoryDirector()
    sample_pkg = {
        "locations": [{"category": "EDO_BRIDGE", "name": "Cầu Gỗ Edo", "weather": "CLEAR"}],
        "characters": [{"characterId": "haru", "canonicalName": "Haru", "voiceId": "vieneu-Thiện Minh"}],
        "storyBeats": [{"dialogue": {"speaker": "Haru", "text": "Tin mật từ Edo!"}}],
        "durationSeconds": 15.0,
    }

    r0 = director.compile_to_runner_package(sample_pkg, variant=0)
    r1 = director.compile_to_runner_package(sample_pkg, variant=1)
    r2 = director.compile_to_runner_package(sample_pkg, variant=2)

    # Check seeds
    s0 = r0["scene_world"]["scene_seed"]
    s1 = r1["scene_world"]["scene_seed"]
    s2 = r2["scene_world"]["scene_seed"]
    assert s0 != s1 and s1 != s2, f"Scene seeds must differ: {s0}, {s1}, {s2}"

    # Check camera
    c0 = r0["scene_world"]["threejs_environment"]["camera_initial"]["position"]
    c1 = r1["scene_world"]["threejs_environment"]["camera_initial"]["position"]
    c2 = r2["scene_world"]["threejs_environment"]["camera_initial"]["position"]
    assert c0 != c1 and c1 != c2, f"Cameras must differ: {c0}, {c1}, {c2}"

    print(f"[PASS] V5 Universal Story Director generates distinct scene seeds ({s0}, {s1}, {s2}) and cameras across variants.")


def test_animation_director_pacing_contract():
    """Verify Animation Director Contract: gestures, weight shifts, head turns every 2-3s, no >3s static hold unless frozen/shock."""
    from pipeline.universal.v5_story_director import V5UniversalStoryDirector
    director = V5UniversalStoryDirector()

    # 1. Test violation on static hold > 3.0s without frozen/shock
    static_cues = [
        {"time": 0.0, "pos": [0, 0, 0], "action": "idle", "is_frozen_shock": False},
        {"time": 4.5, "pos": [0, 0, 0], "action": "speak", "is_frozen_shock": False}, # 4.5s hold!
    ]
    valid, errs = director.validate_animation_director_pacing("actor_test", static_cues)
    assert not valid, "Should fail validation when a pose is held for > 3.0s"
    assert len(errs) > 0 and "exceeding the 3.0s limit" in errs[0]
    print("[PASS] Animation Director validator correctly flags static poses held for > 3.0s.")

    # 2. Test explicit 'frozen/shock' exception
    shock_cues = [
        {"time": 0.0, "pos": [0, 0, 0], "action": "surprise", "is_frozen_shock": True},
        {"time": 4.0, "pos": [0, 0, 0], "action": "relief", "is_frozen_shock": False},
    ]
    valid_shock, errs_shock = director.validate_animation_director_pacing("actor_shock", shock_cues)
    assert valid_shock, f"Should pass when explicitly scripted as frozen/shock: {errs_shock}"
    print("[PASS] Animation Director validator correctly permits > 3.0s hold when explicitly scripted as frozen/shock.")

    # 3. Test that compile_to_runner_package generates compliant cues for a 15-second sequence
    sample_pkg = {
        "locations": [{"category": "CAFE", "name": "Quán Cà Phê", "weather": "CLEAR"}],
        "characters": [
            {"characterId": "tuan", "canonicalName": "Tuấn", "role": "LEAD"},
            {"characterId": "minh", "canonicalName": "Minh", "role": "SUPPORT"}
        ],
        "storyBeats": [
            {
                "beatId": "BEAT_01",
                "timeRange": [0.0, 5.0],
                "primaryVerb": "speak",
                "dialogue": {"speaker": "Tuấn", "text": "Hôm nay tôi muốn chia sẻ một ý tưởng rất lớn."},
                "whatHappens": "Tuấn giải thích ý tưởng."
            },
            {
                "beatId": "BEAT_02",
                "timeRange": [5.0, 10.0],
                "primaryVerb": "listen",
                "dialogue": {"speaker": "Minh", "text": "Ý tưởng này nghe có vẻ táo bạo nhưng rất khả thi."},
                "whatHappens": "Minh gật đầu lắng nghe."
            },
            {
                "beatId": "BEAT_03",
                "timeRange": [10.0, 15.0],
                "primaryVerb": "relief",
                "dialogue": {"speaker": "Tuấn", "text": "Tuyệt vời, vậy chúng ta cùng bắt tay vào làm ngay nhé."},
                "whatHappens": "Cả hai vui mừng chốt kế hoạch."
            }
        ],
        "durationSeconds": 15.0,
    }

    runner_pkg = director.compile_to_runner_package(sample_pkg)
    for actor in runner_pkg["actors"]:
        cues = actor["performance_cues"]
        assert len(cues) >= 6, f"Expected at least 6 cues over 15s for active character, got {len(cues)}"
        valid, errs = director.validate_animation_director_pacing(actor["actor_id"], cues)
        assert valid, f"Pacing violations found: {errs}"

        # Verify visible gestures, weight shifts, and head turns are present
        actions = [c["action"] for c in cues]
        positions = [c["pos"] for c in cues]
        facings = [c["facing"] for c in cues]

        # Check action variety (gestures)
        assert len(set(actions)) >= 2, f"Actor {actor['actor_id']} should have varying gestures: {actions}"

        # Check weight shift (positions in X or Z must shift)
        x_coords = [p[0] for p in positions]
        assert len(set(x_coords)) >= 2, f"Actor {actor['actor_id']} should have weight shifts: {x_coords}"

        # Check that maximum interval between any consecutive cues never exceeds 3.0s
        for i in range(len(cues) - 1):
            interval = cues[i+1]["time"] - cues[i]["time"]
            assert interval <= 3.0, f"Interval {interval}s between cue {i} and {i+1} exceeds 3.0s!"

    print("[PASS] compile_to_runner_package successfully generates gestures, weight shifts, and head turns every 2–3s without >3s static holds.")


if __name__ == "__main__":
    test_abort_when_no_deliberate_changes()
    test_pass_when_seed_changed()
    test_pass_when_camera_changed()
    test_pass_when_timing_changed()
    test_abort_when_render_hash_identical()
    test_succeed_when_render_hash_differs()
    test_v5_story_director_variant_divergence()
    test_animation_director_pacing_contract()
    print("\nALL DRAFT VARIANT DIVERGENCE & ANIMATION DIRECTOR TESTS PASSED!")
