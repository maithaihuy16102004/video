from __future__ import annotations
import unittest
from PIL import Image
from .contract import *
from .renderer import IntegratedSceneRenderer
from ..performance.engine import ActorIntent

def context():
    asset=AssetInstance('object_01','generic_support','MG',{'grip_anchor':[900,650]},{'GRIP':'grip_anchor'},'READY',[.43,.55,.52,.72])
    return SceneRenderContext('generic',CameraContext([1920,1080],'MEDIUM',.5,[.5,.5]),GroundPlane(.5),{'object_01':asset},LightingContext('LEFT_HIGH',.8,.4,'RIGHT',{'MG':1,'BG':.7},[.5,.6]),{'MG':.5,'BG':.75},eyeline_targets={'event_01':[1000,500]})

class IntegrationContractTests(unittest.TestCase):
    def test_shared_camera_ground(self): self.assertEqual(context().camera.horizon_y,context().ground_plane.horizon_y)
    def test_anchor_resolution(self): self.assertEqual(context().resolve({'asset_instance_id':'object_01','anchor':'grip_anchor'}),[900,650])
    def test_affordance_resolution(self): self.assertEqual(context().resolve_affordance('object_01','GRIP').anchor,'grip_anchor')
    def test_contact_target_backward_string(self): self.assertEqual(ContactTargetRef.parse('object_01.grip_anchor').asset_instance_id,'object_01')
    def test_eyeline_target(self): self.assertIn('event_01',context().eyeline_targets)
    def test_depth_assignment(self): self.assertEqual(context().depth_planes['MG'],.5)
    def test_semantic_occlusion(self):
        c=context(); c.occlusion.add('actor_01','BEHIND','object_01'); self.assertEqual(c.occlusion.edges[0].relation,'BEHIND')
    def test_object_state_sync(self):
        c=context(); i=ActorIntent('a','GRIP',[.4,.7],.8,.9,'object_01',orientation='PROFILE_RIGHT',weight='FORWARD',contact_type='HAND_CONTACT'); _,_,d=IntegratedSceneRenderer().render(Image.new('RGBA',(1920,1080),'white'),[i],c); self.assertEqual(d['object_states']['object_01'],'READY')
    def test_lighting_transfer(self): self.assertEqual(context().lighting.key_intensity,.8)
    def test_fallback_without_world_context(self):
        i=ActorIntent('a','STAND',[.5,.7],.8,.9); out=IntegratedSceneRenderer().fallback_render(Image.new('RGBA',(1920,1080),'white'),[i]); self.assertEqual(out.size,(1920,1080))
    def test_fallback_without_advanced_actor_data(self):
        c=context(); i=ActorIntent('a','STAND',[.5,.7],.8,.9); out,actors,_=IntegratedSceneRenderer().render(Image.new('RGBA',(1920,1080),'white'),[i],c); self.assertEqual(len(actors),1)

if __name__=='__main__': unittest.main()
