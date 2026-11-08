import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ricks_dynamic_pipeline import compile_timeline, parse_sfx_trigger, primary_emotion, validate_timeline

def scene(end=2.5):
    return {"scene_id":"scene_001","timestamp":{"start":0.0,"end":end},"narrative":{"text":"Một câu thoại.","voice_profile":"narrator","emotion_tagging":"[urgent][intrigued]"},"charmotion":{"avatar_id":"hero","pipeline":"LivePortrait","motion_intensity":0.8,"driving_video_ref":"assets/driving/hero.mp4"},"visual_composition":{"b_roll_source":"assets/broll/demo.mp4","screen_effect":"dolly_in","subtitle_style":"bold"},"audio_dynamics":{"bgm_track":"assets/bgm/demo.mp3","ducking_level":0.2,"sfx_triggers":["f+12:whoosh.wav"]}}

class Tests(unittest.TestCase):
    def test_contract_rejects_slideshow(self):
        result=compile_timeline([scene()]); self.assertFalse(result["render_contract"]["static_portrait_fallback_allowed"])
    def test_scene_limit(self):
        self.assertTrue(any("<=3.0" in error for error in validate_timeline([scene(3.1)])))
    def test_sfx_frame(self):
        self.assertEqual(parse_sfx_trigger("f+12:whoosh.wav",2.0).frame,72)
    def test_emotion(self):
        self.assertEqual(primary_emotion("[calm][whisper]"),"neutral")

if __name__ == "__main__": unittest.main()
