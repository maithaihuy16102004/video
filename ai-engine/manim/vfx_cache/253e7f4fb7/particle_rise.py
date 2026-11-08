
from manim import *
import random

class ParticleRiseScene(Scene):
    CONFIG_COLOR = "#FFFFFF"
    
    def construct(self):
        self.camera.background_color = BLACK
        
        dots = VGroup()
        anims = []
        for _ in range(60):
            x = random.uniform(-6, 6)
            y_start = random.uniform(-4, -2)
            y_end = random.uniform(2, 5)
            size = random.uniform(0.03, 0.12)
            d = Dot([x, y_start, 0], radius=size, color=self.CONFIG_COLOR)
            d.set_opacity(random.uniform(0.4, 1.0))
            dots.add(d)
            anims.append(d.animate(run_time=random.uniform(1.5, 3.0)).move_to([x, y_end, 0]).set_opacity(0))
        
        self.add(dots)
        self.play(*anims, lag_ratio=0.03)
        self.wait(0.5)
