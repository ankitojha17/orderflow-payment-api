from django.conf import settings
from django.core.mail import send_mail

from services.utils.logger import logger


def send_order_confirmation_email(to_email: str, order_id: int) -> None:
    """
    Sends a plain-text confirmation email. Console backend in development
    prints this to the terminal instead of requiring real SMTP credentials.
    Called from services.tasks.send_order_confirmation_email_task (Celery),
    never synchronously from a request/response cycle.
    """
    if not to_email:
        logger.warning("Skipped confirmation email for Order #%s — user has no email.", order_id)
        return

    send_mail(
        subject=f"Order #{order_id} confirmed",
        message=f"Your order #{order_id} has been paid successfully. Thank you for shopping with OrderFlow!",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        # False on purpose: this always runs inside the Celery task, never
        # synchronously in a request/response cycle, so there's no user-facing
        # response to protect by swallowing the error. If send_mail() raises,
        # the task's except block below needs to actually see it in order to
        # retry — fail_silently=True would hide the failure and let Celery
        # think the email went out when it didn't.
        fail_silently=False,
    )
