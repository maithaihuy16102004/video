from manim import *

class TimelineScene(Scene):
    def construct(self):
        # Tiêu đề
        title = Text("3 Cột Mốc Lịch Sử", font_size=40, color=YELLOW)
        title.to_edge(UP)
        self.play(Write(title))

        # Dòng thời gian
        line = NumberLine(
            x_range=[0, 3, 1],
            length=8,
            color=BLUE,
            include_numbers=False,
        )
        self.play(Create(line))

        labels = ["70.000 năm", "12.000 năm", "500 năm"]
        milestones = ["Nhận thức", "Nông nghiệp", "Khoa học"]

        for i, (yr, ms) in enumerate(zip(labels, milestones)):
            pos = line.n2p(i)
            dot = Dot(pos, color=RED, radius=0.15)
            t1 = Text(yr, font_size=20, color=WHITE).next_to(dot, UP)
            t2 = Text(ms, font_size=24, color=GOLD).next_to(dot, DOWN)
            self.play(FadeIn(dot), Write(t1), Write(t2), run_time=0.8)

        self.wait(1)
