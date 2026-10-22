"""Instagram のカルーセル投稿用に、スライド画像（1080x1350 の JPEG）を作る。"""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1350
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

# 目を引く明るいグラデーション（ピンク → 紫 → オレンジ）
GRADIENT = {
    "top_left": (255, 78, 145),
    "top_right": (139, 92, 246),
    "bottom_left": (255, 159, 67),
    "bottom_right": (236, 72, 153),
}
INK = (30, 27, 58)
ACCENT = (219, 39, 119)
SUB_INK = (90, 86, 120)

# 行頭に来てはいけない文字（句読点や閉じかっこ）
NO_LINE_START = set("、。，．・：；？！ー」』）】〉》〕｝ぁぃぅぇぉっゃゅょァィゥェォッャュョ!?)]}")
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U00002B00-\U00002BFF️‍]+"
)


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size, index=0)  # index 0 = 日本語


def clean(text: str) -> str:
    """画像のフォントで表示できない絵文字を取り除く。"""
    return EMOJI.sub("", text).strip()


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        # 「5つ」「10分」のような数字＋1文字や、「DM」などの英字のかたまりは途中で改行しない
        for token in re.findall(r"[0-9][0-9.,]*\S?|[A-Za-z@#%:/+\-]+|.", paragraph):
            if font.getlength(line + token) <= max_width or not line or token[0] in NO_LINE_START:
                line += token
            else:
                lines.append(line)
                line = token
        lines.append(line)
    return lines


def _background() -> Image.Image:
    g = GRADIENT
    small = Image.new("RGB", (2, 2))
    small.putdata([g["top_left"], g["top_right"], g["bottom_left"], g["bottom_right"]])
    bg = small.resize((W, H), Image.BICUBIC)
    # ふんわりした光の玉を重ねて、のっぺりしないようにする
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((-200, -150, 500, 550), fill=(255, 255, 255, 70))
    d.ellipse((650, 900, 1300, 1550), fill=(255, 255, 255, 50))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    return Image.alpha_composite(bg.convert("RGBA"), glow)


def _card(img: Image.Image, box: tuple[int, int, int, int]) -> None:
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + 18, x1, y1 + 18), 48, fill=(60, 20, 80, 70))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(24)))
    ImageDraw.Draw(img).rounded_rectangle(box, 48, fill=(255, 255, 255, 245))


def _draw_lines(d, lines, font, x, y, fill, spacing, center_width=None):
    for line in lines:
        dx = x + (center_width - font.getlength(line)) / 2 if center_width else x
        d.text((dx, y), line, font=font, fill=fill)
        y += font.size + spacing
    return y


def _footer(d: ImageDraw.ImageDraw, handle: str, page: int, total: int) -> None:
    f = _font(30, bold=False)
    d.text((80, H - 90), handle, font=f, fill=(255, 255, 255))
    label = f"{page} / {total}"
    d.text((W - 80 - f.getlength(label), H - 90), label, font=f, fill=(255, 255, 255))


def cover(hook: str, sub: str, handle: str, total: int) -> Image.Image:
    img = _background()
    d = ImageDraw.Draw(img)
    badge_font = _font(34)
    badge = "ライバー事務所 celeste"
    bw = badge_font.getlength(badge) + 64
    d.rounded_rectangle(((W - bw) / 2, 200, (W + bw) / 2, 270), 35, fill=(255, 255, 255))
    d.text(((W - bw) / 2 + 32, 210), badge, font=badge_font, fill=ACCENT)

    title_font = _font(96)
    lines = wrap(clean(hook), title_font, W - 200)
    y = (H - len(lines) * 128) / 2 - 40
    y = _draw_lines(d, lines, title_font, 0, y, (255, 255, 255), 32, center_width=W)

    if sub:
        sub_font = _font(42, bold=False)
        _draw_lines(d, wrap(clean(sub), sub_font, W - 240), sub_font, 0, y + 40, (255, 255, 255), 16, W)

    swipe_font = _font(36)
    swipe = "スワイプしてチェック →"
    sw = swipe_font.getlength(swipe) + 72
    d.rounded_rectangle(((W - sw) / 2, H - 290, (W + sw) / 2, H - 206), 42, fill=(30, 27, 58, 230))
    d.text(((W - sw) / 2 + 36, H - 280), swipe, font=swipe_font, fill=(255, 255, 255))
    _footer(d, handle, 1, total)
    return img


def content(number: int, heading: str, body: str, handle: str, page: int, total: int) -> Image.Image:
    img = _background()
    box = (70, 150, W - 70, H - 170)
    _card(img, box)
    d = ImageDraw.Draw(img)
    x = box[0] + 70
    inner = box[2] - box[0] - 140

    num_font = _font(44)
    num = f"{number:02d}"
    d.rounded_rectangle((x, box[1] + 80, x + 120, box[1] + 160), 40, fill=ACCENT)
    d.text((x + 60 - num_font.getlength(num) / 2, box[1] + 88), num, font=num_font, fill=(255, 255, 255))

    head_font = _font(76)
    y = _draw_lines(d, wrap(clean(heading), head_font, inner), head_font, x, box[1] + 220, INK, 24)
    d.rounded_rectangle((x, y + 24, x + 140, y + 34), 5, fill=(255, 159, 67))

    body_font = _font(50, bold=False)
    _draw_lines(d, wrap(clean(body), body_font, inner), body_font, x, y + 100, SUB_INK, 36)
    _footer(d, handle, page, total)
    return img


def closing(heading: str, body: str, handle: str, page: int, total: int) -> Image.Image:
    img = _background()
    box = (70, 260, W - 70, H - 280)
    _card(img, box)
    d = ImageDraw.Draw(img)
    inner = box[2] - box[0] - 140

    head_font = _font(72)
    head_lines = wrap(clean(heading), head_font, inner)
    body_font = _font(44, bold=False)
    body_lines = wrap(clean(body), body_font, inner)
    block = len(head_lines) * 94 + 60 + len(body_lines) * 74 + 150
    y = box[1] + (box[3] - box[1] - block) / 2
    y = _draw_lines(d, head_lines, head_font, box[0], y, ACCENT, 22, center_width=box[2] - box[0])
    y = _draw_lines(d, body_lines, body_font, box[0], y + 60, INK, 30, center_width=box[2] - box[0])

    cta_font = _font(38)
    cta = "プロフィールからDMへ"
    cw = cta_font.getlength(cta) + 80
    cx = (W - cw) / 2
    d.rounded_rectangle((cx, y + 50, cx + cw, y + 140), 45, fill=ACCENT)
    d.text((cx + 40, y + 66), cta, font=cta_font, fill=(255, 255, 255))
    _footer(d, handle, page, total)
    return img


def render(post: dict, handle: str, out_dir: Path) -> list[Path]:
    """AI が作った投稿の内容（dict）からスライド画像を作り、保存したパスのリストを返す。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    slides = post["slides"]
    total = len(slides) + 2
    images = [cover(post["hook"], post.get("sub", ""), handle, total)]
    for i, s in enumerate(slides, start=1):
        images.append(content(i, s["heading"], s["body"], handle, i + 1, total))
    images.append(closing(post["closing_heading"], post["closing_body"], handle, total, total))

    paths = []
    for i, img in enumerate(images, start=1):
        path = out_dir / f"{i}.jpg"
        img.convert("RGB").save(path, "JPEG", quality=90)  # Instagram の API は JPEG のみ対応
        paths.append(path)
    return paths
