from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    InputMediaPhoto,
    InputRichBlockBlockQuotation,
    InputRichBlockFooter,
    InputRichBlockParagraph,
    InputRichBlockPhoto,
    InputRichBlockSectionHeading,
    InputRichMessage,
    Message,
    RichTextBold,
    RichTextItalic,
    RichTextMarked,
    RichTextUrl,
)

from app.security.media import validate_media_url
from app.services.cover_cache import cover_cache_service
from app.services.lyrics import LyricExcerpt, bound_excerpt_text

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CardDelivery:
    message: Message
    mode: str
    photo: str | bytes | None


def _plain(value: object, maximum: int = 300) -> str:
    return str(value or "").strip()[:maximum]


def _safe(value: object, maximum: int = 300) -> str:
    return html.escape(_plain(value, maximum))


def _validated_url(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw or len(raw) > 2048 or any(ord(char) < 32 for char in raw):
        return None
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "https" or port not in {None, 443} or parsed.username or parsed.password:
        return None
    if parsed.hostname not in {"open.spotify.com", "www.last.fm", "www.deezer.com"}:
        return None
    return raw


def _safe_url(value: object) -> str | None:
    raw = _validated_url(value)
    return html.escape(raw, quote=True) if raw else None


def _listener_identity(*, user_name: str, user_username: str | None) -> str | None:
    display_name = _plain(user_name, 100)
    username = _plain(str(user_username or "").strip().lstrip("@"), 64)
    if display_name:
        return display_name
    if username:
        return f"@{username}"
    return None


def _listener_line(*, user_id: int, user_name: str, user_username: str | None) -> str:
    identity = _listener_identity(user_name=user_name, user_username=user_username)
    if not identity:
        return "está ouvindo..."
    return f'<a href="tg://user?id={int(user_id)}">{html.escape(identity)}</a> está ouvindo...'


def _listener_rich_text(*, user_id: int, user_name: str, user_username: str | None) -> Any:
    identity = _listener_identity(user_name=user_name, user_username=user_username)
    if not identity:
        return "está ouvindo..."
    return [RichTextUrl(text=identity, url=f"tg://user?id={int(user_id)}"), " está ouvindo..."]


def _playcount_footer(track: dict[str, Any]) -> str | None:
    raw = track.get("user_playcount")
    if isinstance(raw, bool):
        return None
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return None
    if count < 0:
        return None
    return f"♫ {count} plays"


def _footer_text(track: dict[str, Any], footer: str | None) -> str | None:
    if footer is not None:
        value = _plain(footer, 160)
        return value or None
    return _playcount_footer(track)


def music_caption_html(
    track: dict[str, Any],
    *,
    user_id: int,
    user_name: str,
    user_username: str | None = None,
    lyric: LyricExcerpt | None = None,
    lyric_status: str | None = None,
    footer: str | None = None,
) -> str:
    title = _safe(track.get("track_name"))
    artist = _safe(track.get("artist"))
    track_url = _safe_url(track.get("spotify_url"))
    title_part = f'<a href="{track_url}"><b>{title}</b></a>' if track_url else f"<b>{title}</b>"
    lines = [
        _listener_line(user_id=user_id, user_name=user_name, user_username=user_username),
        f"{title_part} - <i>{artist}</i>",
    ]
    if lyric:
        lyric_text = bound_excerpt_text(lyric.text) or ""
        lines.append(f"<blockquote>{html.escape(lyric_text)}</blockquote>")
    elif lyric_status:
        lines.append(f"<i>{_safe(lyric_status, 120)}</i>")
    resolved_footer = _footer_text(track, footer)
    if resolved_footer:
        lines.append(html.escape(resolved_footer))
    return "\n".join(lines)


def music_rich_message(
    track: dict[str, Any],
    *,
    user_id: int,
    user_name: str,
    user_username: str | None = None,
    photo: str | bytes | None,
    lyric: LyricExcerpt | None = None,
    lyric_status: str | None = None,
    footer: str | None = None,
) -> InputRichMessage:
    title = _plain(track.get("track_name"))
    artist = _plain(track.get("artist"))
    track_url = _validated_url(track.get("spotify_url"))
    title_text: Any = RichTextUrl(text=title, url=track_url) if track_url else title

    # Bot API 10.2 native Rich Message blocks. No HTML conversion is used here.
    blocks: list[Any] = [
        InputRichBlockSectionHeading(
            text=_listener_rich_text(
                user_id=user_id,
                user_name=user_name,
                user_username=user_username,
            ),
            size=6,
        )
    ]

    if photo:
        rich_photo = BufferedInputFile(photo, filename="cover.jpg") if isinstance(photo, bytes) else photo
        blocks.append(InputRichBlockPhoto(photo=InputMediaPhoto(media=rich_photo)))

    # Keep the song line as one native RichText sequence: bold title - italic artist.
    blocks.append(
        InputRichBlockSectionHeading(
            text=[
                RichTextBold(text=title_text),
                " - ",
                RichTextItalic(text=artist),
            ],
            size=1,
        )
    )

    if lyric:
        lyric_text = bound_excerpt_text(lyric.text) or ""
        blocks.append(
            InputRichBlockBlockQuotation(
                blocks=[InputRichBlockParagraph(text=lyric_text)],
            )
        )
    elif lyric_status:
        blocks.append(
            InputRichBlockParagraph(
                text=RichTextMarked(text=_plain(lyric_status, 120))
            )
        )

    resolved_footer = _footer_text(track, footer)
    if resolved_footer:
        # Preserve plays as Telegram's native footer (gray footer appearance).
        blocks.append(InputRichBlockFooter(text=resolved_footer))

    return InputRichMessage(blocks=blocks, skip_entity_detection=True)


async def send_rich_text(message: Message, *, rich_html: str, fallback_html: str | None = None) -> Message:
    try:
        return await message.bot.send_rich_message(
            chat_id=message.chat.id,
            rich_message=InputRichMessage(html=rich_html, skip_entity_detection=True),
        )
    except Exception:
        logger.info("RICH_TEXT_FALLBACK")
        return await message.answer(fallback_html or rich_html, parse_mode="HTML", disable_web_page_preview=True)


async def send_music_card(
    bot: Bot,
    *,
    chat_id: int,
    track: dict[str, Any],
    user_id: int,
    user_name: str,
    user_username: str | None = None,
    lyric: LyricExcerpt | None = None,
    lyric_status: str | None = None,
    footer: str | None = None,
) -> CardDelivery:
    track_id = str(track.get("track_id") or "").strip() or None
    cover_url = validate_media_url(track.get("album_image_url"), kind="cover")
    photo = await cover_cache_service.resolve_photo(
        bot,
        track_id=track_id,
        cover_url=cover_url,
        filename="cover-hd.jpg",
    ) if cover_url else None
    rich = music_rich_message(
        track,
        user_id=user_id,
        user_name=user_name,
        user_username=user_username,
        photo=photo,
        lyric=lyric,
        lyric_status=lyric_status,
        footer=footer,
    )
    try:
        sent = await bot.send_rich_message(chat_id=chat_id, rich_message=rich)
        return CardDelivery(sent, "rich", photo)
    except Exception:
        logger.info("RICH_MUSIC_CARD_FALLBACK track_id=%s", track_id or "none")

    caption = music_caption_html(
        track,
        user_id=user_id,
        user_name=user_name,
        user_username=user_username,
        lyric=lyric,
        lyric_status=lyric_status,
        footer=footer,
    )
    if photo:
        fallback_photo = BufferedInputFile(photo, filename="cover-hd.jpg") if isinstance(photo, bytes) else photo
        try:
            sent = await bot.send_photo(chat_id=chat_id, photo=fallback_photo, caption=caption, parse_mode="HTML")
            return CardDelivery(sent, "photo", photo)
        except Exception:
            logger.info("PHOTO_MUSIC_CARD_FALLBACK track_id=%s", track_id or "none")
    sent = await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML", disable_web_page_preview=True)
    return CardDelivery(sent, "text", photo)


async def edit_music_card(
    delivery: CardDelivery,
    *,
    track: dict[str, Any],
    user_id: int,
    user_name: str,
    user_username: str | None = None,
    lyric: LyricExcerpt | None,
    lyric_status: str | None,
    footer: str | None = None,
) -> None:
    if delivery.mode == "rich":
        rich = music_rich_message(
            track,
            user_id=user_id,
            user_name=user_name,
            user_username=user_username,
            photo=delivery.photo,
            lyric=lyric,
            lyric_status=lyric_status,
            footer=footer,
        )
        try:
            await delivery.message.edit_text(text=None, rich_message=rich)
        except Exception:
            # Re-uploading embedded media during an edit can fail on older
            # clients/proxies. Preserve the requested same-message update by
            # retrying as plain HTML without an attachment.
            logger.info("RICH_MUSIC_EDIT_FALLBACK")
            caption = music_caption_html(
                track,
                user_id=user_id,
                user_name=user_name,
                user_username=user_username,
                lyric=lyric,
                lyric_status=lyric_status,
                footer=footer,
            )
            await delivery.message.edit_text(caption, parse_mode="HTML", disable_web_page_preview=True)
        return
    caption = music_caption_html(
        track,
        user_id=user_id,
        user_name=user_name,
        user_username=user_username,
        lyric=lyric,
        lyric_status=lyric_status,
        footer=footer,
    )
    if delivery.mode == "photo":
        await delivery.message.edit_caption(caption=caption, parse_mode="HTML")
    else:
        await delivery.message.edit_text(caption, parse_mode="HTML", disable_web_page_preview=True)
