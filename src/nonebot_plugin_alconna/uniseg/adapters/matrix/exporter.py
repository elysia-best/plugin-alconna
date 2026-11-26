from mimetypes import guess_type
from pathlib import Path
from typing import Any, Sequence

from nonebot.adapters import Bot, Event
from nonebot.adapters.matrix.bot import Bot as MatrixBot
from nonebot.adapters.matrix.event import MessageEvent
from nonebot.adapters.matrix.message import Message, MessageSegment

from nonebot_plugin_alconna.uniseg.constraint import SupportScope
from nonebot_plugin_alconna.uniseg.exporter import MessageExporter, SerializeFailed, SupportAdapter, Target, export
from nonebot_plugin_alconna.uniseg.segment import At, Audio, Emoji, File, Image, Reply, Segment, Text, Video, Voice


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
        if "html" in seg.extract_most_styles():
            return MessageSegment.html(seg.text, seg.text)
        return MessageSegment.text(seg.text)

    @export
    async def at(self, seg: At, bot: Bot | None) -> MessageSegment:
        if seg.flag != "user":
            raise SerializeFailed(f"Matrix does not support {seg.flag} mentions")
        return MessageSegment.mention_user(seg.target, seg.display)

    @export
    async def emoji(self, seg: Emoji, bot: Bot | None) -> MessageSegment:
        return MessageSegment.text(seg.name or seg.id)

    @export
    async def media(self, seg: Image | Voice | Video | Audio | File, bot: Bot | None) -> MessageSegment:
        method = getattr(MessageSegment, "audio" if isinstance(seg, Voice) else seg.__class__.__name__.lower())
        if seg.raw:
            content = seg.raw_bytes
        elif seg.path:
            content = Path(seg.path).read_bytes()
        else:
            raise SerializeFailed(f"invalid media segment: {seg}")
        filename = None if seg.name == seg.__default_name__ else seg.name
        # Guess content type if empty, Matrix requires content type for media segments!
        content_type = seg.mimetype or guess_type(str(seg.path or filename or seg.url or seg.name))[0]
        return method(content, filename=filename, body=filename, content_type=content_type)

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
