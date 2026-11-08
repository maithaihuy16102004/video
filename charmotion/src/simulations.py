"""
Simulation Engine — Module vẽ mô phỏng trực quan các thực thể:
1. Cây lúa mì & Nông nghiệp (Golden Wheat Stalks & Fields)
2. Robot công nghệ cao & Kỷ nguyên AI (Futuristic Humanoid Robot)
3. Mạng nơ-ron thần kinh nhân tạo & Vi mạch (Neural Network & Chip AI)
4. Bếp lửa trại bập bùng & Than hồng (Campfire & Embers)
5. Hệ thống bánh răng công nghiệp & Khói nhà máy (Meshed Industrial Gears & Steam)
6. Tên lửa vũ trụ & Khói phản lực (Space Rocket & Cosmic Orbit)
"""

import math
from PIL import ImageDraw


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _lerp(a, b, t):
    return a + (b - a) * t


# ===========================================================================
# 1. CÂY LÚA MÌ & NÔNG NGHIỆP (WHEAT FIELD & GRAIN SIMULATION)
# ===========================================================================

def draw_wheat_field(draw: ImageDraw.ImageDraw, cx: float, cy: float, scale: float, t: float, grow: float = 1.0):
    """
    Vẽ chùm lúa mì vàng óng đung đưa trong gió + các hạt lúa + râu lúa + ánh nắng.
    cx, cy: vị trí gốc bụi lúa. scale: kích thước chiều cao (px). grow: 0..1 (quá trình lớn lên).
    """
    grow = _clamp(grow, 0.05, 1.0)
    h_actual = scale * grow

    # Gốc đất phì nhiêu
    draw.ellipse([cx - scale * 0.7, cy - scale * 0.08, cx + scale * 0.7, cy + scale * 0.12], fill=(60, 42, 28))

    # Vẽ 3 nhánh lúa mì: nhánh giữa, nhánh trái, nhánh phải
    stalks = [
        {"bend_factor": 0.0, "lean": 0.0, "phase": 0.0, "grain_scale": 1.0, "h_mult": 1.0},
        {"bend_factor": -0.22, "lean": -scale * 0.25, "phase": 0.8, "grain_scale": 0.85, "h_mult": 0.88},
        {"bend_factor": 0.22, "lean": scale * 0.25, "phase": 1.6, "grain_scale": 0.85, "h_mult": 0.88},
    ]

    for s in stalks:
        wind = math.sin(t * 3.0 + s["phase"]) * scale * 0.08
        tip_x = cx + s["lean"] + wind + s["bend_factor"] * scale * 0.3
        tip_y = cy - h_actual * s["h_mult"]

        ctrl_x = cx + (s["lean"] + wind) * 0.4
        ctrl_y = cy - h_actual * 0.5

        # Thân cây lúa (stalk) dạng đường cong mượt mà
        stem_pts = []
        steps = 15
        for i in range(steps + 1):
            p = i / steps
            # Bezier bậc 2
            bx = (1 - p)**2 * cx + 2 * (1 - p) * p * ctrl_x + p**2 * tip_x
            by = (1 - p)**2 * cy + 2 * (1 - p) * p * ctrl_y + p**2 * tip_y
            stem_pts.append((bx, by))

        # Màu thân lúa vàng óng / xanh non pha vàng
        stem_col = (220, 180, 50)
        for i in range(len(stem_pts) - 1):
            draw.line([stem_pts[i], stem_pts[i + 1]], fill=stem_col, width=int(max(2, 5 * scale / 250)))

        # Bông lúa mì (Wheat Ear / Head) ở nửa trên
        # Gồm 10-14 hạt lúa xếp so le hai bên
        num_grains = 12
        ear_start_p = 0.45  # bắt đầu từ 45% chiều cao thân cây
        for g_idx in range(num_grains):
            gp = ear_start_p + (1.0 - ear_start_p) * (g_idx / num_grains)
            # Tọa độ tâm đốt lúa
            gx = (1 - gp)**2 * cx + 2 * (1 - gp) * gp * ctrl_x + gp**2 * tip_x
            gy = (1 - gp)**2 * cy + 2 * (1 - gp) * gp * ctrl_y + gp**2 * tip_y

            # Tiếp tuyến hướng lên
            tangent_dx = 2 * (1 - gp) * (ctrl_x - cx) + 2 * gp * (tip_x - ctrl_x)
            tangent_dy = 2 * (1 - gp) * (ctrl_y - cy) + 2 * gp * (tip_y - ctrl_y)
            ang = math.atan2(tangent_dy, tangent_dx)

            # Vẽ 2 hạt hai bên (trái & phải)
            side = -1 if g_idx % 2 == 0 else 1
            grain_ang = ang + side * math.radians(45)

            grain_len = scale * 0.08 * s["grain_scale"] * grow
            grain_wid = grain_len * 0.45

            # Tọa độ hạt lúa
            hx = gx + math.cos(grain_ang) * grain_len * 0.6
            hy = gy + math.sin(grain_ang) * grain_len * 0.6

            # Vẽ hạt lúa hình oval vàng rực (grain)
            grain_col = (245, 205, 65) if g_idx % 3 != 0 else (255, 225, 95)
            draw.ellipse([hx - grain_wid, hy - grain_len * 0.5, hx + grain_wid, hy + grain_len * 0.5],
                         fill=grain_col, outline=(195, 145, 30), width=1)

            # Râu lúa mì (Awn) vuốt nhọn chĩa xiên lên trời
            awn_len = grain_len * 1.6
            awn_ex = hx + math.cos(grain_ang - side * math.radians(15)) * awn_len
            awn_ey = hy + math.sin(grain_ang - side * math.radians(15)) * awn_len
            draw.line([(hx, hy), (awn_ex, awn_ey)], fill=(255, 235, 130), width=1)


