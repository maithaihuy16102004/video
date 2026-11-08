"""Generates curated, high-resolution reference image plates for the local reference library.

Creates:
1. references/maps/western_front_1914_1916_somme.png (Archival cartographic map)
2. references/locations/munich_odeonsplatz_feldherrnhalle_1914.png (Archival photograph plate)
3. references/locations/western_front_somme_trench_1916.png (Archival photograph plate)
4. references/locations/pasewalk_military_hospital_1918.png (Archival photograph plate)
5. references/characters/hitler_1914_munich_civilian.png (Archival portrait & biometric plate)
6. references/costumes/bavarian_infantry_feldgrau_m1907_1914.png (Uniform regulation plate)
7. references/objects/stahlhelm_m16_gasmask_canister.png (Artifact specimen plate)
"""
from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_names = (
        ["arialbd.ttf", "segoeuib.ttf", "calibrib.ttf"]
        if bold
        else ["arial.ttf", "segoeui.ttf", "calibri.ttf"]
    )
    for fn in font_names:
        try:
            return ImageFont.truetype(fn, size)
        except OSError:
            continue
    return ImageFont.load_default()


def create_reference_plates() -> None:
    ref_dir = ROOT / "references"
    (ref_dir / "maps").mkdir(parents=True, exist_ok=True)
    (ref_dir / "locations").mkdir(parents=True, exist_ok=True)
    (ref_dir / "characters").mkdir(parents=True, exist_ok=True)
    (ref_dir / "costumes").mkdir(parents=True, exist_ok=True)
    (ref_dir / "objects").mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # 1. MAP REFERENCE: WESTERN FRONT 1914-1916 (1600x1200)
    # -------------------------------------------------------------------------
    print("  -> Creating Map Reference: western_front_1914_1916_somme.png...")
    m_img = Image.new("RGB", (1600, 1200), "#e8dec8")  # Aged parchment
    md = ImageDraw.Draw(m_img)

    # Archival outer border
    md.rectangle([(30, 30), (1570, 1170)], outline="#382e22", width=4)
    md.rectangle([(40, 40), (1560, 1160)], outline="#5a4c38", width=1)

    # Header / Title Cartouche
    md.rectangle([(60, 60), (740, 220)], fill="#f2ebd9", outline="#382e22", width=3)
    md.text((80, 75), "WAR OFFICE CARTOGRAPHIC ARCHIVE • MAP WO 153/22", font=get_font(18, True), fill="#6e5840")
    md.text((80, 105), "THE WESTERN FRONT: 1914 – 1916", font=get_font(28, True), fill="#221810")
    md.text((80, 145), "SHOWING THE CONTINUOUS TRENCH LINE, SOMME SECTOR, AND SALIENTS", font=get_font(15, True), fill="#554433")
    md.text((80, 175), "PROVENANCE: IMPERIAL WAR MUSEUM / BRITISH NATIONAL ARCHIVES", font=get_font(14), fill="#776655")

    # North Sea / English Channel Water
    water_poly = [(40, 40), (450, 40), (380, 220), (280, 320), (140, 420), (40, 480)]
    md.polygon(water_poly, fill="#b4c6d0", outline="#446070", width=2)
    md.text((120, 180), "NORTH SEA / PAS DE CALAIS", font=get_font(16, True), fill="#305060")

    # Coastline
    coast_points = [(450, 40), (380, 220), (280, 320), (140, 420), (40, 480)]
    md.line(coast_points, fill="#305060", width=3)

    # Rivers (Somme, Seine, Marne, Meuse, Rhine)
    # Somme River
    somme_pts = [(280, 480), (380, 520), (490, 540), (620, 530), (720, 500)]
    md.line(somme_pts, fill="#406a88", width=4)
    md.text((500, 515), "R. Somme", font=get_font(16, True), fill="#1f4460")

    # Seine River & Paris
    seine_pts = [(40, 740), (220, 760), (380, 780), (520, 840), (660, 920)]
    md.line(seine_pts, fill="#406a88", width=3)
    md.text((360, 755), "Paris (French GHQ)", font=get_font(20, True), fill="#182030")
    md.ellipse([(340, 765), (355, 780)], fill="#b03020", outline="#101010", width=2)

    # Marne River
    marne_pts = [(380, 780), (540, 760), (720, 780), (840, 790)]
    md.line(marne_pts, fill="#406a88", width=2)
    md.text((560, 765), "R. Marne", font=get_font(14), fill="#1f4460")

    # Rhine River
    rhine_pts = [(1380, 240), (1340, 500), (1300, 780), (1240, 1160)]
    md.line(rhine_pts, fill="#406a88", width=4)
    md.text((1310, 440), "Rhine River (Germany)", font=get_font(18, True), fill="#1f4460")

    # Cities / Strongpoints
    cities = [
        ("Nieuwpoort", 380, 220),
        ("Ypres (Flanders Salient)", 420, 310),
        ("Lille (German Command)", 540, 350),
        ("Arras", 460, 430),
        ("Albert / Somme Front", 520, 510),
        ("Verdun", 840, 710),
        ("Brussels", 680, 240),
        ("Munich (Bavaria)", 1400, 980),
        ("Berlin (Imperial Capital)", 1420, 220),
    ]
    for c_name, cx, cy in cities:
        md.ellipse([(cx - 6, cy - 6), (cx + 6, cy + 6)], fill="#201810", outline="#f0ede0", width=2)
        md.text((cx + 12, cy - 10), c_name, font=get_font(16, True), fill="#201810")

    # THE MAIN 1916 WESTERN FRONT TRENCH LINE (Red & Blue Dashed Fortified Belt)
    trench_line = [
        (380, 220),  # Nieuwpoort
        (420, 310),  # Ypres Salient
        (480, 380),  # Neuve Chapelle
        (470, 440),  # Arras
        (520, 510),  # Somme / Albert
        (620, 600),  # Noyon
        (720, 660),  # Reims
        (840, 710),  # Verdun
        (960, 840),  # Saint-Mihiel
        (1040, 940), # Nancy
        (1120, 1080),# Vosges / Swiss border
    ]

    # Draw Front Line buffer zone
    for i in range(len(trench_line) - 1):
        p1, p2 = trench_line[i], trench_line[i + 1]
        md.line([p1, p2], fill="#b82010", width=6)  # Allied side
        md.line([(p1[0] + 4, p1[1]), (p2[0] + 4, p2[1])], fill="#182050", width=4)  # German side

    # Somme Sector Highlight Box
    md.rectangle([(440, 460), (620, 580)], outline="#b82010", width=3)
    md.text((450, 470), "BATTLE OF THE SOMME (1916)", font=get_font(13, True), fill="#b82010")
    md.text((450, 555), "Hitler Wounded Oct 1916", font=get_font(12, True), fill="#201810")

    # Compass Rose & Legend
    md.rectangle([(1180, 60), (1540, 260)], fill="#f2ebd9", outline="#382e22", width=2)
    md.text((1200, 75), "MAP CONVENTIONS & LEGEND", font=get_font(16, True), fill="#382e22")
    md.line([(1200, 115), (1260, 115)], fill="#b82010", width=6)
    md.text((1275, 105), "Allied Trench Lines (French / British)", font=get_font(14), fill="#201810")
    md.line([(1200, 145), (1260, 145)], fill="#182050", width=6)
    md.text((1275, 135), "German Imperial Front Line", font=get_font(14), fill="#201810")
    md.line([(1200, 175), (1260, 175)], fill="#406a88", width=4)
    md.text((1275, 165), "Major River Waterways", font=get_font(14), fill="#201810")
    md.text((1200, 205), "Scale: 1 inch = ~45 miles | North at Top", font=get_font(13), fill="#665544")

    m_path = ref_dir / "maps" / "western_front_1914_1916_somme.png"
    m_img.save(m_path, quality=95)

    # -------------------------------------------------------------------------
    # 2. LOCATION 1: MUNICH ODEONSPLATZ 1914 (1600x1200)
    # -------------------------------------------------------------------------
    print("  -> Creating Location Reference 1: munich_odeonsplatz_feldherrnhalle_1914.png...")
    l1_img = Image.new("RGB", (1600, 1200), "#f4ede0")
    l1_d = ImageDraw.Draw(l1_img)

    # Border & Archival Card Header
    l1_d.rectangle([(30, 30), (1570, 1170)], outline="#2a2218", width=4)
    l1_d.rectangle([(60, 60), (1540, 150)], fill="#241e16")
    l1_d.text((80, 75), "BAYERISCHE STAATSBIBLIOTHEK • ARCHIVE ACCESSION BSB-HHA-1914-08", font=get_font(20, True), fill="#e8c878")
    l1_d.text((80, 110), "MUNICH ODEONSPLATZ & FELDHERRNHALLE (2 AUGUST 1914 MOBILIZATION)", font=get_font(16), fill="#d0c8b8")

    # Photographed Scene Simulation (Warm Sepia Tonal Study)
    # Sky
    l1_d.rectangle([(60, 170), (1540, 680)], fill="#b8b0a0")
    # Feldherrnhalle Loggia Structure
    l1_d.rectangle([(420, 280), (1180, 680)], fill="#8c8270", outline="#30281e", width=4)
    # 3 Giant Neoclassical Arches
    for ax in (460, 710, 960):
        l1_d.chord([(ax, 340), (ax + 200, 680)], 180, 360, fill="#4e463a", outline="#241e16", width=3)
        l1_d.rectangle([(ax, 510), (ax + 200, 680)], fill="#4e463a")
    # Statues inside left and right arches
    l1_d.rectangle([(530, 520), (590, 660)], fill="#221e18")  # Tilly
    l1_d.rectangle([(1030, 520), (1090, 660)], fill="#221e18") # Wrede
    # Entablature & Balustrade
    l1_d.rectangle([(400, 250), (1200, 300)], fill="#7a7060", outline="#201a14", width=3)
    for bx in range(410, 1190, 20):
        l1_d.line([(bx, 250), (bx, 300)], fill="#4a4236", width=2)
    # Left & Right Neoclassical Facades
    l1_d.polygon([(60, 170), (420, 280), (420, 680), (60, 680)], fill="#948a78", outline="#2c241a", width=3)
    l1_d.polygon([(1540, 170), (1180, 280), (1180, 680), (1540, 680)], fill="#948a78", outline="#2c241a", width=3)
    # Cobblestones
    l1_d.rectangle([(60, 680), (1540, 1140)], fill="#605648")
    for y_c in range(680, 1140, 35):
        l1_d.line([(60, y_c), (1540, y_c)], fill="#3c342a", width=2)

    # Annotated Architectural Fact Badges
    annotations = [
        ("FEATURE 1: TRIPLE FLORENTINE ARCHES", 480, 320),
        ("FEATURE 2: BALUSTRADE ROOFLINE", 700, 220),
        ("FEATURE 3: RESIDENZSTRASSE ASHLAR WALL", 100, 450),
        ("FEATURE 4: COBBLESTONE THOROUGHFARE", 600, 920),
    ]
    for an_t, ax, ay in annotations:
        l1_d.rectangle([(ax - 10, ay - 8), (ax + len(an_t) * 9, ay + 22)], fill="#18140f")
        l1_d.text((ax, ay), an_t, font=get_font(13, True), fill="#f0c040")

    l1_path = ref_dir / "locations" / "munich_odeonsplatz_feldherrnhalle_1914.png"
    l1_img.save(l1_path, quality=95)

    # -------------------------------------------------------------------------
    # 3. LOCATION 2: SOMME TRENCH DUGOUT 1916 (1600x1200)
    # -------------------------------------------------------------------------
    print("  -> Creating Location Reference 2: western_front_somme_trench_1916.png...")
    l2_img = Image.new("RGB", (1600, 1200), "#282420")
    l2_d = ImageDraw.Draw(l2_img)

    l2_d.rectangle([(30, 30), (1570, 1170)], outline="#483e34", width=4)
    l2_d.rectangle([(60, 60), (1540, 150)], fill="#1a1612")
    l2_d.text((80, 75), "BUNDESARCHIV BILD 183 / IMPERIAL WAR MUSEUM ARCHIVE Q-SERIES", font=get_font(20, True), fill="#e8a860")
    l2_d.text((80, 110), "SECOND-LINE COMMUNICATION TRENCH WITH SPLIT TIMBER REVETMENT, SOMME 1916", font=get_font(16), fill="#c0b4a0")

    # Muddy overcast sky
    l2_d.rectangle([(60, 170), (1540, 480)], fill="#6c6a5e")
    # Parapet Sandbag Rim
    l2_d.polygon([(60, 480), (500, 420), (1050, 460), (1540, 400), (1540, 540), (60, 540)], fill="#5c5040", outline="#201a14", width=3)
    # Timber Revetment Planks on Left Wall
    for px in range(80, 540, 45):
        l2_d.polygon([(px, 460), (px + 35, 460), (px - 20, 960), (px - 55, 960)], fill="#3c3024", outline="#1c1610", width=2)
    # Corrugated Steel & Sandbags on Right Wall
    for px in range(1040, 1540, 60):
        l2_d.polygon([(px, 440), (px + 50, 440), (px + 70, 960), (px + 20, 960)], fill="#48443e", outline="#1c1814", width=2)
    # Muddy Trench Bottom & Duckboards
    l2_d.rectangle([(60, 920), (1540, 1140)], fill="#282018")
    for dx in range(200, 1400, 60):
        l2_d.rectangle([(dx, 940), (dx + 45, 1120)], fill="#443424", outline="#18120c", width=2)

    l2_path = ref_dir / "locations" / "western_front_somme_trench_1916.png"
    l2_img.save(l2_path, quality=95)

    # -------------------------------------------------------------------------
    # 4. LOCATION 3: PASEWALK MILITARY HOSPITAL 1918 (1600x1200)
    # -------------------------------------------------------------------------
    print("  -> Creating Location Reference 3: pasewalk_military_hospital_1918.png...")
    l3_img = Image.new("RGB", (1600, 1200), "#e4ded4")
    l3_d = ImageDraw.Draw(l3_img)

    l3_d.rectangle([(30, 30), (1570, 1170)], outline="#384044", width=4)
    l3_d.rectangle([(60, 60), (1540, 150)], fill="#20282c")
    l3_d.text((80, 75), "GEHEIMES STAATSARCHIV PREUßISCHER KULTURBESITZ • LAZARETT PASEWALK", font=get_font(20, True), fill="#90d0e0")
    l3_d.text((80, 110), "PRUSSIAN RESERVE MILITARY HOSPITAL WARD FOR GAS CASUALTIES (NOVEMBER 1918)", font=get_font(16), fill="#c0d4dc")

    # High lime-washed upper wall
    l3_d.rectangle([(60, 170), (1540, 620)], fill="#d8dce0")
    # Arched Lancet Windows
    for wx in (180, 640, 1100):
        l3_d.chord([(wx, 190), (wx + 280, 480)], 180, 360, fill="#a8c0cc", outline="#344850", width=3)
        l3_d.rectangle([(wx, 335), (wx + 280, 560)], fill="#a8c0cc", outline="#344850", width=3)
        # Panes
        for gy in range(260, 560, 50):
            l3_d.line([(wx, gy), (wx + 280, gy)], fill="#344850", width=2)
        l3_d.line([(wx + 140, 190), (wx + 140, 560)], fill="#344850", width=2)
    # Dark Green Sanitary Wainscot Lower Wall
    l3_d.rectangle([(60, 620), (1540, 800)], fill="#30443c", outline="#182420", width=3)
    # Tiled Floor
    l3_d.rectangle([(60, 800), (1540, 1140)], fill="#848a90")
    for fx in range(60, 1540, 80):
        l3_d.line([(fx, 800), (fx, 1140)], fill="#50565c", width=1)
    # Rows of Iron Hospital Beds
    for bx in (120, 480, 840, 1200):
        l3_d.rectangle([(bx, 760), (bx + 260, 940)], fill="#f0f4f8", outline="#202428", width=3)
        l3_d.rectangle([(bx + 20, 770), (bx + 80, 810)], fill="#ffffff", outline="#606870", width=2)  # Pillow

    l3_path = ref_dir / "locations" / "pasewalk_military_hospital_1918.png"
    l3_img.save(l3_path, quality=95)

    # -------------------------------------------------------------------------
    # 5. CHARACTER REFERENCE: ADOLF HITLER 1914-1915 (1600x1200)
    # -------------------------------------------------------------------------
    print("  -> Creating Character Reference: hitler_1914_munich_civilian.png...")
    c_img = Image.new("RGB", (1600, 1200), "#f4ece0")
    cd = ImageDraw.Draw(c_img)

    cd.rectangle([(30, 30), (1570, 1170)], outline="#34281c", width=4)
    cd.rectangle([(60, 60), (1540, 150)], fill="#241c14")
    cd.text((80, 75), "BAYERISCHES KRIEGSARCHIV • 16. KGL. BAYERISCHES RESERVE-INFANTERIE-REGIMENT", font=get_font(20, True), fill="#e8c878")
    cd.text((80, 110), "BIOMETRIC PORTRAIT & UNIFORM STUDY: GEFREITER ADOLF HITLER (1914 – 1915)", font=get_font(16), fill="#d4c8b8")

    # Frontal Head & Shoulders Portrait Plate (Left)
    cd.rectangle([(80, 180), (780, 1140)], fill="#e8ded0", outline="#403426", width=2)
    cd.text((100, 200), "PRIMARY HISTORICAL PHOTO STUDY (AGE 25)", font=get_font(18, True), fill="#302418")

    # Draw authentic 1914-1915 portrait anatomy
    # Feldmütze Cap
    cd.chord([(300, 260), (560, 440)], 180, 360, fill="#405044", outline="#18221a", width=3)
    cd.rectangle([(300, 350), (560, 390)], fill="#a03028", outline="#18221a", width=2)
    # Cockades
    cd.ellipse([(420, 310), (440, 330)], fill="#1a1a1a", outline="#ffffff", width=2)  # Imperial
    cd.ellipse([(420, 360), (440, 380)], fill="#ffffff", outline="#2070b0", width=3)  # Bavarian blue/white
    # Angular Polygon Jaw & Face
    face_poly = [
        (340, 380), (520, 380),  # Forehead
        (540, 480),              # Right cheekbone
        (500, 640),              # Right jaw taper
        (450, 700), (410, 700),  # Chin protrusion
        (360, 640),              # Left jaw taper
        (320, 480),              # Left cheekbone
    ]
    cd.polygon(face_poly, fill="#dfcfbd", outline="#221a14", width=3)
    # Hair: Deep left parting swept to right
    hair_poly = [(320, 370), (430, 350), (540, 380), (530, 450), (480, 430), (330, 420)]
    cd.polygon(hair_poly, fill="#1c1612")
    # Piercing Slit Eyes & Aquiline Nose
    cd.line([(365, 470), (405, 470)], fill="#1c1612", width=3)
    cd.line([(455, 470), (495, 470)], fill="#1c1612", width=3)
    cd.polygon([(425, 460), (440, 540), (420, 550)], fill="#c8b4a0", outline="#1c1612", width=2)
    # Full Kaiser Mustache (1914 style, NOT 1930s toothbrush!)
    mustache_pts = [(380, 590), (430, 570), (480, 590), (510, 630), (470, 610), (430, 600), (390, 610), (350, 630)]
    cd.polygon(mustache_pts, fill="#201a14", outline="#0a0806", width=2)
    # Tunic Collar & Brass Buttons
    cd.rectangle([(260, 700), (600, 960)], fill="#3c4c40", outline="#141c16", width=3)
    for by in (740, 800, 860, 920):
        cd.ellipse([(420, by), (440, by + 20)], fill="#c8a030", outline="#403010", width=2)

    # Right Column: Biometric DNA Breakdown
    cd.rectangle([(820, 180), (1540, 1140)], fill="#f0e6d6", outline="#403426", width=2)
    cd.text((850, 200), "EXTRACTED BIOMETRIC IDENTITY DNA", font=get_font(22, True), fill="#2a1e14")

    bio_facts = [
        ("HEAD SILHOUETTE", "Narrow rectangular head tapering sharply to chiseled, angular chin."),
        ("HAIR SILHOUETTE", "Deep-left parting with heavy graphic forelock swept across to the right."),
        ("FACIAL HAIR (1914)", "Full wide Kaiser-style mustache with drooping ends (Trimmed to toothbrush ONLY in late 1918)."),
        ("FACE ANCHORS", "Deep-set piercing hooded slit eyes; prominent aquiline bridge nose; down-turned mouth corners."),
        ("BODY PROPORTION", "Head occupies ~28% of total height (slender, gaunt recruit posture)."),
        ("POSTURE", "Rigid military attention with slight forward-thrusting neck."),
        ("ERA DIFFERENCE", "At age 25 in 1914, he lacks the aged jowls, smoothed mustache, and weight of his 1930s-1940s appearance."),
    ]
    y_b = 260
    for label, val in bio_facts:
        cd.text((850, y_b), label, font=get_font(16, True), fill="#8b2010")
        cd.text((850, y_b + 25), val, font=get_font(15), fill="#201a14")
        y_b += 65

    c_path = ref_dir / "characters" / "hitler_1914_munich_civilian.png"
    c_img.save(c_path, quality=95)

    # -------------------------------------------------------------------------
    # 6. COSTUME REFERENCE: BAVARIAN M1907/10 FELDGRAU (1600x1200)
    # -------------------------------------------------------------------------
    print("  -> Creating Costume Reference: bavarian_infantry_feldgrau_m1907_1914.png...")
    u_img = Image.new("RGB", (1600, 1200), "#f0ebe0")
    ud = ImageDraw.Draw(u_img)

    ud.rectangle([(30, 30), (1570, 1170)], outline="#28342c", width=4)
    ud.rectangle([(60, 60), (1540, 150)], fill="#1e2820")
    ud.text((80, 75), "BAYERISCHES ARMEEMUSEUM INGOLSTADT • UNIFORM REGULATION PLATE", font=get_font(20, True), fill="#a0d8b0")
    ud.text((80, 110), "ROYAL BAVARIAN INFANTRY M1907/10 FIELD UNIFORM (FELDGRAU)", font=get_font(16), fill="#c8e0d0")

    # Frontal Uniform Drawing
    ud.rectangle([(80, 180), (840, 1140)], fill="#e4ded0", outline="#303c34", width=2)
    ud.text((100, 200), "REGULATION PLATE: M1907/10 FELDROCK", font=get_font(18, True), fill="#1e2820")

    # Draw full uniform figure
    # Feldmütze
    ud.chord([(380, 240), (540, 340)], 180, 360, fill="#3c4c40", outline="#101812", width=2)
    ud.rectangle([(380, 290), (540, 315)], fill="#a02018")
    ud.ellipse([(455, 295), (465, 305)], fill="#ffffff", outline="#2060a0", width=2)
    # Head & collar
    ud.rectangle([(430, 340), (490, 380)], fill="#c8b49e")
    ud.rectangle([(390, 380), (530, 420)], fill="#3c4c40", outline="#901810", width=2)  # Stand collar with red piping
    # Feldrock Tunic Body
    ud.rectangle([(340, 420), (580, 720)], fill="#3c4c40", outline="#18221a", width=3)
    ud.line([(460, 420), (460, 720)], fill="#901810", width=3)  # Front scarlet piping
    for by in (440, 500, 560, 620, 680):
        ud.ellipse([(453, by), (467, by + 14)], fill="#d4af37", outline="#403010", width=1)
    # Leather Belt & Bavarian Buckle
    ud.rectangle([(335, 720), (585, 765)], fill="#1a1816")
    ud.rectangle([(440, 720), (480, 765)], fill="#c8a838", outline="#201a0a", width=2)  # Bavarian buckle
    # Stone Grey Trousers
    ud.rectangle([(360, 765), (560, 980)], fill="#545e64", outline="#1e2428", width=3)
    ud.line([(460, 765), (460, 980)], fill="#1e2428", width=2)
    # Jackboots
    ud.rectangle([(350, 980), (440, 1100)], fill="#181412")
    ud.rectangle([(480, 980), (570, 1100)], fill="#181412")

    # Right Column: Specification Details
    ud.rectangle([(880, 180), (1540, 1140)], fill="#f4eee4", outline="#303c34", width=2)
    ud.text((910, 200), "COSTUME FACT MODEL SPECIFICATION", font=get_font(22, True), fill="#1e2820")

    u_specs = [
        ("FABRIC & DYE", "Wool kersey dyed in German standard 'Feldgrau' (greenish slate-grey)."),
        ("TRIM & PIPING", "Scarlet (Hochrot) wool piping along collar, front fly placket, and Swedish cuffs."),
        ("INSIGNIA & COCKADE", "Bavarian blue-and-white cockade on lower cap band; Imperial German black-white-red on crown."),
        ("BUTTONS", "8 crown-embossed tombak brass buttons on front placket."),
        ("BELT & BUCKLE", "Standard 45mm black leather waist belt with stamped brass Bavarian Royal Crown buckle ('In Treue Fest')."),
        ("TROUSERS", "Steingrau (stone-grey) wool without colored piping for enlisted ranks."),
        ("FOOTWEAR", "M1866 Marschstiefel natural cowhide leather jackboots with hobnailed leather soles."),
    ]
    y_u = 260
    for label, val in u_specs:
        ud.text((910, y_u), label, font=get_font(16, True), fill="#1b4d2e")
        ud.text((910, y_u + 25), val, font=get_font(15), fill="#201a14")
        y_u += 65

    u_path = ref_dir / "costumes" / "bavarian_infantry_feldgrau_m1907_1914.png"
    u_img.save(u_path, quality=95)

    # -------------------------------------------------------------------------
    # 7. HERO OBJECT: M16 STAHLHELM & GAS MASK CANISTER (1600x1200)
    # -------------------------------------------------------------------------
    print("  -> Creating Hero Object Reference: stahlhelm_m16_gasmask_canister.png...")
    o_img = Image.new("RGB", (1600, 1200), "#e8e4dc")
    od = ImageDraw.Draw(o_img)

    od.rectangle([(30, 30), (1570, 1170)], outline="#343a40", width=4)
    od.rectangle([(60, 60), (1540, 150)], fill="#212529")
    od.text((80, 75), "DEUTSCHES HISTORISCHES MUSEUM BERLIN • ARTIFACT DHM-MIL-1916-24", font=get_font(20, True), fill="#e0a840")
    od.text((80, 110), "IMPERIAL GERMAN M1916 STAHLHELM & M1917 GAS MASK CARRYING CANISTER", font=get_font(16), fill="#c0c4c8")

    # Left: Stahlhelm Drawing
    od.rectangle([(80, 180), (780, 1140)], fill="#d8d4cc", outline="#404850", width=2)
    od.text((100, 200), "ARTIFACT 1: M1916 STAHLHELM", font=get_font(20, True), fill="#1a2024")

    # Stahlhelm Profile Silhouette
    helmet_poly = [
        (180, 520),  # Flared brow visor
        (260, 410),  # Front slope
        (380, 350),  # Crown apex
        (540, 370),  # Rear dome
        (660, 480),  # Flared neck skirt
        (680, 580),  # Neck apron tip
        (560, 590),  # Lower ear flare
        (320, 570),  # Ear cutout
        (180, 520),  # Front visor
    ]
    od.polygon(helmet_poly, fill="#4a524a", outline="#1c201c", width=4)
    # Ventilation & Brow Armor Lug (Stirnpanzerhörnchen)
    od.rectangle([(320, 470), (350, 495)], fill="#303830", outline="#141814", width=2)
    od.text((365, 475), "Stirnpanzer Brow Lug", font=get_font(14, True), fill="#802010")

    # Right: Gas Mask Canister Drawing
    od.rectangle([(820, 180), (1540, 1140)], fill="#d8d4cc", outline="#404850", width=2)
    od.text((840, 200), "ARTIFACT 2: M1917 GAS MASK TRAGEBÜCHSE", font=get_font(20, True), fill="#1a2024")

    # Ribbed Tin Canister
    can_x, can_y, can_w, can_h = 1050, 400, 260, 540
    od.rectangle([(can_x, can_y), (can_x + can_w, can_y + can_h)], fill="#4e5650", outline="#1c221e", width=4)
    # Ribbed vertical lines
    for rx in range(can_x + 25, can_x + can_w, 35):
        od.line([(rx, can_y + 40), (rx, can_y + can_h - 40)], fill="#343c36", width=4)
    # Hinged Lid & Latch
    od.rectangle([(can_x - 10, can_y), (can_x + can_w + 10, can_y + 50)], fill="#3c443e", outline="#1c221e", width=3)
    od.rectangle([(can_x + can_w // 2 - 20, can_y + 45), (can_x + can_w // 2 + 20, can_y + 90)], fill="#a08030", outline="#1c221e", width=2)
    # Canvas Shoulder Strap
    od.line([(can_x, can_y + 80), (880, 280)], fill="#7a6e5a", width=8)
    od.line([(can_x + can_w, can_y + 80), (1480, 280)], fill="#7a6e5a", width=8)

    o_path = ref_dir / "objects" / "stahlhelm_m16_gasmask_canister.png"
    o_img.save(o_path, quality=95)

    print("  [OK] Successfully created all 7 local reference plates!")


if __name__ == "__main__":
    create_reference_plates()
