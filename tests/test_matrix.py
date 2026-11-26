from unittest.mock import ANY

import pytest
from nonebot import get_adapter
from nonebot.adapters.matrix import Adapter, Bot, Message, MessageEvent, MessageSegment
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
    from nonebot_plugin_alconna import At, Image, Reply, Text, UniMessage
    from nonebot_plugin_alconna.uniseg.adapters.matrix.builder import MatrixMessageBuilder

    builder = MatrixMessageBuilder()
    segs = builder.generate(
        Message(
            [
                MessageSegment.text("hello"),
                MessageSegment.mention_user("@alice:example.org", "Alice"),
                MessageSegment.reply("$reply:example.org"),
                MessageSegment.image("mxc://example.org/image", body="image.png"),
            ]
        )
    )

    assert segs[0] == Text("hello")
    assert segs[1] == At("user", "@alice:example.org", "Alice")
    assert isinstance(segs[2], Reply)
    assert segs[2].id == "$reply:example.org"
    assert segs[2].origin == MessageSegment.reply("$reply:example.org")
    assert segs[3] == Image(url="mxc://example.org/image", name="image.png")

    exported = (
        UniMessage.text("hello")
        .at("@alice:example.org")
        .reply("$reply:example.org")
        .image(url="mxc://example.org/image", name="image.png")
        .export_sync(adapter="Matrix")
    )
    assert exported == Message(
        [
            MessageSegment.text("hello"),
            MessageSegment.mention_user("@alice:example.org"),
            MessageSegment.reply("$reply:example.org"),
            MessageSegment.image("mxc://example.org/image"),
        ]
    )


@pytest.mark.asyncio()
async def test_matrix_reply_and_send(app: App):
    from nonebot_plugin_alconna import Emoji, Reply
    from nonebot_plugin_alconna.uniseg.adapters.matrix.builder import MatrixMessageBuilder
    from nonebot_plugin_alconna.uniseg.adapters.matrix.exporter import MatrixMessageExporter
    from nonebot_plugin_alconna.uniseg.target import Target

    async with app.test_api() as ctx:
        adapter = get_adapter(Adapter)
        bot = ctx.create_bot(base=MatrixBot, adapter=adapter, self_id="@bot:example.org", bot_info=BotInfo(homeserver="https://matrix.example.org", access_token="test-token", user_id="@bot:example.org"), self_info=WhoamiResponse(user_id="@bot:example.org"))
        event = make_message_event(reply="$origin:example.org")

        builder = MatrixMessageBuilder()
        assert await builder.extract_reply(event, bot) == Reply("$origin:example.org")

        exporter = MatrixMessageExporter()
        ctx.should_call_send(event, Message(MessageSegment.text("hello")), bot=bot, txn_id="txn-id")
        await exporter.send_to(event, bot, Message(MessageSegment.text("hello")), txn_id="txn-id")

        ctx.should_call_api(
            "send_message",
            {
                "room_id": "!room:example.org",
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
