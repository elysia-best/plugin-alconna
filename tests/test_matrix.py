from unittest.mock import ANY

import pytest
from nonebot import get_adapter
from nonebot.adapters.matrix import Adapter, Message, MessageEvent, MessageSegment
from nonebot.adapters.matrix.api.model import WhoamiResponse
from nonebot.adapters.matrix.bot import Bot as MatrixBot
from nonebot.adapters.matrix.config import BotInfo
from nonebug import App


def make_message_event(message: Message | None = None, reply: str | None = None) -> MessageEvent:
    event = MessageEvent.model_validate(
        {
            "type": "m.room.message",
            "content": {"msgtype": "m.text", "body": "hello"},
            "event_id": "$event:example.org",
            "sender": "@alice:example.org",
            "room_id": "!room:example.org",
            "to_me": True,
        }
    )
    if message is not None:
        event._message = message
    event.reply = reply
    return event


def test_matrix_builder_and_export():
    from nonebot_plugin_alconna import At, Image, Reply, Text, UniMessage, Voice
    from nonebot_plugin_alconna.uniseg.adapters.matrix.builder import MatrixMessageBuilder

    builder = MatrixMessageBuilder()
    segs = builder.generate(
        Message(
            [
                MessageSegment.text("hello"),
                MessageSegment.mention_user("@alice:example.org", "Alice"),
                MessageSegment.reply("$reply:example.org"),
                MessageSegment.image("mxc://example.org/image", body="image.png"),
                MessageSegment.voice(
                    "mxc://example.org/voice",
                    duration=952,
                    filename="Voice message.ogg",
                    body="Voice message",
                    content_type="audio/ogg",
                ),
            ]
        )
    )

    assert segs[0] == Text("hello")
    assert segs[1] == At("user", "@alice:example.org", "Alice")
    assert isinstance(segs[2], Reply)
    assert segs[2].id == "$reply:example.org"
    assert segs[2].origin == MessageSegment.reply("$reply:example.org")
    assert segs[3] == Image(url="mxc://example.org/image", mimetype="image/png", name="image.png")
    assert segs[4] == Voice(
        url="mxc://example.org/voice",
        duration=0.952,
        mimetype="audio/ogg",
        name="Voice message.ogg",
    )

    exported = (
        UniMessage.text("hello").at("@alice:example.org").reply("$reply:example.org").export_sync(adapter="Matrix")
    )
    assert exported == Message(
        [
            MessageSegment.text("hello"),
            MessageSegment.mention_user("@alice:example.org"),
            MessageSegment.reply("$reply:example.org"),
        ]
    )


def test_matrix_builder_preserves_media_metadata_and_room_mention():
    from nonebot_plugin_alconna import AtAll, Audio, File, Image, Text, Video
    from nonebot_plugin_alconna.uniseg.adapters.matrix.builder import MatrixMessageBuilder

    segments = MatrixMessageBuilder().generate(
        Message(
            [
                MessageSegment.mention_room(),
                MessageSegment.sticker(
                    "mxc://example.org/sticker",
                    body="sticker.webp",
                    content_type="image/webp",
                    info={"w": 128, "h": 64},
                ),
                MessageSegment.audio(
                    "mxc://example.org/audio",
                    body="audio.ogg",
                    content_type="audio/ogg",
                    info={"duration": 3000},
                ),
                MessageSegment.video(
                    "mxc://example.org/video",
                    body="video.mp4",
                    content_type="video/mp4",
                    info={"duration": 2000},
                ),
                MessageSegment.file(
                    "mxc://example.org/file",
                    body="document.pdf",
                    content_type="application/pdf",
                ),
            ]
        )
    )

    assert segments[0] == AtAll()
    assert segments[1] == Image(
        url="mxc://example.org/sticker",
        mimetype="image/webp",
        name="sticker.webp",
        width=128,
        height=64,
        sticker=True,
    )
    assert segments[2] == Audio(url="mxc://example.org/audio", mimetype="audio/ogg", name="audio.ogg", duration=3)
    assert segments[3] == Video(url="mxc://example.org/video", mimetype="video/mp4", name="video.mp4", duration=2)
    assert segments[4] == File(url="mxc://example.org/file", mimetype="application/pdf", name="document.pdf")

    styled = MatrixMessageBuilder().generate(Message([MessageSegment.notice("notice"), MessageSegment.emote("waves")]))
    assert styled == [Text("notice", {(0, 6): ["notice"]}), Text("waves", {(0, 5): ["emote"]})]


