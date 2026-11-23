"""外网视频解析：以内核 yt-dlp 解析外网站点的视频，下载后连卡片一起发进群。

说明：
- 识别、调度、体积控制、卡片绘制、消息发送都是本站自己写的；
- 真正的取流能力来自开源项目 yt-dlp（https://github.com/yt-dlp/yt-dlp，Unlicense）；
- 只处理外网站点，国内平台留给其它插件，避免撞车。
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time
import urllib.request
from pathlib import Path

import yt_dlp
from PIL import Image, ImageDraw, ImageFont

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

URL_RE = re.compile(r"https?://[^\s<>\"'\u3000]+", re.I)

# 只认这些外网站点；国内平台（B站、抖音、小红书……）故意不列
# 三元组：(展示名, 匹配正则, 配置键)。配置键对应 site_<key> 这个独立开关。
SITE_RULES: tuple[tuple[str, str, str], ...] = (
    ("YouTube", r"(?:youtube\.com|youtu\.be|youtube-nocookie\.com)", "youtube"),
    ("Twitter/X", r"(?:twitter\.com|x\.com|t\.co)", "twitter"),
    ("TikTok", r"tiktok\.com", "tiktok"),
    ("Instagram", r"instagram\.com", "instagram"),
    ("Facebook", r"(?:facebook\.com|fb\.watch)", "facebook"),
    ("Twitch", r"twitch\.tv", "twitch"),
    ("Vimeo", r"vimeo\.com", "vimeo"),
    ("Reddit", r"reddit\.com", "reddit"),
    ("Dailymotion", r"(?:dailymotion\.com|dai\.ly)", "dailymotion"),
    ("niconico", r"nicovideo\.jp", "niconico"),
    ("SoundCloud", r"soundcloud\.com", "soundcloud"),
    ("Bilibili 海外版", r"bilibili\.tv", "bilibili_tv"),
)

FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def pick_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def match_site(url: str) -> tuple[str, str] | None:
    """返回 (展示名, 配置键)，没命中就返回 None。"""
    for name, pattern, key in SITE_RULES:
        if re.search(pattern, url, re.I):
            return name, key
    return None


def fmt_duration(seconds) -> str:
    try:
        total = int(seconds or 0)
    except (TypeError, ValueError):
        return "未知"
    if total <= 0:
        return "未知"
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_count(value) -> str:
    try:
        num = int(value or 0)
    except (TypeError, ValueError):
        return "—"
    if num >= 100_000_000:
        return f"{num / 100_000_000:.1f}亿"
    if num >= 10_000:
        return f"{num / 10_000:.1f}万"
    return str(num)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, limit: int = 2) -> list[str]:
    """按像素宽度折行，超出行数时把最后一行换成省略号结尾。"""
    text = str(text or "")
    lines: list[str] = []
    current = ""
    for ch in text:
        trial = current + ch
        if font.getlength(trial) > max_width and current:
            lines.append(current)
            current = ch
            if len(lines) >= limit:
                lines[-1] = lines[-1][:-1].rstrip() + "…"
                return lines[:limit]
        else:
            current = trial
    if current:
        if len(lines) < limit:
            lines.append(current)
        else:
            lines[-1] = lines[-1][:-1].rstrip() + "…"
    return lines[:limit]


def draw_card(info: dict, cover: Path | None, platform: str, out_path: Path) -> Path:
    width, height = 900, 400
    canvas = Image.new("RGB", (width, height), "#12161f")
    draw = ImageDraw.Draw(canvas)

    # 封面：左侧 400x400 裁切填充
    if cover and cover.exists():
        try:
            with Image.open(cover) as raw:
                art = raw.convert("RGB")
                scale = max(400 / art.width, 400 / art.height)
                art = art.resize((max(1, int(art.width * scale)), max(1, int(art.height * scale))))
                left = (art.width - 400) // 2
                top = (art.height - 400) // 2
                art = art.crop((left, top, left + 400, top + 400))
                canvas.paste(art, (0, 0))
        except Exception:
            logger.warning("[yt_share] 封面处理失败", exc_info=True)

    # 右侧信息
    title_font = pick_font(38)
    meta_font = pick_font(26)
    tag_font = pick_font(22)

    x = 436
    draw.rounded_rectangle([x - 20, 34, x + 40, 74], radius=10, fill="#2f6bff")
    draw.text((x - 8, 40), platform[:3].upper(), font=tag_font, fill="#ffffff")

    y = 96
    for line in wrap_text(info.get("title") or "未命名视频", title_font, width - x - 44, limit=2):
        draw.text((x, y), line, font=title_font, fill="#f5f7ff")
        y += 46

    y += 10
    author = info.get("uploader") or info.get("channel") or "未知作者"
    draw.text((x, y), f"@{author}", font=meta_font, fill="#9db0d0")
    y += 42

    stats = [
        ("时长", fmt_duration(info.get("duration"))),
        ("播放", fmt_count(info.get("view_count"))),
        ("点赞", fmt_count(info.get("like_count"))),
    ]
    for label, value in stats:
        draw.text((x, y), f"{label}  {value}", font=meta_font, fill="#c6d4ef")
        y += 34

    draw.text((x, height - 34), "解析：外网视频解析 · 内核 yt-dlp", font=tag_font, fill="#5d6c88")
    canvas.save(out_path)
    return out_path


@register("yt_share", "lemonir", "外网视频解析（yt-dlp 内核）", "0.1.0")
class YtSharePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}
        self._last: dict[str, float] = {}
        self._workdir = Path(tempfile.gettempdir()) / "astrbot_yt_share"
        self._workdir.mkdir(parents=True, exist_ok=True)

    # ---------------- 配置读取 ----------------
    def _int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _bool(self, key: str, default: bool = True) -> bool:
        return bool(self.config.get(key, default))

    def _ydl_opts(self, extra: dict | None = None) -> dict:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 30,
            "retries": 2,
            "outtmpl": str(self._workdir / "%(id)s.%(ext)s"),
        }
        proxy = str(self.config.get("proxy") or "").strip()
        if proxy:
            opts["proxy"] = proxy
        if extra:
            opts.update(extra)
        return opts

    @staticmethod
    def _cleanup(pattern: str) -> None:
        for path in Path(tempfile.gettempdir()).glob(f"astrbot_yt_share/{pattern}*"):
            try:
                path.unlink()
            except OSError:
                pass

    # ---------------- 主流程 ----------------
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_any_message(self, event: AstrMessageEvent):
        if not self._bool("enable", True):
            return
        if str(event.get_sender_id() or "") == str(event.get_self_id() or ""):
            return

        text = event.message_str or ""
        if not text:
            return
        candidates = URL_RE.findall(text)
        if not candidates:
            return

        url, platform, site_key = None, None, None
        for candidate in candidates:
            hit = match_site(candidate)
            if hit:
                platform, site_key = hit
                url = candidate.rstrip("，。,.)）]】")
                break
        if not url:
            return
        # 站点级开关；总开关在上面已经拦过，这里关掉就是彻底不处理这个站
        if not self._bool(f"site_{site_key}", True):
            logger.debug(f"[yt_share] {platform} 的解析开关是关的，跳过：{url}")
            return

        scope = event.unified_msg_origin
        now = time.time()
        cooldown = self._int("cooldown_seconds", 30)
        if cooldown > 0 and now - self._last.get(scope, 0.0) < cooldown:
            return
        self._last[scope] = now

        logger.info(f"[yt_share] 识别到 {platform} 链接：{url}")
        try:
            async for part in self._handle(event, url, platform):
                yield part
        except Exception:
            logger.exception("[yt_share] 解析流程异常")

    async def _handle(self, event: AstrMessageEvent, url: str, platform: str):
        timeout = self._int("download_timeout_seconds", 180)
        max_h = self._int("max_height", 720)
        max_mb = self._int("max_size_mb", 50)

        # 1) 先取元数据
        try:
            info = await asyncio.wait_for(
                asyncio.to_thread(self._extract, url), timeout=60
            )
        except Exception as exc:
            logger.warning(f"[yt_share] 元数据获取失败：{exc}")
            return

        video_id = str(info.get("id") or "video")

        # 2) 封面 + 卡片
        card_path = None
        if self._bool("send_card", True):
            cover = await asyncio.to_thread(self._grab_cover, info, video_id)
            card_path = self._workdir / f"{video_id}_card.jpg"
            try:
                await asyncio.to_thread(draw_card, info, cover, platform, card_path)
            except Exception:
                logger.warning("[yt_share] 卡片绘制失败", exc_info=True)
                card_path = None

        # 3) 下载视频
        video_path = None
        if self._bool("send_video", True):
            try:
                video_path = await asyncio.wait_for(
                    asyncio.to_thread(self._download, url, max_h, max_mb), timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"[yt_share] 下载超时：{url}")
            except Exception as exc:
                logger.warning(f"[yt_share] 下载失败：{exc}")

        # 4) 发送
        parts: list = []
        if card_path and card_path.exists():
            parts.append(Comp.Image.fromFileSystem(str(card_path)))
        if video_path and video_path.exists():
            parts.append(Comp.Video.fromFileSystem(str(video_path)))
        if parts:
            yield event.chain_result(parts)
        elif self._bool("fallback_link_on_fail", False):
            # 默认关闭：群里大多数人没有代理，给了链接也点不开。
            # 只有管理员明确需要时才打开。
            yield event.plain_result(f"{platform} 这条没下成文件，原链接：{url}")
        # 开关关着就安静收场，不刷屏

        # 5) 收尾
        for path in (card_path, video_path):
            if path and Path(path).exists():
                try:
                    Path(path).unlink()
                except OSError:
                    pass

    # ---------------- 具体动作（同步，跑在线程里） ----------------
    def _extract(self, url: str) -> dict:
        with yt_dlp.YoutubeDL(self._ydl_opts({"skip_download": True})) as ydl:
            return ydl.extract_info(url, download=False)

    def _grab_cover(self, info: dict, video_id: str) -> Path | None:
        thumb = info.get("thumbnail")
        if not thumb:
            return None
        target = self._workdir / f"{video_id}_cover.jpg"
        if target.exists():
            return target
        try:
            req = urllib.request.Request(thumb, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp, target.open("wb") as fh:
                fh.write(resp.read())
            return target
        except Exception:
            logger.warning("[yt_share] 封面下载失败", exc_info=True)
            return None

    def _download(self, url: str, max_height: int, max_mb: int) -> Path | None:
        opts = self._ydl_opts({
            "format": (
                f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={max_height}]+bestaudio/"
                f"best[height<={max_height}]/best"
            ),
            "merge_output_format": "mp4",
        })
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
        if not path.exists():
            for candidate in self._workdir.glob(f"{info.get('id')}*"):
                if candidate.suffix.lower() in (".mp4", ".mkv", ".webm", ".m4a"):
                    path = candidate
                    break
        if not path.exists():
            return None
        if path.stat().st_size > max_mb * 1024 * 1024:
            logger.info(f"[yt_share] 文件 {path.stat().st_size/1048576:.1f}MB 超过上限，丢弃")
            try:
                path.unlink()
            except OSError:
                pass
            return None
        return path