# ===========================================================================
# 2. BẾP LỬA TRẠI BẬP BÙNG & TÀN TRO HỒNG (CAMPFIRE & FIRE PARTICLES)
# ===========================================================================

def draw_fire_simulation(draw: ImageDraw.ImageDraw, cx: float, cy: float, scale: float, t: float):
    """
    Vẽ đống lửa trại 3 lớp (Đỏ - Cam - Lõi Vàng) nhảy múa theo sóng sin + than hồng bay bốc.
    """
    # 1. Củi gỗ đan chéo dưới đáy
    log_w = scale * 0.7
    log_h = scale * 0.14
    # Thanh gỗ 1
    draw.polygon([
        (cx - log_w * 0.7, cy + scale * 0.12),
        (cx + log_w * 0.6, cy - scale * 0.05),
        (cx + log_w * 0.7, cy + scale * 0.05),
        (cx - log_w * 0.6, cy + scale * 0.22),
    ], fill=(90, 50, 30), outline=(50, 25, 15), width=2)
    # Thanh gỗ 2
    draw.polygon([
        (cx - log_w * 0.65, cy - scale * 0.02),
        (cx + log_w * 0.65, cy + scale * 0.16),
        (cx + log_w * 0.55, cy + scale * 0.24),
        (cx - log_w * 0.75, cy + scale * 0.08),
    ], fill=(110, 65, 40), outline=(50, 25, 15), width=2)

    # 2. Ba tầng ngọn lửa nhảy múa
    flame_layers = [
        {"col": (230, 50, 20), "h_mult": 1.0, "w_mult": 0.55, "freq": 8.0, "phase": 0.0},     # Vỏ đỏ ngoài
        {"col": (255, 140, 20), "h_mult": 0.78, "w_mult": 0.40, "freq": 10.0, "phase": 1.2},   # Thân cam giữa
        {"col": (255, 235, 80), "h_mult": 0.52, "w_mult": 0.25, "freq": 12.0, "phase": 2.5},   # Lõi vàng trong
    ]

    for fl in flame_layers:
        fh = scale * fl["h_mult"]
        fw = scale * fl["w_mult"]
        freq = fl["freq"]
        phase = fl["phase"]

        pts = []
        base_y = cy + scale * 0.08
        pts.append((cx - fw, base_y))

        # Đường cong ngọn lửa bên trái
        steps = 8
        for i in range(1, steps):
            p = i / steps
            wave = math.sin(t * freq + p * 6.0 + phase) * scale * 0.06 * (1 - p)
            px = cx - fw * (1 - p) + wave
            py = base_y - fh * p
            pts.append((px, py))

        # Đỉnh ngọn lửa vuốt nhọn lắc lư
        tip_x = cx + math.sin(t * (freq + 2) + phase) * scale * 0.1
        tip_y = base_y - fh * (1.0 + 0.12 * math.sin(t * 14.0 + phase))
        pts.append((tip_x, tip_y))

        # Đường cong ngọn lửa bên phải đi xuống
        for i in range(steps - 1, 0, -1):
            p = i / steps
            wave = math.sin(t * freq + p * 6.0 + phase + 1.5) * scale * 0.06 * (1 - p)
            px = cx + fw * (1 - p) + wave
            py = base_y - fh * p
            pts.append((px, py))

        pts.append((cx + fw, base_y))
        draw.polygon(pts, fill=fl["col"])

    # 3. Hạt tàn than hồng (Embers) bay bốc lên cao
    for idx in range(12):
        seed = idx * 137.5
        life = (t * 1.5 + idx * 0.3) % 1.0  # chu kỳ 0..1
        px = cx + math.sin(seed + t * 4.0) * scale * 0.35 * life
        py = (cy + scale * 0.05) - scale * 1.4 * life
        r = (1.0 - life) * 4.5 + 1.0
        draw.ellipse([px - r, py - r, px + r, py + r], fill=(255, 220, 100))


