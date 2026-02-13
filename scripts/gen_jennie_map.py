from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

out = Path('backend/app/stories/2_jennie_murder_mini/2_jennie_murder_mini.png')
W, H = 1200, 720
bg = (14, 16, 24)
img = Image.new('RGB', (W, H), bg)
d = ImageDraw.Draw(img)

palette = {
    'interview_a': (66, 135, 245),
    'interview_b': (244, 114, 182),
    'lab': (255, 193, 79),
    'entry': (94, 234, 212),
    'kitchen': (248, 113, 113),
    'camera': (160, 174, 192),
    'text': (235, 237, 240),
    'grid': (52, 58, 70),
    'accent': (94, 234, 212),
}

for x in range(0, W, 80):
    d.line([(x, 0), (x, H)], fill=palette['grid'], width=1)
for y in range(0, H, 80):
    d.line([(0, y), (W, y)], fill=palette['grid'], width=1)

rooms = {
    'Interview Room A (Steve)': ((60, 80), (320, 260), 'interview_a'),
    'Interview Room B (Bob)': ((60, 300), (320, 480), 'interview_b'),
    'Evidence Lab': ((380, 160), (660, 340), 'lab'),
    'Apartment Entry/Hall': ((760, 200), (1080, 320), 'entry'),
    'Kitchen (Crime Scene)': ((760, 340), (1080, 540), 'kitchen'),
    'Hallway Camera View': ((900, 80), (1140, 180), 'camera'),
}

try:
    font = ImageFont.truetype('arial.ttf', 18)
except Exception:
    font = ImageFont.load_default()

for label, ((x1, y1), (x2, y2), key) in rooms.items():
    d.rounded_rectangle([x1, y1, x2, y2], radius=12, fill=palette.get(key, (90, 90, 90)), outline=(20, 20, 25), width=2)
    d.text((x1 + 12, y1 + 12), label, fill=palette['text'], font=font)

def arrow(a, b, color, width=4):
    d.line([a, b], fill=color, width=width)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    sz = 12
    back = (b[0] - sz * math.cos(ang), b[1] - sz * math.sin(ang))
    left = (back[0] + sz * 0.6 * math.sin(ang), back[1] - sz * 0.6 * math.cos(ang))
    right = (back[0] - sz * 0.6 * math.sin(ang), back[1] + sz * 0.6 * math.cos(ang))
    d.polygon([b, left, right], fill=color)

arrow((320, 170), (380, 210), palette['accent'])
arrow((320, 390), (380, 290), palette['accent'])
arrow((660, 250), (760, 260), palette['accent'])
arrow((920, 320), (920, 340), palette['accent'])
arrow((1040, 240), (1040, 200), palette['accent'])
arrow((1040, 260), (1040, 360), palette['accent'])
arrow((920, 460), (920, 360), palette['accent'])

legend_x, legend_y = 70, 540
legend_items = [
    ('Interview A', 'interview_a'),
    ('Interview B', 'interview_b'),
    ('Evidence Lab', 'lab'),
    ('Entry/Hall', 'entry'),
    ('Kitchen Scene', 'kitchen'),
    ('Hallway Cam', 'camera'),
    ('Path/flow', 'accent'),
]
for i, (txt, key) in enumerate(legend_items):
    y = legend_y + i * 26
    d.rectangle([legend_x, y, legend_x + 18, y + 18], fill=palette.get(key, (120, 120, 120)), outline=(25, 25, 30))
    d.text((legend_x + 26, y - 2), txt, fill=palette['text'], font=font)

d.text((720, 32), 'Jennie Mini-Case — Movement & Evidence Map', fill=palette['text'], font=font)
d.text((720, 56), 'Fictional scenario for epistemic-state testing', fill=palette['text'], font=font)

out.parent.mkdir(parents=True, exist_ok=True)
img.save(out)
print('wrote', out.resolve())
