from mimetypes import guess_type
from pathlib import Path
from typing import Any, Sequence

from nonebot.adapters import Bot, Event
from nonebot.adapters.matrix.bot import Bot as MatrixBot
from nonebot.adapters.matrix.event import MessageEvent
from nonebot.adapters.matrix.message import Message, MessageSegment
from nonebot.internal.driver import Request

from nonebot_plugin_alconna.uniseg.constraint import SupportScope
from nonebot_plugin_alconna.uniseg.exporter import MessageExporter, SerializeFailed, SupportAdapter, Target, export
from nonebot_plugin_alconna.uniseg.segment import (
    At,
    AtAll,
    Audio,
    Emoji,
    File,
    Image,
    Media,
    Reply,
    Segment,
    Text,
    Video,
    Voice,
)


async def _media_content(seg: Media, bot: Bot | None) -> bytes:
    if seg.raw:
        return seg.raw_bytes
    if seg.path:
        return Path(seg.path).read_bytes()

    origin = seg.origin
    if isinstance(bot, MatrixBot) and isinstance(origin, MessageSegment) and isinstance(origin.data.get("file"), dict):
        return await bot.encryption().download_encrypted_file(origin.data["file"])

    if seg.url and seg.url.startswith("mxc://"):
        if not isinstance(bot, MatrixBot):
            raise SerializeFailed("Matrix mxc media requires a Matrix bot")
        try:
            server_name, media_id = seg.url[6:].split("/", 1)
        except ValueError as exc:
            raise SerializeFailed(f"invalid Matrix media URI: {seg.url}") from exc
        content = await bot.download_media(server_name=server_name, media_id=media_id)
        if isinstance(content, bytes):
            return content
        raise SerializeFailed("Matrix media download did not return bytes")

    if seg.url and bot:
        response = await bot.adapter.request(Request("GET", seg.url))
        return response.content
    raise SerializeFailed(f"invalid media segment: {seg}")


class MatrixMessageExporter(MessageExporter[Message]):
    @classmethod
    def get_adapter(cls) -> SupportAdapter:
        return SupportAdapter.matrix

    def get_message_type(self):
        return Message

    def get_target(self, event: Event, bot: Bot | None = None) -> Target:
        assert isinstance(event, MessageEvent)
        assert event.room_id is not None
        direct_rooms = getattr(bot, "direct_rooms", set()) if bot else set()
        return Target(
            str(event.room_id),
            private=bool(event.room_id in direct_rooms),
            source=str(event.event_id or ""),
            adapter=self.get_adapter(),
            self_id=bot.self_id if bot else None,
            scope=SupportScope.matrix,
        )

    def get_message_id(self, event: Event) -> str:
        assert isinstance(event, MessageEvent)
        assert event.event_id is not None
        return str(event.event_id)

    @export
    async def text(self, seg: Text, bot: Bot | None) -> MessageSegment | list[MessageSegment]:
        styles = seg.extract_most_styles()
        if "html" in styles:
            origin = seg.origin
            formatted_body = (
                origin.data.get("formatted_body")
                if isinstance(origin, MessageSegment) and origin.type == "html"
                else None
            )
            return MessageSegment.html(seg.text, formatted_body or seg.text)
        if "notice" in styles:
            return MessageSegment.notice(seg.text)
        if "emote" in styles:
            return MessageSegment.emote(seg.text)
        return MessageSegment.text(seg.text)

    @export
    async def at(self, seg: At, bot: Bot | None) -> MessageSegment:
        if seg.flag != "user":
            raise SerializeFailed(f"Matrix does not support {seg.flag} mentions")
        return MessageSegment.mention_user(seg.target, seg.display)

    @export
    async def at_all(self, seg: AtAll, bot: Bot | None) -> MessageSegment:
        return MessageSegment.mention_room()

    @export
    async def emoji(self, seg: Emoji, bot: Bot | None) -> MessageSegment:
        return MessageSegment.text(seg.name or seg.id)

    @export
    async def media(self, seg: Image | Voice | Video | Audio | File, bot: Bot | None) -> MessageSegment:
        content = await _media_content(seg, bot)
        filename = None if seg.name == seg.__default_name__ else seg.name
        content_type = seg.mimetype or guess_type(str(seg.path or filename or seg.url or seg.name))[0]
        info: dict[str, Any] = {"mimetype": content_type} if content_type else {}
        if isinstance(seg, Image):
            if seg.width is not None:
                info["w"] = seg.width
            if seg.height is not None:
                info["h"] = seg.height
        if isinstance(seg, (Audio, Video)) and seg.duration is not None:
            info["duration"] = round(seg.duration * 1000)
        if isinstance(seg, Voice):
            duration = round(seg.duration * 1000) if seg.duration is not None else None
            return MessageSegment.voice(
                content,
                duration=duration,
                filename=filename or seg.name,
                body="Voice message" if seg.name == seg.__default_name__ else seg.name,
                content_type=content_type or "audio/ogg",
                info=info,
            )
        method = (
            MessageSegment.sticker
            if isinstance(seg, Image) and seg.sticker
            else getattr(MessageSegment, seg.__class__.__name__.lower())
        )
        return method(
            content,
            filename=filename,
            body=filename,
            content_type=content_type,
            info=info,
        )

    @export
    async def reply(self, seg: Reply, bot: Bot | None) -> MessageSegment:
        return MessageSegment.reply(seg.id)

    async def send_to(self, target: Target | Event, bot: Bot, message: Message, **kwargs):
        assert isinstance(bot, MatrixBot)
        if isinstance(target, Event):
            return await bot.send(target, message, **kwargs)
        return await bot.send_to(target.id, message, **kwargs)

    async def recall(self, mid: Any, bot: Bot, context: Target | Event):
        assert isinstance(bot, MatrixBot)
        room_id = context.id if isinstance(context, Target) else context.room_id
        if room_id is None:
            raise SerializeFailed("Matrix recall requires room_id")
        await bot.redact(room_id, str(mid))

    async def edit(self, new: Sequence[Segment], mid: Any, bot: Bot, context: Target | Event):
        raise NotImplementedError

    async def reaction(self, emoji: Emoji, mid: Any, bot: Bot, context: Target | Event, delete: bool = False):
        if delete:
            raise NotImplementedError
        assert isinstance(bot, MatrixBot)
        room_id = context.id if isinstance(context, Target) else context.room_id
        if room_id is None:
            raise SerializeFailed("Matrix reaction requires room_id")
        await bot.react(room_id, str(mid), emoji.name or emoji.id)

    def get_reply(self, mid: Any):
        return Reply(str(mid))