# ===========================================================================
# 3. BÁNH RĂNG CÔNG NGHIỆP & HƠI NƯỚC (INDUSTRIAL GEARS & STEAM)
# ===========================================================================

def _draw_gear(draw: ImageDraw.ImageDraw, cx: float, cy: float, r_outer: float, r_inner: float,
               teeth: int, rot: float, col: tuple, hub_col: tuple):
    """Vẽ 1 bánh răng cơ khí có răng cưa thật xoay quanh trục."""
    tooth_depth = (r_outer - r_inner)
    pts = []
    total_pts = teeth * 4
    for i in range(total_pts):
        tooth_idx = i // 4
        sub = i % 4
        base_ang = (tooth_idx / teeth) * 2 * math.pi + rot

        # sub 0: đáy trước răng, 1: đỉnh trước, 2: đỉnh sau, 3: đáy sau răng
        if sub == 0:
            ang = base_ang
            r = r_inner
        elif sub == 1:
            ang = base_ang + (0.25 / teeth) * 2 * math.pi
            r = r_outer
        elif sub == 2:
            ang = base_ang + (0.60 / teeth) * 2 * math.pi
            r = r_outer
        else:
            ang = base_ang + (0.85 / teeth) * 2 * math.pi
            r = r_inner

        pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))

    draw.polygon(pts, fill=col, outline=(30, 30, 40), width=2)
    # Vòng tròn kim loại và trục tâm bánh răng
    draw.ellipse([cx - r_inner * 0.55, cy - r_inner * 0.55, cx + r_inner * 0.55, cy + r_inner * 0.55],
                 fill=hub_col, outline=(30, 30, 40), width=2)
    draw.ellipse([cx - r_inner * 0.22, cy - r_inner * 0.22, cx + r_inner * 0.22, cy + r_inner * 0.22],
                 fill=(25, 25, 35))


