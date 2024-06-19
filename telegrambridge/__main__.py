import pika
import logging


def main():
    logging.basicConfig(level=logging.INFO)

    connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = connection.channel()

    channel.queue_declare(queue="submits", durable=True)

    try:
        for i in range(3):
            content = f"message {i}"
            channel.basic_publish(
                exchange="",
                routing_key="submits",
                body=content,
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                ),
            )
            logging.info(f"Message '{content}' sent")

    finally:
        logging.info(f"Connection closed")
        connection.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
