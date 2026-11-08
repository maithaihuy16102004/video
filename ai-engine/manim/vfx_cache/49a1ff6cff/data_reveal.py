
from manim import *

class DataRevealScene(Scene):
    CONFIG_NUMBER = 8000000000
    CONFIG_LABEL = "Dân số"
    CONFIG_UNIT = "người"
    CONFIG_COLOR = "#FFD700"
    
    def construct(self):
        self.camera.background_color = BLACK
        
        label_txt = Text(self.CONFIG_LABEL, font_size=36, color=LIGHT_GREY)
        label_txt.to_edge(UP, buff=1)
        
        num_str = f"{self.CONFIG_NUMBER:,}"
        num_display = Text(num_str, font_size=72, color=self.CONFIG_COLOR, weight=BOLD)
        unit_txt = Text(self.CONFIG_UNIT, font_size=36, color=self.CONFIG_COLOR)
        unit_txt.next_to(num_display, RIGHT, buff=0.2)
        group = VGroup(num_display, unit_txt)
        group.move_to(ORIGIN)
        
        self.add(label_txt)
        self.play(
            GrowFromCenter(group, run_time=1.5),
        )
        self.wait(1.5)