def draw_industrial_gears(draw: ImageDraw.ImageDraw, cx: float, cy: float, scale: float, t: float):
    """
    Vẽ hệ thống 2 bánh răng ăn khớp xoay đồng bộ + ống khói nhà máy phả khói.
    """
    # Ống khói nhà máy gạch đỏ ở góc
    chim_x = cx + scale * 0.75
    chim_y = cy + scale * 0.4
    chim_w = scale * 0.28
    chim_h = scale * 0.65
    draw.rectangle([chim_x - chim_w / 2, chim_y - chim_h, chim_x + chim_w / 2, chim_y], fill=(160, 60, 50))
    draw.rectangle([chim_x - chim_w * 0.6, chim_y - chim_h - scale * 0.05, chim_x + chim_w * 0.6, chim_y - chim_h],
                   fill=(80, 80, 90))

    # Khói trắng bốc lên từ ống khói
    for i in range(5):
        s_life = (t * 0.8 + i * 0.2) % 1.0
        sy = (chim_y - chim_h) - s_life * scale * 0.8
        sx = chim_x + math.sin(s_life * 4.0 + i) * scale * 0.15 + s_life * scale * 0.2
        sr = scale * 0.08 + s_life * scale * 0.18
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(220, 225, 230))

    # Bánh răng lớn (Vàng đồng, 12 răng, quay theo chiều kim đồng hồ)
    r1_out = scale * 0.50
    r1_in = scale * 0.40
    t1 = 12
    ang1 = t * 1.5
    _draw_gear(draw, cx - scale * 0.25, cy, r1_out, r1_in, t1, ang1,
               col=(220, 160, 50), hub_col=(250, 200, 90))

    # Bánh răng nhỏ (Xanh kim loại, 8 răng, ăn khớp và quay ngược chiều kim đồng hồ)
    r2_out = scale * 0.35
    r2_in = scale * 0.27
    t2 = 8
    ang2 = -ang1 * (t1 / t2) + (math.pi / t2)
    # Khoảng cách tâm bằng tổng bán kính chia bánh răng
    mesh_dist = (r1_in + r2_out) * 0.95
    _draw_gear(draw, cx - scale * 0.25 + mesh_dist, cy - scale * 0.22, r2_out, r2_in, t2, ang2,
               col=(70, 130, 180), hub_col=(130, 180, 220))


# ===========================================================================
# 4. ROBOT CÔNG NGHỆ CAO & MẠNG NƠ-RON AI (ROBOT & NEURAL NETWORK)
# ===========================================================================

