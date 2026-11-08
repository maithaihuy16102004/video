
from manim import *

class DataRevealScene(Scene):
    CONFIG_NUMBER = 50
    CONFIG_LABEL = "Sức mạnh của Trật tự Tưởng tượng"
    CONFIG_UNIT = " người"
    CONFIG_COLOR = "#00BFFF"
    
    def construct(self):
        self.camera.background_color = BLACK
        
        label_txt = Text(self.CONFIG_LABEL, font_size=36, color=LIGHT_GREY)
        label_txt.to_edge(UP, buff=1)
        
        num_display = Integer(0, font_size=120, color=self.CONFIG_COLOR)
        unit_txt = Text(self.CONFIG_UNIT, font_size=48, color=self.CONFIG_COLOR)
        unit_txt.next_to(num_display, RIGHT, buff=0.2)
        
        self.add(label_txt)
        self.play(
            ChangeDecimalToValue(num_display, self.CONFIG_NUMBER, run_time=2.5),
        )
        self.play(Write(unit_txt))
        self.wait(1.5)
