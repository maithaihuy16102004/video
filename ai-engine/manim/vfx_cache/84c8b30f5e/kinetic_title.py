
from manim import *

class KineticTitleScene(Scene):
    CONFIG_TITLE = "Khởi đầu yếu ớt"
    CONFIG_SUBTITLE = "Cách đây 70 nghìn năm, tổ tiên chúng ta, loài Homo"
    CONFIG_COLOR = "#FFD700"
    
    def construct(self):
        self.camera.background_color = BLACK
        
        title = Text(self.CONFIG_TITLE, font_size=64, color=self.CONFIG_COLOR,
                     weight=BOLD).scale(0.8)
        subtitle = Text(self.CONFIG_SUBTITLE, font_size=28, color=LIGHT_GREY).scale(0.7)
        subtitle.next_to(title, DOWN, buff=0.3)
        
        # Hiệu ứng glow (nhân bản mờ)
        glow = title.copy().set_opacity(0.3).scale(1.08)
        
        # Animation
        self.play(
            FadeIn(glow, scale=0.5),
            Write(title, run_time=1.2),
        )
        self.play(FadeIn(subtitle, shift=UP*0.3), run_time=0.8)
        self.wait(1.5)
        self.play(FadeOut(VGroup(title, subtitle, glow), shift=UP*0.5))
