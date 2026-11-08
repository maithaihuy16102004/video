from __future__ import annotations
import unittest
from .assets.asset_resolver import UniversalAssetResolver
from .schemas import AssetRequirement,StoryBeat
from .director.cinematic_director import CinematicDirector

class SemanticAssetTests(unittest.TestCase):
    def setUp(self): self.r=UniversalAssetResolver()
    def resolve(self,semantic,category): return self.r.resolve(AssetRequirement(requirement_id='x',semantic=semantic,category=category))
    def test_wire_cannot_be_bed(self): self.assertNotIn('bed',self.resolve('barbed wire','WIRE').asset_id.lower())
    def test_weapon_cannot_be_chair(self): self.assertNotIn('chair',self.resolve('rifle','WEAPON').asset_id.lower())
    def test_vehicle_cannot_be_table(self): self.assertNotIn('table',self.resolve('motor vehicle','VEHICLE').asset_id.lower())
    def test_bed_cannot_be_lamp(self): self.assertNotIn('lamp',self.resolve('hospital bed','BED').asset_id.lower())
    def test_unknown_returns_gap(self): self.assertEqual(self.resolve('orbital quantum loom','VEHICLE').status,'ASSET_GAP')
    def test_exact_outweighs_material(self): self.assertIn('bed',self.resolve('bed','BED').asset_id.lower())

class VisualIntentTests(unittest.TestCase):
    def test_visual_question_generation(self):
        b=StoryBeat(beat_id='b',index=0,text='A door opens',objects=['door'],suggested_purpose='REVEAL')
        q,a=CinematicDirector._derive_visual_intent(b,'REVEAL'); self.assertTrue(q and a)
    def test_reasons_exist(self):
        b=StoryBeat(beat_id='b',index=0,text='Run',actions=[],suggested_purpose='ACTION')
        self.assertTrue(CinematicDirector._camera_reason('ACTION',b)); self.assertTrue(CinematicDirector._cut_reason(b,0))
    def test_energy(self): self.assertEqual(CinematicDirector._energy(StoryBeat(beat_id='b',index=0,text='x',tension=.9)),'HIGH')

if __name__=='__main__': unittest.main()