@pytest.mark.asyncio()
async def test_matrix_exporter_sends_room_mention_and_sticker():
    from nonebot_plugin_alconna import AtAll, Image, Text
    from nonebot_plugin_alconna.uniseg.adapters.matrix.exporter import MatrixMessageExporter

    exporter = MatrixMessageExporter()
    mention = await exporter.export([AtAll()], None, False)
    assert mention[0].type == "mention_room"
    sticker = await exporter.export([Image(raw=b"webp", sticker=True)], None, False)
    assert sticker[0].type == "sticker"
    assert sticker[0].data["content"] == b"webp"
    notice = await exporter.export([Text("notice", {(0, 6): ["notice"]})], None, False)
    emote = await exporter.export([Text("waves", {(0, 5): ["emote"]})], None, False)
    assert notice[0].type == "notice"
    assert emote[0].type == "emote"


@pytest.mark.asyncio()
async def test_matrix_media_export_downloads_mxc(app: App, monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_alconna import Audio, File, Image, Video, Voice
    from nonebot_plugin_alconna.uniseg.adapters.matrix.exporter import MatrixMessageExporter

    async with app.test_api() as ctx:
        adapter = get_adapter(Adapter)
        bot = ctx.create_bot(
            base=MatrixBot,
            adapter=adapter,
            self_id="@bot:example.org",
            bot_info=BotInfo(
                homeserver="https://matrix.example.org",
                access_token="test-token",
                user_id="@bot:example.org",
            ),
            self_info=WhoamiResponse(user_id="@bot:example.org"),
        )

        async def download_media(*, server_name: str, media_id: str):
            assert (server_name, media_id) == ("example.org", "media")
            return b"media"

        monkeypatch.setattr(bot, "download_media", download_media)
        exporter = MatrixMessageExporter()
        segments = [
            Image(url="mxc://example.org/media", mimetype="image/png"),
            File(url="mxc://example.org/media", mimetype="application/pdf"),
            Audio(url="mxc://example.org/media", mimetype="audio/ogg"),
            Video(url="mxc://example.org/media", mimetype="video/mp4"),
            Voice(url="mxc://example.org/media", duration=0.952, mimetype="audio/ogg"),
        ]
        for segment in segments:
            exported = await exporter.export([segment], bot, False)
            assert exported[0].data["content"] == b"media"
            assert exported[0].data["url"] is None
            assert exported[0].data["content_type"] == segment.mimetype
            assert exported[0].data["info"]["mimetype"] == segment.mimetype

        voice = await exporter.export(
            [Voice(raw=b"voice", duration=0.952, name="Voice message.ogg", mimetype="audio/ogg")],
            bot,
            False,
        )
        assert voice[0].type == "voice"
        assert voice[0].data["duration"] == 952
        assert voice[0].data["content_type"] == "audio/ogg"
        assert voice[0].data["info"]["mimetype"] == "audio/ogg"


@pytest.mark.asyncio()
async def test_matrix_image_fetch_downloads_mxc(app: App, monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_alconna import Image
    from nonebot_plugin_alconna.uniseg import image_fetch

    async with app.test_api() as ctx:
        adapter = get_adapter(Adapter)
        bot = ctx.create_bot(
            base=MatrixBot,
            adapter=adapter,
            self_id="@bot:example.org",
            bot_info=BotInfo(
                homeserver="https://matrix.example.org",
                access_token="test-token",
                user_id="@bot:example.org",
            ),
            self_info=WhoamiResponse(user_id="@bot:example.org"),
        )

        async def download_media(*, server_name: str, media_id: str):
            assert (server_name, media_id) == ("example.org", "media")
            return b"image-bytes"

        monkeypatch.setattr(bot, "download_media", download_media)
        image = Image(url="mxc://example.org/media")
        assert await image_fetch(make_message_event(), bot, {}, image) == b"image-bytes"

        async def request(_request):
            return type("Response", (), {"content": b"external-image-bytes"})()

        monkeypatch.setattr(adapter, "request", request)
        external_image = Image(url="https://example.org/image.png")
        assert await image_fetch(make_message_event(), bot, {}, external_image) == b"external-image-bytes"

        class CryptoStub:
            ready = True

            async def download_encrypted_file(self, file: dict[str, str]) -> bytes:
                assert file == {"url": "mxc://example.org/encrypted"}
                return b"encrypted-image-bytes"

        bot.crypto = CryptoStub()
        origin = MessageSegment.image("mxc://example.org/encrypted")
        origin.data["file"] = {"url": "mxc://example.org/encrypted"}
        encrypted_image = Image()
        encrypted_image.origin = origin
        assert await image_fetch(make_message_event(), bot, {}, encrypted_image) == b"encrypted-image-bytes"


@pytest.mark.asyncio()
async def test_matrix_extract_reply_decrypts_encrypted_target(app: App):
    from nonebot.adapters.matrix.api.model import RawMatrixEvent

    from nonebot_plugin_alconna.uniseg.adapters.matrix.builder import MatrixMessageBuilder

    class CryptoStub:
        async def decrypt_room_event(self, raw, *, room_id: str):
            assert room_id == "!room:example.org"
            assert raw.type == "m.room.encrypted"
            return RawMatrixEvent.model_validate(
                {
                    "type": "m.room.message",
                    "event_id": "$origin:example.org",
                    "sender": "@alice:example.org",
                    "room_id": room_id,
                    "content": {"msgtype": "m.text", "body": "decrypted content"},
                }
            )

    async with app.test_api() as ctx:
        adapter = get_adapter(Adapter)
        bot = ctx.create_bot(
            base=MatrixBot,
            adapter=adapter,
            self_id="@bot:example.org",
            bot_info=BotInfo(
                homeserver="https://matrix.example.org",
                access_token="test-token",
                user_id="@bot:example.org",
            ),
            self_info=WhoamiResponse(user_id="@bot:example.org"),
        )
        bot.crypto = CryptoStub()
        ctx.should_call_api(
            "get_room_event",
            {"room_id": "!room:example.org", "event_id": "$origin:example.org"},
            RawMatrixEvent.model_validate(
                {
                    "type": "m.room.encrypted",
                    "event_id": "$origin:example.org",
                    "sender": "@alice:example.org",
                    "room_id": "!room:example.org",
                    "content": {},
                }
            ),
        )

        reply = await MatrixMessageBuilder().extract_reply(make_message_event(reply="$origin:example.org"), bot)
        assert reply is not None
        assert reply.id == "$origin:example.org"
        assert reply.msg == Message("decrypted content")
        assert reply.origin.type == "m.room.message"


@pytest.mark.asyncio()
async def test_matrix_reply_and_send(app: App):
    from nonebot.adapters.matrix.api.model import RawMatrixEvent

    from nonebot_plugin_alconna import Emoji
    from nonebot_plugin_alconna.uniseg.adapters.matrix.builder import MatrixMessageBuilder
    from nonebot_plugin_alconna.uniseg.adapters.matrix.exporter import MatrixMessageExporter
    from nonebot_plugin_alconna.uniseg.target import Target

    async with app.test_api() as ctx:
        adapter = get_adapter(Adapter)
        bot = ctx.create_bot(
            base=MatrixBot,
            adapter=adapter,
            self_id="@bot:example.org",
            bot_info=BotInfo(
                homeserver="https://matrix.example.org", access_token="test-token", user_id="@bot:example.org"
            ),
            self_info=WhoamiResponse(user_id="@bot:example.org"),
        )
        event = make_message_event(reply="$origin:example.org")
        ctx.should_call_api(
            "get_room_event",
            {"room_id": "!room:example.org", "event_id": "$origin:example.org"},
            RawMatrixEvent.model_validate(
                {
                    "type": "m.room.message",
                    "event_id": "$origin:example.org",
                    "sender": "@alice:example.org",
                    "room_id": "!room:example.org",
                    "content": {
                        "msgtype": "m.sticker",
                        "body": "smile.webp",
                        "url": "mxc://example.org/sticker",
                        "info": {"mimetype": "image/webp"},
                    },
                }
            ),
        )

        builder = MatrixMessageBuilder()
        reply = await builder.extract_reply(event, bot)
        assert reply is not None
        assert reply.id == "$origin:example.org"
        assert reply.msg == Message(
            MessageSegment.sticker(
                "mxc://example.org/sticker",
                body="smile.webp",
                content_type="image/webp",
                info={"mimetype": "image/webp"},
            )
        )
        assert reply.origin.event_id == "$origin:example.org"

        exporter = MatrixMessageExporter()
        bot._encryption_states["!room:example.org"] = None
        ctx.should_call_send(event, Message(MessageSegment.text("hello")), bot=bot, txn_id="txn-id")
        await exporter.send_to(event, bot, Message(MessageSegment.text("hello")), txn_id="txn-id")

        ctx.should_call_api(
            "send_event",
            {
                "room_id": "!room:example.org",
                "event_type": "m.room.message",
                "txn_id": "txn-id",
                "content": {"msgtype": "m.text", "body": "hello"},
            },
            {"event_id": "$sent:example.org"},
        )
        await exporter.send_to(Target("!room:example.org"), bot, Message(MessageSegment.text("hello")), txn_id="txn-id")

        ctx.should_call_api(
            "redact_event",
            {
                "room_id": "!room:example.org",
                "event_id": "$sent:example.org",
                "txn_id": ANY,
                "reason": None,
            },
            {"event_id": "$redact:example.org"},
        )
        await exporter.recall("$sent:example.org", bot, event)

        ctx.should_call_api(
            "create_reaction",
            {
                "room_id": "!room:example.org",
                "event_id": "$sent:example.org",
                "key": "👍",
                "txn_id": ANY,
            },
            {"event_id": "$reaction:example.org"},
        )
        await exporter.reaction(Emoji("👍", "👍"), "$sent:example.org", bot, event)
