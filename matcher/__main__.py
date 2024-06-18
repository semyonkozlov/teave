import pika


def main():
    connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = connection.channel()

    channel.queue_declare(queue="submits", durable=True)

    def callback(ch, method, properties, body):
        print(f" [x] Received {body}")
        # ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_qos(prefetch_size=0)
    channel.basic_consume(queue="submits", on_message_callback=callback)

    print(" [*] Waiting for messages. To exit press CTRL+C")
    channel.start_consuming()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