def draw_futuristic_robot(draw: ImageDraw.ImageDraw, cx: float, cy: float, scale: float, t: float):
    """
    Vẽ Robot hình người công nghệ cao:
    - Đầu kim loại giáp vát góc công nghệ (sci-fi chassis)
    - Kính mắt LED quét radar cyan phát sáng
    - Anten phát sóng vô tuyến tỏa ra
    - Đèn equalizer miệng nhảy múa theo âm thanh
    - Lõi năng lượng Arc Reactor ngực phát sáng nhịp tim
    """
    # 1. Anten trên đỉnh đầu
    ant_h = scale * 0.35
    head_top = cy - scale * 0.55
    draw.line([(cx, head_top), (cx, head_top - ant_h)], fill=(120, 140, 160), width=4)
    # Đầu tròn anten
    draw.ellipse([cx - 8, head_top - ant_h - 8, cx + 8, head_top - ant_h + 8], fill=(0, 240, 255))
    # Sóng vô tuyến wifi tỏa ra
    wave_r = (t * 60) % 40 + 10
    draw.arc([cx - wave_r, head_top - ant_h - wave_r, cx + wave_r, head_top - ant_h + wave_r],
             start=210, end=330, fill=(0, 240, 255), width=2)

    # 2. Đầu Robot (Chassis kim loại)
    hw = scale * 0.42
    hh = scale * 0.38
    draw.rounded_rectangle([cx - hw, head_top, cx + hw, head_top + hh],
                           radius=int(scale * 0.08), fill=(40, 48, 62), outline=(0, 240, 255), width=3)

    # Tai 2 bên (Ear bolts)
    draw.rounded_rectangle([cx - hw - scale * 0.08, head_top + hh * 0.3, cx - hw, head_top + hh * 0.7],
                           radius=4, fill=(80, 100, 125))
    draw.rounded_rectangle([cx + hw, head_top + hh * 0.3, cx + hw + scale * 0.08, head_top + hh * 0.7],
                           radius=4, fill=(80, 100, 125))

    # Kính bảo hộ LED (Visor / Eye screen)
    visor_w = hw * 0.78
    visor_h = hh * 0.32
    visor_y = head_top + hh * 0.22
    draw.rounded_rectangle([cx - visor_w, visor_y, cx + visor_w, visor_y + visor_h],
                           radius=6, fill=(10, 20, 30), outline=(60, 180, 240), width=2)

    # Đèn mắt LED quét qua lại (Radar Eye Scan)
    scan_x = cx + math.sin(t * 5.0) * (visor_w * 0.6)
    draw.ellipse([scan_x - 14, visor_y + 4, scan_x + 14, visor_y + visor_h - 4], fill=(0, 255, 230))
    draw.ellipse([scan_x - 7, visor_y + 8, scan_x + 7, visor_y + visor_h - 8], fill=(255, 255, 255))

    # Miệng Equalizer hiển thị sóng âm
    mouth_y = head_top + hh * 0.68
    num_bars = 7
    bar_w = 6
    spacing = 10
    total_w = num_bars * spacing
    start_bx = cx - total_w / 2
    for b_idx in range(num_bars):
        bx = start_bx + b_idx * spacing
        bh = (math.sin(t * 12.0 + b_idx * 1.5) * 0.5 + 0.5) * (scale * 0.12) + 3
        draw.line([(bx, mouth_y - bh / 2), (bx, mouth_y + bh / 2)], fill=(0, 240, 255), width=bar_w)

    # 3. Cổ Robot
    draw.rectangle([cx - scale * 0.12, head_top + hh, cx + scale * 0.12, head_top + hh + scale * 0.1],
                   fill=(60, 70, 85))

    # 4. Ngực và Thân Robot (Torso)
    torso_top = head_top + hh + scale * 0.1
    tw = scale * 0.58
    th = scale * 0.52
    draw.rounded_rectangle([cx - tw, torso_top, cx + tw, torso_top + th],
                           radius=int(scale * 0.1), fill=(32, 40, 52), outline=(80, 130, 180), width=3)

    # Lõi năng lượng Arc Reactor ngực (nhịp tim phát sáng)
    arc_y = torso_top + th * 0.42
    arc_pulse = (math.sin(t * 4.0) * 0.2 + 0.8)
    arc_r = scale * 0.14 * arc_pulse
    draw.ellipse([cx - arc_r, arc_y - arc_r, cx + arc_r, arc_y + arc_r],
                 fill=(0, 230, 255), outline=(255, 255, 255), width=2)
    draw.ellipse([cx - arc_r * 0.5, arc_y - arc_r * 0.5, cx + arc_r * 0.5, arc_y + arc_r * 0.5],
                 fill=(255, 255, 255))


def draw_neural_network_brain(draw: ImageDraw.ImageDraw, cx: float, cy: float, w: float, h: float, t: float):
    """
    Vẽ mạng nơ-ron AI (Deep Neural Network) với các nút thần kinh và xung điện di chuyển.
    """
    layers = [
        {"x_rel": -0.42, "nodes": 3},  # Input layer
        {"x_rel": -0.14, "nodes": 4},  # Hidden layer 1
        {"x_rel": 0.14, "nodes": 4},   # Hidden layer 2
        {"x_rel": 0.42, "nodes": 2},   # Output layer
    ]

    node_coords = []
    for l_idx, l in enumerate(layers):
        lx = cx + l["x_rel"] * w
        n_count = l["nodes"]
        layer_nodes = []
        for n_idx in range(n_count):
            ly = cy + ((n_idx + 0.5) / n_count - 0.5) * h
            layer_nodes.append((lx, ly))
        node_coords.append(layer_nodes)

    # Vẽ đường truyền kết nối giữa các layer
    for l_idx in range(len(node_coords) - 1):
        curr_layer = node_coords[l_idx]
        next_layer = node_coords[l_idx + 1]
        for src in curr_layer:
            for dst in next_layer:
                # Đường synapse mờ
                draw.line([src, dst], fill=(40, 80, 140), width=1)

                # Xung điện (Data pulse) chạy dọc theo synapse
                pulse_t = (t * 2.0 + (src[1] + dst[1]) * 0.005) % 1.0
                px = src[0] + (dst[0] - src[0]) * pulse_t
                py = src[1] + (dst[1] - src[1]) * pulse_t
                draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(0, 255, 240))

    # Vẽ các nút nơ-ron phát sáng
    for l_idx, layer in enumerate(node_coords):
        for nx, ny in layer:
            nr = 11 + math.sin(t * 5.0 + nx * 0.05) * 2
            col = (0, 240, 255) if l_idx % 2 == 0 else (255, 180, 40)
            draw.ellipse([nx - nr, ny - nr, nx + nr, ny + nr], fill=col, outline=(255, 255, 255), width=2)
            draw.ellipse([nx - 3, ny - 3, nx + 3, ny + 3], fill=(255, 255, 255))


