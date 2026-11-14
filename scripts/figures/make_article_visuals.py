"""Reproducible article schematics; no candidate, grader, model or network runs.

Run with an existing Pillow environment: python scripts/figures/make_article_visuals.py
All generated outputs are confined to figures/article-visuals/.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import math
from pathlib import Path
import platform
import signal
import time
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont, __version__ as PILLOW_VERSION

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "figures" / "article-visuals"
W, H = 1472, 960
PAPER, WHITE, INK = "#F6F3EB", "#FFFEFA", "#20282D"
MUTED, RULE, FAINT = "#616A6E", "#CBCDC7", "#E7E7DF"
BLUE, BLUE_WASH = "#2458C6", "#E8EDF7"
ORANGE, ORANGE_WASH = "#B84B25", "#F7E7DA"
FONT_PAIRS = [
    (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
    (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
     Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    (Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
     Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")),
]
FONT_PATHS = next((p for p in FONT_PAIRS if all(f.exists() for f in p)), None)
if FONT_PATHS is None:
    raise SystemExit("An existing Arial or DejaVu Sans regular/bold pair is required.")
FONT_FAMILY = "Arial" if FONT_PATHS[0].name.lower() == "arial.ttf" else "DejaVu Sans"
FONTS = {}
STARTED, TIMEOUT_SECONDS = time.monotonic(), 180


def check_deadline():
    if time.monotonic() - STARTED > TIMEOUT_SECONDS:
        raise TimeoutError("Rendering exceeded the 180-second deadline")


def font(size, bold=False):
    key = (size, bold)
    if key not in FONTS:
        FONTS[key] = ImageFont.truetype(str(FONT_PATHS[int(bold)]), size)
    return FONTS[key]


def ease(value):
    value = max(0., min(1., value))
    return value * value * (3 - 2 * value)


class Canvas:
    """Shared native primitives for the raster figures and editable SVG."""

    def __init__(self, height=H, vector=False):
        self.height = height
        self.image = Image.new("RGB", (W, height), PAPER)
        self.draw = ImageDraw.Draw(self.image)
        self.svg = [f'<rect width="{W}" height="{height}" fill="{PAPER}"/>'] if vector else None

    def box(self, box, fill=PAPER, stroke=None, width=2, radius=0):
        x,y,r,b = box
        self.draw.rounded_rectangle(box,radius=radius,fill=fill,outline=stroke,width=width)
        if self.svg is not None:
            self.svg.append(f'<rect x="{x}" y="{y}" width="{r-x}" height="{b-y}" rx="{radius}" '
                            f'fill="{fill}" stroke="{stroke or "none"}" stroke-width="{width}"/>')

    def polygon(self, points, fill, stroke=None, width=2):
        self.draw.polygon(points,fill=fill)
        if stroke:
            self.draw.line(points+[points[0]],fill=stroke,width=width,joint="curve")
        if self.svg is not None:
            self.svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in points)}" '
                            f'fill="{fill}" stroke="{stroke or "none"}" stroke-width="{width}"/>')

    def circle(self, x,y,r,fill=PAPER,stroke=None,width=2):
        self.draw.ellipse((x-r,y-r,x+r,y+r),fill=fill,outline=stroke,width=width)
        if self.svg is not None:
            self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" '
                            f'stroke="{stroke or "none"}" stroke-width="{width}"/>')

    def text(self,x,y,text,size=28,color=INK,bold=False,align="left"):
        f = font(size,bold)
        ascent=f.getmetrics()[0]
        for index,line in enumerate(text.split("\n")):
            xx=x
            if align!="left":
                xx-=self.draw.textlength(line,font=f)/(2 if align=="center" else 1)
            yy=y+index*(size+9)+ascent
            self.draw.text((xx,yy),line,font=f,fill=color,anchor="ls")
            if self.svg is not None:
                self.svg.append(f'<text x="{xx:.2f}" y="{yy}" font-family="{FONT_FAMILY},sans-serif" '
                                f'font-size="{size}" font-weight="{700 if bold else 400}" '
                                f'fill="{color}">{html.escape(line)}</text>')

    def line(self,points,color=RULE,width=3,arrow=False,dashed=False):
        if dashed:
            for a,b in zip(points,points[1:]):
                dx,dy=b[0]-a[0],b[1]-a[1]
                length=math.hypot(dx,dy)
                if not length:
                    continue
                for start in range(0,math.ceil(length),18):
                    end=min(start+9,length)
                    self.draw.line([(a[0]+dx*start/length,a[1]+dy*start/length),
                                    (a[0]+dx*end/length,a[1]+dy*end/length)],fill=color,width=width)
        else:
            self.draw.line(points,fill=color,width=width,joint="curve")
        if self.svg is not None:
            dash=' stroke-dasharray="9 9"' if dashed else ""
            self.svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" '
                            f'fill="none" stroke="{color}" stroke-width="{width}"{dash}/>')
        if arrow:
            a,b=points[-2:]
            angle=math.atan2(b[1]-a[1],b[0]-a[0])
            p=[b,(b[0]-15*math.cos(angle-.45),b[1]-15*math.sin(angle-.45)),
               (b[0]-15*math.cos(angle+.45),b[1]-15*math.sin(angle+.45))]
            self.polygon(p,color)

    def check(self,x,y,color=BLUE,scale=1):
        self.line([(x,y+12*scale),(x+10*scale,y+22*scale),(x+30*scale,y)],color,max(2,round(5*scale)))

    def save_svg(self,path):
        title="The training loop, independent audit, and securegrade caller boundary"
        desc=("MBPP task and first-assert prompts enter Tiny Aya Global with LoRA. Completions and full tests "
              "enter one selected historical AlignTune or securegrade callback. Numeric rewards feed AlignTune/TRL "
              "GRPO and a LoRA update. rewardcheck separately audits AlignTune, SafeTune and securegrade. Trusted "
              "tests and expected values remain in the securegrade caller. Arguments cross to a fresh candidate "
              "interpreter; untrusted return data is validated, decoded into built-ins and compared in the caller.")
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{self.height}" '
                        f'viewBox="0 0 {W} {self.height}" role="img" aria-labelledby="title desc">\n'
                        f'<title id="title">{title}</title>\n<desc id="desc">{desc}</desc>\n'
                        +"\n".join(self.svg)+"\n</svg>\n",encoding="utf-8")


def heading(c,tag,title):
    c.text(64,34,tag,24,MUTED,True)
    c.text(64,79,title,52,INK,True)
    c.line([(64,158),(1408,158)],INK,2)


def document(c,x,y,w=160,h=190,color=INK,kind="code",checks=0):
    """Folded source document or actual checklist; syntax strokes are not code."""
    fold=min(28,w*.2)
    c.polygon([(x,y),(x+w-fold,y),(x+w,y+fold),(x+w,y+h),(x,y+h)],WHITE,color,2)
    c.line([(x+w-fold,y),(x+w-fold,y+fold),(x+w,y+fold)],color,2)
    if kind=="tests":
        for i in range(3):
            yy=y+h*.26+i*h*.24
            side=w*.17
            c.box((x+w*.13,yy,x+w*.13+side,yy+side),PAPER,RULE,2)
            c.line([(x+w*.4,yy+side/2),(x+w*.83,yy+side/2)],RULE,max(2,round(w*.025)))
            if checks>i:
                c.check(x+w*.14,yy+w*.005,BLUE,w*.005)
    else:
        mid=y+h*.35
        c.line([(x+w*.32,mid-h*.07),(x+w*.19,mid),(x+w*.32,mid+h*.07)],color,3)
        c.line([(x+w*.67,mid-h*.07),(x+w*.8,mid),(x+w*.67,mid+h*.07)],color,3)
        for i,length in enumerate((.57,.4,.62)):
            c.line([(x+w*.19,y+h*.58+i*h*.12),(x+w*(.19+length),y+h*.58+i*h*.12)],RULE,4)


def network(c,x,y):
    layers=[[(x,y-40),(x,y+40)],[(x+78,y-65),(x+78,y),(x+78,y+65)],[(x+156,y-40),(x+156,y+40)]]
    for a,b in zip(layers,layers[1:]):
        for p in a:
            for q in b:
                c.line([p,q],RULE,2)
    for layer in layers:
        for xx,yy in layer:
            c.circle(xx,yy,13,WHITE,INK,3)
    # Adapter sits above the output side, clear of both data-input routes.
    c.line([(x+214,y-94),(x+156,y-53)],BLUE,3)
    c.box((x+214,y-138,x+342,y-94),BLUE)
    c.text(x+278,y-131,"LoRA",25,WHITE,True,align="center")


def cycle(c,x,y,r=24):
    for start in (15,195):
        points=[(x+r*math.cos(math.radians(a)),y+r*math.sin(math.radians(a))) for a in range(start,start+135,6)]
        c.line(points,BLUE,3,True)


def architecture():
    c=Canvas(1160,True)
    heading(c,"01 / TRAINING + AUDIT","Where the reward enters training")
    # A single training loop; the full-test route and update route never cross.
    c.line([(455,570),(32,570),(32,196),(780,196),(780,244)],BLUE,3,True)
    c.text(67,171,"LoRA update",26,BLUE,True)
    c.text(64,245,"MBPP training row",31,INK,True)
    c.box((76,310,330,463),FAINT,RULE)
    c.box((70,303,324,456),WHITE,RULE)
    c.box((64,296,318,449),WHITE,INK)
    c.text(84,315,"Task +",27,INK,True)
    c.text(84,350,"first visible assert",25,INK)
    c.line([(84,391),(298,391)],RULE,2)
    c.text(84,410,"Full reward tests",25,BLUE,True)
    c.line([(318,351),(442,351)],INK,3,True)
    c.text(345,312,"prompt",24,MUTED)
    c.text(580,234,"Tiny Aya Global",32,INK,True,align="center")
    c.text(580,275,"3.35B",25,MUTED,align="center")
    network(c,502,382)
    c.line([(688,351),(874,351)],INK,3,True)
    c.text(710,309,"completions",24,MUTED)
    c.line([(318,429),(360,429),(360,490),(830,490),(830,376),(874,376)],BLUE,3,True)
    c.text(653,461,"full tests",25,BLUE)
    # The split is a selector, not two simultaneous callbacks.
    c.text(903,234,"Choose one reward callback",30,INK,True)
    c.circle(886,364,12,INK)
    c.line([(899,364),(936,316),(968,316)],ORANGE,3)
    c.line([(899,364),(936,428),(968,428)],BLUE,3)
    c.text(985,292,"AlignTune",31,ORANGE,True)
    c.text(985,333,"code_execution · 0.1.28",26,MUTED)
    c.text(985,403,"securegrade",31,BLUE,True)
    c.text(985,444,"0.1.0 core / 0.1.1 H",26,MUTED)
    c.text(1377,366,"or",25,MUTED,True)
    c.line([(1356,316),(1436,316),(1436,570),(755,570)],BLUE,3,True)
    c.line([(1356,428),(1436,428)],BLUE,3)
    c.text(950,520,"numeric rewards",27,BLUE,True)
    c.text(1190,590,"[r0, r1, ...]",27,BLUE,True)
    cycle(c,483,570)
    c.text(526,541,"GRPO",33,INK,True)
    c.text(526,581,"AlignTune / TRL",25,MUTED)

    c.line([(64,654),(1408,654)],INK,2)
    c.text(64,678,"Inside securegrade",34,INK,True)
    c.text(445,685,"The tests stay with the caller.",29,MUTED)
    c.box((64,750,603,1010),BLUE_WASH)
    c.text(88,766,"CALLER",24,BLUE,True)
    document(c,88,817,95,146,BLUE,"tests")
    c.text(213,799,"Expected values",28,INK,True)
    for x in (235,299,363):
        c.circle(x,864,19,WHITE,BLUE,2)
        c.line([(x-8,864),(x+8,864)],BLUE,3)
    c.text(213,923,"Validate / decode",27,BLUE,True)
    c.text(213,964,"Compare built-in values",26,BLUE,True)
    c.text(91,976,"Tests",23,MUTED)
    c.line([(603,835),(1000,835)],BLUE,3,True)
    c.text(656,789,"arguments only",27,BLUE,True)
    c.line([(1000,952),(603,952)],INK,3,True)
    c.text(635,907,"untrusted return data",26,INK,True)
    c.text(657,973,"type-tagged JSON",24,MUTED)
    c.line([(866,748),(866,1010)],RULE,2,dashed=True)
    c.circle(1091,888,105,PAPER,INK,2)
    document(c,1044,822,93,133,INK)
    c.text(1217,819,"Fresh",30,INK,True)
    c.text(1217,859,"interpreter",30,INK,True)
    c.text(1217,918,"Candidate",25,MUTED)
    c.text(1217,952,"code",25,MUTED)
    c.line([(64,1042),(1408,1042)],INK,2)
    # A magnifier is the side audit, not a part of training.
    c.circle(86,1090,22,PAPER,INK,3)
    c.line([(102,1106),(120,1124)],INK,5)
    c.text(146,1059,"Separate audit",24,MUTED,True)
    c.text(146,1093,"rewardcheck",32,INK,True)
    c.line([(383,1114),(467,1114)],MUTED,3,True,dashed=True)
    c.text(499,1065,"AlignTune · SafeTune · securegrade",30,INK,True)
    c.text(499,1110,"Reference, nonanswer and test-wiring controls",26,MUTED)
    c.image.save(OUT/"architecture-astra.png",optimize=True)
    c.save_svg(OUT/"architecture-astra.svg")
    ET.parse(OUT/"architecture-astra.svg")
    return c.image.size


def trace(c,points,fraction,color=ORANGE,width=7):
    lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
    remaining=sum(lengths)*max(0,min(1,fraction))
    for a,b,length in zip(points,points[1:],lengths):
        if remaining<=0:
            return
        ratio=min(1,remaining/length)
        end=(a[0]+(b[0]-a[0])*ratio,a[1]+(b[1]-a[1])*ratio)
        c.line([a,end],color,width)
        remaining-=length


def candidate(c,x,y,reference=False,stopped=False,small=False):
    w,h=(150,184) if small else (220,215)
    document(c,x,y,w,h,BLUE if reference else INK)
    if stopped:
        c.box((x-12,y+h-62,x+w+12,y+h-14),INK)
        c.text(x+w/2,y+h-51,"ENDED",24,WHITE,True,align="center")


def footer(c,stage,text):
    c.line([(64,855),(1408,855)],RULE,2)
    c.text(64,881,stage,24,MUTED,True)
    c.text(1408,881,text,24,MUTED,align="right")


def history_frame(t):
    c=Canvas()
    heading(c,"02 / ONE NONANSWER, TWO VERDICTS","Same nonanswer, different verdict")
    c.text(64,191,"Historical AlignTune 0.1.28",32,ORANGE,True)
    c.text(64,236,"code_verifiable · fenced assert-test path",27,MUTED)
    c.line([(64,369),(1030,369)],RULE,2)
    c.line([(64,369),(64,668),(1030,668),(1030,369)],RULE,2)
    c.text(97,383,"EARLY-EXIT NONANSWER",24,INK,True)
    candidate(c,115,430,stopped=t>=1.0)
    c.text(605,383,"APPENDED TESTS",24,MUTED,True)
    document(c,655,430,180,213,RULE,"tests")
    c.line([(355,540),(628,540)],RULE,3,dashed=True)
    trace(c,[(93,651),(370,651),(370,608)],ease(t/.95),ORANGE,7)
    if t>=1.0:
        c.line([(355,608),(385,608)],ORANGE,7)
        c.text(224,682,"process terminates",26,ORANGE,True,align="center")
        c.text(889,484,"NEVER",28,ORANGE,True)
        c.text(889,522,"RUN",28,ORANGE,True)
    if t>=1.2:
        c.text(586,303,"exit status reaches the grader",27,ORANGE,True)
        trace(c,[(370,481),(415,481),(415,341),(1240,341),(1240,449)],ease((t-1.2)/1.1),ORANGE,6)
    if t>=2.3:
        c.text(1240,452,"1.0",115,ORANGE,True,align="center")
        c.text(1240,584,"REWARD",24,ORANGE,True,align="center")
    if t>=2.5:
        c.text(64,756,"The tests never ran. The nonanswer still earned full credit.",36,INK,True)
    footer(c,"1 / THE HISTORICAL FAILURE","Exit alone; no printed success signal")
    return c.image


def secure_frame(t,reference=False):
    c=Canvas()
    heading(c,"02 / ONE NONANSWER, TWO VERDICTS","Same nonanswer, different verdict")
    c.text(64,191,"Independent securegrade",32,BLUE,True)
    c.text(64,236,"Supplied-reference positive control" if reference else "The same early-exit nonanswer",27,MUTED)
    c.line([(577,318),(577,705)],RULE,2,dashed=True)
    c.circle(225,538,147,PAPER,INK,2)
    candidate(c,150,445,reference,stopped=(not reference and t>=1.0),small=True)
    c.text(225,697,"Fresh interpreter",26,MUTED,True,align="center")
    c.text(760,356,"CALLER",24,BLUE,True)
    c.box((755,400,1110,656),BLUE_WASH)
    document(c,780,424,90,137,BLUE,"tests",checks=sum(t>=1.9+i*.22 for i in range(3)) if reference else 0)
    c.text(895,417,"Expected",26,INK,True)
    c.text(895,451,"values",26,INK,True)
    for x in (912,961,1010):
        c.circle(x,516,16,WHITE,BLUE,2)
        c.line([(x-6,516),(x+6,516)],BLUE,3)
    c.text(783,576,"Validate / decode",26,BLUE,True)
    c.text(783,614,"then compare",26,BLUE,True)
    c.line([(777,329),(225,329),(225,383)],RULE,3,True)
    c.text(365,288,"arguments only",26,BLUE,True)
    trace(c,[(777,329),(225,329),(225,383)],ease(t/.7),BLUE,5)
    c.line([(372,568),(739,568)],RULE,3,dashed=True)
    if reference:
        c.text(415,609,"return data",26,INK,True)
        if .6<=t<1.55:
            x=390+320*ease((t-.6)/.95)
            c.box((x-30,546,x+30,590),INK)
            for i in range(3):
                c.circle(x-17+i*17,568,4,WHITE)
        if t>=1.55:
            trace(c,[(711,568),(755,568)],ease((t-1.55)/.35),BLUE,5)
        if t>=2.45:
            c.text(1248,452,"1.0",115,BLUE,True,align="center")
            c.text(1248,584,"REWARD",24,BLUE,True,align="center")
        if t>=2.0:
            c.text(64,756,"Returned data is checked against expected values in the caller.",34,INK,True)
        footer(c,"3 / THE POSITIVE CONTROL","Supplied reference, not every correct program")
    else:
        if t>=1.0:
            c.line([(482,555),(508,581)],INK,4)
            c.line([(508,555),(482,581)],INK,4)
            c.text(415,609,"no return",27,INK,True)
            c.text(780,691,"Nothing to compare",27,BLUE,True)
        if t>=1.7:
            c.text(1248,452,"0.0",115,BLUE,True,align="center")
            c.text(1248,584,"REWARD",24,BLUE,True,align="center")
        if t>=1.9:
            c.text(64,756,"No returned result. No credit for the process ending.",36,INK,True)
        footer(c,"2 / THE INDEPENDENT DESIGN","Tests and expected values never leave the caller")
    return c.image


def summary_frame():
    c=Canvas()
    heading(c,"02 / ONE NONANSWER, TWO VERDICTS","Same nonanswer, different verdict")
    document(c,691,190,90,106,INK)
    c.box((663,248,809,285),INK)
    c.text(736,255,"NO ANSWER",21,WHITE,True,align="center")
    c.line([(658,249),(340,249),(340,340)],ORANGE,3,True)
    c.line([(814,249),(1110,249),(1110,340)],BLUE,3,True)
    c.text(64,367,"Historical AlignTune 0.1.28",32,ORANGE,True)
    c.text(64,410,"code_verifiable · fenced assert tests",25,MUTED)
    c.text(815,367,"Independent securegrade",32,BLUE,True)
    c.text(815,410,"Tests + expected values stay in the caller",25,MUTED)
    c.text(64,468,"1.0",122,ORANGE,True)
    c.text(306,485,"Tests skipped.\nExit earns credit.",31,INK,True)
    c.text(815,468,"0.0",122,BLUE,True)
    c.text(1065,485,"No returned result.\nNothing to verify.",30,INK,True)
    c.line([(736,361),(736,624)],RULE,2)
    c.line([(64,667),(1408,667)],INK,2)
    c.text(64,690,"POSITIVE CONTROL / SECUREGRADE",24,BLUE,True)
    document(c,64,747,55,70,BLUE)
    c.text(143,753,"Supplied reference",29,INK,True)
    c.line([(415,773),(474,773)],BLUE,3,True)
    c.text(503,746,"Return data",29,INK,True)
    c.text(503,784,"validate / decode",24,MUTED)
    c.line([(702,773),(759,773)],BLUE,3,True)
    c.text(788,746,"Caller compares",29,INK,True)
    c.text(788,784,"with expected values",24,MUTED)
    c.line([(1035,773),(1137,773)],BLUE,3,True)
    c.text(1182,721,"1.0",77,BLUE,True)
    footer(c,"ILLUSTRATED MECHANISMS","Historical callback ≠ current release")
    return c.image


PHASES=[
    ("execution_starts",0,1000,800,"Historical execution enters the nonanswer; appended checks wait."),
    ("terminates_before_tests",1000,2400,1700,"Candidate terminates. Only its exit status reaches the grader; tests do not run."),
    ("historical_credit",2400,4400,3600,"Historical code_verifiable gives the nonanswer reward 1.0."),
    ("caller_keeps_tests",4400,6100,5800,"securegrade sends arguments only; the same candidate terminates without a return."),
    ("no_result_no_credit",6100,8400,7400,"Caller has no returned result to compare, so reward is 0.0."),
    ("reference_returns_data",8400,10300,9600,"Supplied reference returns candidate-originated data; caller validates and decodes it."),
    ("reference_checked",10300,12000,11300,"Caller comparisons succeed for the supplied reference; reward is 1.0."),
    ("final_comparison",12000,15200,14000,"Persistent summary of all three scoped outcomes."),
]


def frame_at(ms):
    if ms<4400:
        return history_frame(ms/1000)
    if ms<8400:
        return secure_frame((ms-4400)/1000)
    if ms<12000:
        return secure_frame((ms-8400)/1000,True)
    return summary_frame()


def animation():
    palette_source=Image.new("RGB",(W,H*4),PAPER)
    for i,ms in enumerate((3600,7400,11300,14000)):
        palette_source.paste(frame_at(ms),(0,H*i))
    palette=palette_source.quantize(colors=128,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
    frames=[]
    for ms in range(0,15200,80):
        check_deadline()
        frames.append(frame_at(ms).quantize(palette=palette,dither=Image.Dither.NONE))
    path=OUT/"same-nonanswer-astra.gif"
    frames[0].save(path,save_all=True,append_images=frames[1:],duration=80,disposal=1,optimize=False)
    summary_frame().save(OUT/"same-nonanswer-astra-poster.png",optimize=True)
    decoded,durations,offsets=[],[],[]
    with Image.open(path) as gif:
        assert "loop" not in gif.info,"GIF must play once"
        elapsed=0
        for i in range(gif.n_frames):
            gif.seek(i)
            offsets.append(elapsed)
            decoded.append(gif.convert("RGB").copy())
            durations.append(gif.info["duration"])
            elapsed+=durations[-1]
    assert elapsed==15200
    assert path.stat().st_size<3_000_000
    sheet=Image.new("RGB",(W,4*(H//2+52)),PAPER)
    d=ImageDraw.Draw(sheet)
    stages=[]
    for i,(name,start,end,sample,description) in enumerate(PHASES):
        idx=max(n for n,offset in enumerate(offsets) if offset<=sample)
        x,y=(i%2)*(W//2),(i//2)*(H//2+52)
        d.text((x+25,y+13),f"{sample/1000:.1f}s / {name.replace('_',' ')}",font=font(23,True),fill=INK)
        sheet.paste(decoded[idx].resize((W//2,H//2),Image.Resampling.LANCZOS),(x,y+52))
        stages.append(dict(name=name,start_ms=start,end_ms=end,sample_ms=sample,
                           decoded_frame=idx,description=description))
    sheet.save(OUT/"stages-astra-contact-sheet.png",optimize=True)
    return dict(dimensions=[W,H],duration_ms=elapsed,nominal_fps=12.5,
                generated_frames=len(frames),encoded_frames=len(decoded),
                encoded_frame_durations_ms=durations,loop_extension_present=False,
                playback="once; 3.2-second final hold, then retain summary",disposal=1,
                palette="one shared 128-color palette; no dithering",phases=stages)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    print("Rendering editorial objects + action storyboard (180-second deadline).",flush=True)
    dimensions=architecture()
    print("Architecture saved; rendering 190 animation frames.",flush=True)
    animation_info=animation()
    files={}
    for name in ("architecture-astra.png","architecture-astra.svg","same-nonanswer-astra.gif",
                 "same-nonanswer-astra-poster.png","stages-astra-contact-sheet.png"):
        raw=(OUT/name).read_bytes()
        entry=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        if name.endswith(".png"):
            with Image.open(io.BytesIO(raw)) as im:
                im.verify()
            with Image.open(io.BytesIO(raw)) as im:
                entry["dimensions"]=list(im.size)
        files[name]=entry
    sources=["ARTICLE-DRAFT-v2.md","results/gate1-2026-11-01.md","securegrade/README.md",
             "harness/README.md","design/RUNS-2026-11-02.md","design/HOLE-PAIR-2026-11-04.md"]
    manifest=dict(schema=2,design="Astra editorial redesign; explanatory schematics, not new measurements",
                  runtime=dict(python=platform.python_version(),pillow=PILLOW_VERSION),
                  fonts=[dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in FONT_PATHS],
                  renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  architecture_dimensions=list(dimensions),animation=animation_info,outputs=files,
                  source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources})
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    check_deadline()
    print(json.dumps(dict(elapsed_seconds=round(time.monotonic()-STARTED,2),
                          gif_bytes=files["same-nonanswer-astra.gif"]["bytes"],
                          gif_frames=animation_info["encoded_frames"],duration_ms=15200,
                          output_directory=str(OUT)),indent=2),flush=True)


if __name__=="__main__":
    if hasattr(signal,"SIGALRM"):
        def expired(signum,frame):
            raise TimeoutError("Rendering exceeded the 180-second deadline")
        signal.signal(signal.SIGALRM,expired)
        signal.alarm(TIMEOUT_SECONDS)
    main()
