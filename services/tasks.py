from celery import shared_task

from services.utils.send_mail import send_order_confirmation_email
from services.utils.logger import logger


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_order_confirmation_email_task(self, to_email: str, order_id: int):
    """
    Runs on the Celery worker, off the request/response cycle — the webhook
    view returns immediately after queuing this instead of waiting on email I/O.
    """
    try:
        send_order_confirmation_email(to_email, order_id)
    except Exception as exc:
        logger.error("Failed to send confirmation email for Order #%s: %s", order_id, exc)
        raise self.retry(exc=exc)
