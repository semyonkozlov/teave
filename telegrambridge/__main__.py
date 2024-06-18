import pika


def main():
    connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = connection.channel()

    channel.queue_declare(queue="submits", durable=True)

    try:
        while True:
            print(f" [*] Input message")
            content = input()
            channel.basic_publish(
                exchange="",
                routing_key="submits",
                body=content,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                ),
            )
            print(f" [x] Sent")

    finally:
        print(f"Connection closed")
        connection.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
