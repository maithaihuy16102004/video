
from manim import *

class ImpactFlashScene(Scene):
    CONFIG_TEXT = "BƯỚC NHẢY 2: ĐỊNH CƯ"
    CONFIG_COLOR = "#FF4444"
    
    def construct(self):
        self.camera.background_color = BLACK
        
        # Flash trắng
        flash_rect = Rectangle(
            width=16, height=9, fill_color=WHITE, fill_opacity=1
        ).set_stroke(width=0)
        
        # Text cú đấm
        impact = Text(self.CONFIG_TEXT, font_size=72, color=self.CONFIG_COLOR,
                      weight=BOLD)
        
        self.play(FadeIn(flash_rect, run_time=0.08))
        self.play(FadeOut(flash_rect, run_time=0.3))
        self.play(
            GrowFromCenter(impact, run_time=0.5),
        )
        self.play(impact.animate.scale(1.15).set_opacity(0.6), run_time=0.4)
        self.wait(1.0)
        self.play(FadeOut(impact))
