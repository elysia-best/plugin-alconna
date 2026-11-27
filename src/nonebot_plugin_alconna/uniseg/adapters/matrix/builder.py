from typing import TYPE_CHECKING

from nonebot.adapters import Bot, Event
from nonebot.adapters.matrix.event import MessageEvent
from nonebot.adapters.matrix.message import MessageSegment

from nonebot_plugin_alconna.uniseg.builder import MessageBuilder, build
from nonebot_plugin_alconna.uniseg.constraint import SupportAdapter
from nonebot_plugin_alconna.uniseg.segment import (
    At,
    AtAll,
    Audio,
    File,
    Image,
    Reply,
    Text,
    Video,
    Voice,
)


class MatrixMessageBuilder(MessageBuilder[MessageSegment]):
    @classmethod
    def get_adapter(cls) -> SupportAdapter:
        return SupportAdapter.matrix

    @build("text", "notice", "emote")
    def text(self, seg: MessageSegment):
        result = Text(seg.data["text"])
        if seg.type != "text" and result.text:
            result.mark(0, len(result.text), seg.type)
        return result

    @build("html")
    def html(self, seg: MessageSegment):
        body = seg.data["body"]
        return Text(body).mark(0, len(body), "html")

    @build("mention_user")
    def mention_user(self, seg: MessageSegment):
        return At("user", str(seg.data["user_id"]), seg.data.get("display_name"))

    @build("mention_room")
    def mention_room(self, seg: MessageSegment):
        return AtAll()

    @build("reply")
    def reply(self, seg: MessageSegment):
        return Reply(str(seg.data["event_id"]), origin=seg)

    @build("image")
    def image(self, seg: MessageSegment):
        info = seg.data.get("info") or {}
        return Image(
            url=seg.data.get("url"),
            raw=seg.data.get("content"),
            mimetype=seg.data.get("content_type") or info.get("mimetype"),
            name=seg.data.get("filename") or seg.data.get("body") or "image.png",
            width=info.get("w"),
            height=info.get("h"),
        )

    @build("file")
    def file(self, seg: MessageSegment):
        info = seg.data.get("info") or {}
        return File(
            url=seg.data.get("url"),
            raw=seg.data.get("content"),
            mimetype=seg.data.get("content_type") or info.get("mimetype"),
            name=seg.data.get("filename") or seg.data.get("body") or "file.bin",
        )

    @build("audio")
    def audio(self, seg: MessageSegment):
        info = seg.data.get("info") or {}
        duration = info.get("duration")
        return Audio(
            url=seg.data.get("url"),
            raw=seg.data.get("content"),
            mimetype=seg.data.get("content_type") or info.get("mimetype"),
            name=seg.data.get("filename") or seg.data.get("body") or "audio.mp3",
            duration=duration / 1000 if isinstance(duration, int) else None,
        )

    @build("video")
    def video(self, seg: MessageSegment):
        info = seg.data.get("info") or {}
        duration = info.get("duration")
        return Video(
            url=seg.data.get("url"),
            raw=seg.data.get("content"),
            mimetype=seg.data.get("content_type") or info.get("mimetype"),
            name=seg.data.get("filename") or seg.data.get("body") or "video.mp4",
            duration=duration / 1000 if isinstance(duration, int) else None,
        )

    @build("sticker")
    def sticker(self, seg: MessageSegment):
        info = seg.data.get("info") or {}
        return Image(
            url=seg.data.get("url"),
            raw=seg.data.get("content"),
            mimetype=seg.data.get("content_type") or info.get("mimetype"),
            name=seg.data.get("filename") or seg.data.get("body") or "sticker.webp",
            width=info.get("w"),
            height=info.get("h"),
            sticker=True,
        )

    @build("voice")
    def voice(self, seg: MessageSegment):
        info = seg.data.get("info") or {}
        duration = seg.data.get("duration")
        if not isinstance(duration, int):
            duration = info.get("duration")
        return Voice(
            url=seg.data.get("url"),
            raw=seg.data.get("content"),
            mimetype=seg.data.get("content_type") or info.get("mimetype"),
            duration=duration / 1000 if isinstance(duration, int) else None,
            name=seg.data.get("filename") or seg.data.get("body") or "voice.wav",
        )

    async def extract_reply(self, event: Event, bot: Bot):
        if TYPE_CHECKING:
            assert isinstance(event, MessageEvent)
        if isinstance(event, MessageEvent) and event.reply:
            return Reply(str(event.reply))
        return None
