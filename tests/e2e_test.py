import aiormq

from common.models import Submit


def create_submit(user_type: str) -> Submit:
    return Submit.model_validate(
        {
            "user_type": user_type,
            "event_type": "trekking",
            "location": {"city": "Tbilisi"},
            "num_attendees": 4,
        }
    )


async def test_matcher_creates_event():
    connection = await aiormq.connect("amqp://guest:guest@rabbitmq/")
    channel = await connection.channel()
    await channel.queue_declare(queue="submits", durable=True)

    submit = create_submit(user_type="lead")
    await channel.basic_publish(
        submit.model_dump_json().encode(), routing_key="submits"
    )

    for _ in range(3):
        submit = create_submit(user_type="follower")
        await channel.basic_publish(
            submit.model_dump_json().encode(), routing_key="submits"
        )

    # TODO assert event q

    await connection.close()
