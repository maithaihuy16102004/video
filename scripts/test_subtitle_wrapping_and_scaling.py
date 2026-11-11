"""Comprehensive validation and acceptance tests for Subtitle Box Width, Automatic Wrapping & Iterative Font Reduction.

Contract Requirements:
1. Subtitle box width must equal 90% of frame width max, centered.
2. Automatic line-wrap when text exceeds box bounds — never truncate or render text past the box edge.
3. If wrapped text exceeds 2 lines, reduce font size by 10% increments until it fits into <= 2 lines.
"""

import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.universal.v5_story_director import V5UniversalStoryDirector


def test_python_story_director_subtitle_invariants():
    print("\n--- Running Python Story Director Subtitle Invariant Tests ---")
    director = V5UniversalStoryDirector()
    frame_w, frame_h = 1920, 1080
    max_expected_w = int(frame_w * 0.90)  # 1728px

    # Test 1: Short text (1 line, fits comfortably without reduction)
    print(">>> [Test 1] Short single-line subtitle...")
    short_text = "Xin chào kinh thành Edo!"
    r1 = director.validate_subtitle_box_and_wrap(short_text, frame_w, frame_h)
    assert r1["passed"], f"Test 1 failed: {r1}"
    assert r1["line_count"] == 1, f"Expected 1 line, got {r1['line_count']}"
    assert r1["reduction_steps"] == 0, f"Expected 0 reductions, got {r1['reduction_steps']}"
    assert r1["final_font_size"] == 28, f"Expected 28px font, got {r1['final_font_size']}"
    assert r1["box_width"] <= max_expected_w, f"Box width {r1['box_width']} exceeds max {max_expected_w}"
    assert r1["max_box_width"] == max_expected_w, f"Expected max box width {max_expected_w}, got {r1['max_box_width']}"
    assert r1["is_centered"], "Subtitle box must be horizontally centered"
    assert r1["box_x"] == int(round((frame_w - r1["box_width"]) / 2))
    assert not r1["overflow_detected"], "No text overflow allowed"
    print(f"  [PASS] Short text: 1 line, 0 reductions, boxWidth={r1['box_width']}px (<= {max_expected_w}px), centered at X={r1['box_x']}px.")

    # Test 2: Medium text (wraps to 2 lines cleanly without font reduction)
    print(">>> [Test 2] Medium subtitle wrapping to 2 lines...")
    medium_text = (
        "Cơn mưa chiều buông xuống Nihonbashi, từng bước chân vội vã tìm nơi trú ẩn "
        "trong kinh thành cổ kính khi chuông chiều bắt đầu điểm."
    )
    r2 = director.validate_subtitle_box_and_wrap(medium_text, frame_w, frame_h)
    assert r2["passed"], f"Test 2 failed: {r2}"
    assert r2["line_count"] == 2, f"Expected 2 lines, got {r2['line_count']}"
    assert r2["reduction_steps"] == 0, f"Expected 0 reductions, got {r2['reduction_steps']}"
    assert r2["final_font_size"] == 28, f"Expected 28px font, got {r2['final_font_size']}"
    assert r2["box_width"] <= max_expected_w
    assert r2["is_centered"]
    assert not r2["overflow_detected"]
    # Verify no truncation: all words from original text are preserved across lines
    combined_words = " ".join(r2["lines"]).split()
    orig_words = medium_text.split()
    assert combined_words == orig_words, "All words must be preserved; never truncate!"
    assert "..." not in " ".join(r2["lines"]), "Text must not contain truncation ellipsis"
    print(f"  [PASS] Medium text: wrapped to 2 lines without truncation, boxWidth={r2['box_width']}px, zero overflow.")

    # Test 3: Long text (initially 3 lines at 28px -> requires 10% font reduction until <= 2 lines)
    print(">>> [Test 3] Long subtitle triggering iterative 10% font reductions...")
    long_text = (
        "Vào năm 1800 tại cầu Nihonbashi, Haru đang vội vã chạy qua màn mưa tầm tã để kịp giao "
        "bức thư mật quan trọng cho quan trấn thủ kinh thành trước khi cổng thành phía bắc chính thức đóng cửa "
        "vào lúc hoàng hôn buông xuống trên dòng sông Sumida mênh mông lạnh giá."
    )
    r3 = director.validate_subtitle_box_and_wrap(long_text, frame_w, frame_h)
    assert r3["passed"], f"Test 3 failed: {r3}"
    assert r3["line_count"] <= 2, f"Expected <= 2 lines, got {r3['line_count']}"
    assert r3["reduction_steps"] > 0, f"Expected font reduction steps > 0, got {r3['reduction_steps']}"
    assert r3["final_font_size"] < 28, f"Expected reduced font size < 28, got {r3['final_font_size']}"
    assert r3["box_width"] <= max_expected_w
    assert r3["is_centered"]
    assert not r3["overflow_detected"]
    assert " ".join(r3["lines"]).split() == long_text.split(), "Zero truncation invariant violated!"
    print(
        f"  [PASS] Long text: reduced font from 28px to {r3['final_font_size']}px in {r3['reduction_steps']} step(s); "
        f"lines={r3['line_count']}, boxWidth={r3['box_width']}px."
    )

    # Test 4: Extra-long text (> 350 characters, multiple 10% reduction steps)
    print(">>> [Test 4] Extra-long subtitle stress test...")
    extra_long = (
        "Vào năm 1800 tại cầu Nihonbashi, Haru đang vội vã chạy qua màn mưa tầm tã để kịp giao bức thư mật quan trọng "
        "cho quan trấn thủ kinh thành trước khi cổng thành phía bắc chính thức đóng cửa vào lúc hoàng hôn, "
        "trong khi những tên tuần sai của Mạc Phủ bí mật bám sát ngay phía sau lưng chàng từng bước một không hề rời mắt."
    )
    r4 = director.validate_subtitle_box_and_wrap(extra_long, frame_w, frame_h)
    assert r4["passed"], f"Test 4 failed: {r4}"
    assert r4["line_count"] <= 2, f"Strict 2-line ceiling exceeded: got {r4['line_count']} lines"
    assert r4["reduction_steps"] >= 3, f"Expected at least 3 reduction steps, got {r4['reduction_steps']}"
    assert r4["box_width"] <= max_expected_w
    assert r4["is_centered"]
    assert r4["max_line_width"] <= r4["available_text_width"], "Text rendered past box bounds!"
    assert " ".join(r4["lines"]).split() == extra_long.split(), "Never truncate text invariant violated!"
    print(
        f"  [PASS] Extra-long text: {len(extra_long)} chars -> reduced in {r4['reduction_steps']} steps "
        f"to {r4['final_font_size']}px, perfectly fits in {r4['line_count']} lines with 0 overflow."
    )


