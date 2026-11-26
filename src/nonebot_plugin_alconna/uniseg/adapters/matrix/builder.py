from typing import TYPE_CHECKING

from nonebot.adapters import Bot, Event
from nonebot.adapters.matrix.event import MessageEvent
from nonebot.adapters.matrix.message import MessageSegment

from nonebot_plugin_alconna.uniseg.builder import MessageBuilder, build
from nonebot_plugin_alconna.uniseg.constraint import SupportAdapter
from nonebot_plugin_alconna.uniseg.segment import At, Audio, File, Image, Reply, Text, Video


class MatrixMessageBuilder(MessageBuilder[MessageSegment]):
    @classmethod
    def get_adapter(cls) -> SupportAdapter:
        return SupportAdapter.matrix

    @build("text", "notice", "emote")
    def text(self, seg: MessageSegment):
        return Text(seg.data["text"])

    @build("html")
    def html(self, seg: MessageSegment):
        body = seg.data["body"]
        return Text(body).mark(0, len(body), "html")

    @build("mention_user")
    def mention_user(self, seg: MessageSegment):
        return At("user", str(seg.data["user_id"]), seg.data.get("display_name"))

    @build("reply")
    def reply(self, seg: MessageSegment):
        return Reply(str(seg.data["event_id"]), origin=seg)

    @build("image")
    def image(self, seg: MessageSegment):
        return Image(
            url=seg.data.get("url"),
            raw=seg.data.get("content"),
            mimetype=seg.data.get("content_type"),
            name=seg.data.get("filename") or seg.data.get("body") or "image.png",
        )

    @build("file")
    def file(self, seg: MessageSegment):
        return File(
            url=seg.data.get("url"),
            raw=seg.data.get("content"),
            mimetype=seg.data.get("content_type"),
            name=seg.data.get("filename") or seg.data.get("body") or "file.bin",
        )

    @build("audio")
    def audio(self, seg: MessageSegment):
        return Audio(
            url=seg.data.get("url"),
            raw=seg.data.get("content"),
            mimetype=seg.data.get("content_type"),
            name=seg.data.get("filename") or seg.data.get("body") or "audio.mp3",
        )

    @build("video")
    def video(self, seg: MessageSegment):
        return Video(
            url=seg.data.get("url"),
            raw=seg.data.get("content"),
            mimetype=seg.data.get("content_type"),
            name=seg.data.get("filename") or seg.data.get("body") or "video.mp4",
        )

    async def extract_reply(self, event: Event, bot: Bot):
        if TYPE_CHECKING:
            assert isinstance(event, MessageEvent)
        if isinstance(event, MessageEvent) and event.reply:
            return Reply(str(event.reply))
        return None
