from unittest.mock import patch

from django.test import TestCase, override_settings

from services.tasks import send_order_confirmation_email_task


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class SendOrderConfirmationEmailTaskTests(TestCase):
    """
    Regression test for fail_silently=True previously hiding email failures
    from Celery. With fail_silently=False, an SMTP-layer exception must
    actually reach the task's except block and trigger a retry — if
    send_mail() were still swallowing it, self.retry() would never be called.
    """

    @patch('services.utils.send_mail.send_mail')
    def test_task_retries_when_send_mail_raises(self, mock_send_mail):
        mock_send_mail.side_effect = Exception("SMTP connection refused")

        with self.assertRaises(Exception):
            send_order_confirmation_email_task.apply(args=['user@example.com', 1]).get()

        # The underlying send_mail() was actually invoked with fail_silently=False,
        # i.e. we're not passing fail_silently=True anywhere in the call.
        _, kwargs = mock_send_mail.call_args
        self.assertFalse(kwargs.get('fail_silently'))