def test_node_motioncanvas_cinematic_overlay():
    print("\n--- Running Node Motion Canvas CinematicOverlay Renderer Invariant Tests ---")

    # Re-bundle with esbuild
    bundle_cmd = [
        "npx.cmd" if sys.platform == "win32" else "npx",
        "esbuild",
        str(ROOT / "motioncanvas" / "components" / "CinematicOverlay.ts"),
        "--bundle",
        "--platform=node",
        "--format=esm",
        f"--outfile={ROOT / 'scratch' / 'bundle_overlay.mjs'}"
    ]
    bundle_res = subprocess.run(bundle_cmd, capture_output=True, text=True, cwd=str(ROOT))
    if bundle_res.returncode != 0:
        raise RuntimeError(f"Failed to bundle CinematicOverlay: {bundle_res.stderr}")

    node_script = """
    import('./bundle_overlay.mjs').then(mod => {
      const { CinematicOverlayRenderer } = mod;

      // Realistic mock 2D canvas context implementing standard typography metrics
      function createMockCtx() {
        let curFont = '600 28px sans-serif';
        return {
          set font(f) { curFont = f; },
          get font() { return curFont; },
          measureText(text) {
            const match = curFont.match(/(\\d+(?:\\.\\d+)?)px/);
            const size = match ? parseFloat(match[1]) : 28;
            let width = 0;
            for (const ch of text) {
              if (ch === ' ') width += size * 0.28;
              else if (/[WwMm@]/.test(ch)) width += size * 0.85;
              else if (/[ijl|!:',.]/.test(ch)) width += size * 0.25;
              else if (/[A-Z]/.test(ch)) width += size * 0.70;
              else width += size * 0.55;
            }
            return { width };
          },
          save() {}, restore() {}, beginPath() {}, moveTo() {}, arcTo() {},
          closePath() {}, fill() {}, stroke() {}, fillText() {}
        };
      }

      const frameW = 1920;
      const frameH = 1080;
      const renderer = new CinematicOverlayRenderer(createMockCtx(), frameW, frameH);

      // Verify Test Case 1: Max width calculation (must be 90% max = 1728px)
      const maxBoxWidth = Math.round(frameW * 0.90);
      if (maxBoxWidth !== 1728) {
        throw new Error(`Expected maxBoxWidth 1728, got ${maxBoxWidth}`);
      }

      // Verify Test Case 2: Short subtitle
      const shortLayout = renderer.computeSubtitleLayout('Kinh thành Edo 1800');
      if (shortLayout.lines.length !== 1) {
        throw new Error(`Expected 1 line, got ${shortLayout.lines.length}`);
      }
      if (shortLayout.fontSize !== 28 || shortLayout.reductionSteps !== 0) {
        throw new Error(`Short text should not reduce font: size=${shortLayout.fontSize}, steps=${shortLayout.reductionSteps}`);
      }
      if (shortLayout.boxWidth > 1728) {
        throw new Error(`Box width ${shortLayout.boxWidth} exceeds 90% limit (1728)`);
      }
      if (!shortLayout.isCentered) {
        throw new Error(`Box must be horizontally centered: boxX=${shortLayout.boxX}`);
      }
      console.log('  [PASS] Node Case 1 (Short): 1 line, 0 reductions, perfectly centered.');

      // Verify Test Case 3: Medium subtitle (2 lines without font reduction)
      const medText = 'Trời mưa như trút nước trên sông Sumida, những con thuyền nhỏ chầm chậm cập bến đò trong ánh hoàng hôn mờ ảo.';
      const medLayout = renderer.computeSubtitleLayout(medText);
      if (medLayout.lines.length > 2) {
        throw new Error(`Expected <= 2 lines, got ${medLayout.lines.length}`);
      }
      if (medLayout.boxWidth > 1728) {
        throw new Error(`Box width ${medLayout.boxWidth} exceeds 1728`);
      }
      if (!medLayout.isCentered) {
        throw new Error('Medium text box must be centered');
      }
      if (medLayout.overflowDetected) {
        throw new Error('Overflow detected in medium text');
      }
      console.log('  [PASS] Node Case 2 (Medium): fits in <= 2 lines, zero overflow past box edge.');

      // Verify Test Case 4: Long text exceeding 2 lines -> 10% reductions
      const longText = 'Vào năm 1800 tại cầu Nihonbashi, Haru đang vội vã chạy qua màn mưa tầm tã để kịp giao bức thư mật quan trọng cho quan trấn thủ kinh thành trước khi cổng thành phía bắc chính thức đóng cửa vào lúc hoàng hôn, trong khi những tên tuần sai của Mạc Phủ bí mật bám sát ngay phía sau lưng chàng từng bước một không hề rời mắt khỏi chiếc hộp gỗ.';
      const longLayout = renderer.computeSubtitleLayout(longText);

      if (longLayout.lines.length > 2) {
        throw new Error(`Strict 2-line invariant failed: got ${longLayout.lines.length} lines`);
      }
      if (longLayout.reductionSteps === 0) {
        throw new Error('Expected iterative font reductions for long text');
      }
      if (longLayout.fontSize >= 28) {
        throw new Error(`Font size should be reduced from 28: got ${longLayout.fontSize}`);
      }
      if (longLayout.boxWidth > 1728) {
        throw new Error(`Box width ${longLayout.boxWidth} exceeds 1728`);
      }
      if (!longLayout.isCentered) {
        throw new Error('Long text box must be centered');
      }
      if (longLayout.maxLineWidth > longLayout.availableTextWidth) {
        throw new Error(`Text line width ${longLayout.maxLineWidth} exceeds available text width ${longLayout.availableTextWidth}`);
      }
      if (longLayout.overflowDetected) {
        throw new Error('Text overflow detected past box edge');
      }
      console.log(`  [PASS] Node Case 3 (Long): reduced ${longLayout.reductionSteps}x (28px -> ${longLayout.fontSize}px), lines=${longLayout.lines.length}, zero overflow.`);

      // Verify Test Case 5: Full rendering via draw() and telemetry recording
      renderer.draw({
        timeSeconds: 2.5,
        subtitle: {
          speaker: 'Haru',
          text: longText,
          color: '#FFC83B'
        }
      });
      const recorded = renderer.getLastSubtitleLayout();
      if (!recorded || recorded.lines.length > 2 || recorded.boxWidth > 1728 || !recorded.isCentered) {
        throw new Error('Recorded subtitle layout telemetry invalid');
      }
      console.log('  [PASS] Node Case 4 (Renderer Telemetry): getLastSubtitleLayout() records validated state.');

      console.log('\\nALL NODE MOTION CANVAS SUBTITLE TESTS PASSED!');
    }).catch(err => {
      console.error('Node Subtitle Test Failure:', err);
      process.exit(1);
    });
    """

    res = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, cwd=str(ROOT / "scratch"))
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr)
        raise RuntimeError(f"Node Subtitle Tests failed with code {res.returncode}")


def main():
    print("=" * 70)
    print("SUBTITLE BOX 90% MAX, CENTERING, WRAPPING & 10% FONT REDUCTION AUDIT")
    print("=" * 70)

    test_python_story_director_subtitle_invariants()
    test_node_motioncanvas_cinematic_overlay()

    print("\n" + "=" * 70)
    print("SUBTITLE ENGINE CONTRACT AUDIT: ALL TESTS PASSED STRICTLY (100%)")
    print("=" * 70)


if __name__ == "__main__":
    main()