# ===========================================================================
# 5. TÊN LỬA VŨ TRỤ & KHÔNG GIAN (SPACE ROCKET & ORBIT)
# ===========================================================================

def draw_space_rocket(draw: ImageDraw.ImageDraw, cx: float, cy: float, scale: float, t: float):
    """
    Vẽ tên lửa phóng xiên lên trời với luồng lửa phản lực và khói phía sau.
    """
    # Góc xiên tên lửa ~ -60 độ (hướng lên trên bên phải)
    ang = math.radians(-55)
    cos_a = math.cos(ang)
    sin_a = math.sin(ang)

    def rot(dx, dy):
        return (cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)

    rw = scale * 0.22
    rh = scale * 0.75

    # Luồng lửa phụt ra từ đuôi
    tail_y = rh * 0.5
    fire_len = (scale * 0.45) * (0.85 + 0.25 * math.sin(t * 25.0))
    fire_pts = [
        rot(-rw * 0.6, tail_y),
        rot(0, tail_y + fire_len),
        rot(rw * 0.6, tail_y)
    ]
    draw.polygon(fire_pts, fill=(255, 80, 20))
    # Lõi lửa vàng trong
    core_pts = [
        rot(-rw * 0.35, tail_y),
        rot(0, tail_y + fire_len * 0.65),
        rot(rw * 0.35, tail_y)
    ]
    draw.polygon(core_pts, fill=(255, 240, 80))

    # Cánh đuôi tên lửa 2 bên
    draw.polygon([rot(-rw, tail_y * 0.4), rot(-rw * 1.8, tail_y), rot(-rw, tail_y)], fill=(220, 40, 40))
    draw.polygon([rot(rw, tail_y * 0.4), rot(rw * 1.8, tail_y), rot(rw, tail_y)], fill=(220, 40, 40))

    # Thân tên lửa (hình thuôn trắng)
    body_pts = [
        rot(0, -rh * 0.65),            # Mũi nhọn
        rot(-rw, -rh * 0.2),
        rot(-rw, tail_y),
        rot(rw, tail_y),
        rot(rw, -rh * 0.2),
    ]
    draw.polygon(body_pts, fill=(245, 245, 250), outline=(40, 40, 50), width=2)

    # Chóp mũi đỏ
    nose_pts = [
        rot(0, -rh * 0.65),
        rot(-rw * 0.7, -rh * 0.38),
        rot(rw * 0.7, -rh * 0.38),
    ]
    draw.polygon(nose_pts, fill=(220, 40, 40))

    # Cửa sổ kính phi hành gia (Porthole)
    win_c = rot(0, -rh * 0.05)
    wr = rw * 0.42
    draw.ellipse([win_c[0] - wr, win_c[1] - wr, win_c[0] + wr, win_c[1] + wr],
                 fill=(60, 180, 240), outline=(200, 200, 210), width=3)
    draw.ellipse([win_c[0] - wr * 0.4, win_c[1] - wr * 0.4, win_c[0] - wr * 0.1, win_c[1] - wr * 0.1],
                 fill=(255, 255, 255))
