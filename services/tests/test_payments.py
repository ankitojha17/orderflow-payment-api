import hashlib
import hmac
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from services.utils.authentication import generate_jwt
from services.models import Order, Payment, Product


WEBHOOK_SECRET = 'test-webhook-secret'


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


@override_settings(
    RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class RazorpayWebhookTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ankit', password='strongpass123', email='ankit@example.com')
        self.product = Product.objects.create(name="Mouse", price=500, stock_quantity=5)
        self.order = Order.objects.create(user=self.user, total_amount=500)
        self.payment = Payment.objects.create(order=self.order, razorpay_order_id='order_ABC123')

    def _payload(self, event='payment.captured', order_id='order_ABC123', payment_id='pay_XYZ789', amount=50000, currency='INR'):
        return json.dumps({
            'event': event,
            'payload': {
                'payment': {
                    'entity': {'id': payment_id, 'order_id': order_id, 'amount': amount, 'currency': currency}
                }
            }
        }).encode()

    def test_webhook_rejects_invalid_signature(self):
        body = self._payload()
        response = self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='not-the-real-signature',
        )
        self.assertEqual(response.status_code, 400)

        self.payment.refresh_from_db()
        self.assertFalse(self.payment.is_webhook_processed)

    def test_webhook_processes_valid_signature_and_marks_order_paid(self):
        body = self._payload()
        response = self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=_sign(body),
        )
        self.assertEqual(response.status_code, 200)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertTrue(self.payment.is_webhook_processed)
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_webhook_is_idempotent_on_duplicate_delivery(self):
        body = self._payload()
        signature = _sign(body)

        first = self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        second = self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIn('already', second.json()['message'].lower())

    def test_webhook_returns_404_for_unknown_razorpay_order_id(self):
        body = self._payload(order_id='order_UNKNOWN', payment_id='pay_1')
        response = self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=_sign(body),
        )
        self.assertEqual(response.status_code, 404)

    def test_webhook_marks_payment_and_order_failed_on_payment_failed_event(self):
        body = self._payload(event='payment.failed')
        response = self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=_sign(body),
        )
        self.assertEqual(response.status_code, 200)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertTrue(self.payment.is_webhook_processed)
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertEqual(self.order.status, Order.Status.FAILED)

    def test_webhook_ignores_unhandled_event_types(self):
        body = self._payload(event='payment.authorized')
        response = self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=_sign(body),
        )
        self.assertEqual(response.status_code, 200)

        self.payment.refresh_from_db()
        self.assertFalse(self.payment.is_webhook_processed)

    def test_webhook_downgrades_to_failed_on_amount_mismatch(self):
        body = self._payload(amount=1, currency='INR')
        response = self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=_sign(body),
        )
        self.assertEqual(response.status_code, 200)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertEqual(self.order.status, Order.Status.FAILED)

    def test_webhook_rejects_malformed_json_body(self):
        body = b'{not valid json'
        response = self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=_sign(body),
        )
        self.assertEqual(response.status_code, 400)

    def test_webhook_rejects_payload_missing_payment_ids(self):
        body = json.dumps({'event': 'payment.captured', 'payload': {}}).encode()
        response = self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=_sign(body),
        )
        self.assertEqual(response.status_code, 400)


class CreatePaymentViewTests(APITestCase):
    """
    Guard clauses on POST /orders/{id}/pay/. The Razorpay client itself is
    mocked out — these tests only exercise the validation that runs before
    we'd ever make a network call to Razorpay.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='priya', password='strongpass123', email='priya@example.com')
        self.product = Product.objects.create(name="Keyboard", price=1500, stock_quantity=5)
        self.token = generate_jwt(self.user)

    def _auth(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}

    def test_rejects_payment_for_already_paid_order(self):
        order = Order.objects.create(user=self.user, total_amount=1500, status=Order.Status.PAID)
        response = self.client.post(reverse('CreatePayment', args=[order.id]), **self._auth())
        self.assertEqual(response.status_code, 409)

    def test_rejects_payment_for_zero_amount_order(self):
        order = Order.objects.create(user=self.user, total_amount=0)
        response = self.client.post(reverse('CreatePayment', args=[order.id]), **self._auth())
        self.assertEqual(response.status_code, 400)

    def test_rejects_payment_when_a_successful_payment_already_exists(self):
        order = Order.objects.create(user=self.user, total_amount=1500)
        Payment.objects.create(order=order, razorpay_order_id='order_OLD', status=Payment.Status.SUCCESS)
        response = self.client.post(reverse('CreatePayment', args=[order.id]), **self._auth())
        self.assertEqual(response.status_code, 409)

    @patch('services.views.payments.create_payment_view.get_razorpay_client')
    def test_allows_payment_for_valid_pending_order(self, mock_get_client):
        mock_get_client.return_value.order.create.return_value = {
            'id': 'order_NEW123', 'amount': 150000, 'currency': 'INR',
        }
        order = Order.objects.create(user=self.user, total_amount=1500)
        response = self.client.post(reverse('CreatePayment', args=[order.id]), **self._auth())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['data']['razorpay_order_id'], 'order_NEW123')


@override_settings(
    RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class PaymentRetryFlowTests(APITestCase):
    """
    End-to-end: a failed payment attempt followed by a successful retry.
    Regression test for the bug where retrying payment after a failure left
    stale Payment state (status=FAILED, is_webhook_processed=True) behind,
    causing the webhook for the *successful* retry to be silently ignored
    by the idempotency guard.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='retry_user', password='strongpass123', email='r@example.com')
        self.product = Product.objects.create(name="Webcam", price=2000, stock_quantity=5)
        self.token = generate_jwt(self.user)
        self.order = Order.objects.create(user=self.user, total_amount=2000)

    def _auth(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}

    def _webhook(self, event, order_id, payment_id, amount=200000, currency='INR'):
        body = json.dumps({
            'event': event,
            'payload': {'payment': {'entity': {'id': payment_id, 'order_id': order_id, 'amount': amount, 'currency': currency}}},
        }).encode()
        return self.client.post(
            reverse('RazorpayWebhook'), data=body, content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=_sign(body),
        )

    @patch('services.views.payments.create_payment_view.get_razorpay_client')
    def test_failed_attempt_then_successful_retry_marks_order_paid(self, mock_get_client):
        # First attempt: create a Razorpay order, then Razorpay reports it failed.
        mock_get_client.return_value.order.create.return_value = {
            'id': 'order_ATTEMPT1', 'amount': 200000, 'currency': 'INR',
        }
        response = self.client.post(reverse('CreatePayment', args=[self.order.id]), **self._auth())
        self.assertEqual(response.status_code, 201)

        failed_webhook = self._webhook('payment.failed', 'order_ATTEMPT1', 'pay_ATTEMPT1')
        self.assertEqual(failed_webhook.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.FAILED)

        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertTrue(payment.is_webhook_processed)

        # Retry: user clicks "Pay Again" — a brand new Razorpay order.
        mock_get_client.return_value.order.create.return_value = {
            'id': 'order_ATTEMPT2', 'amount': 200000, 'currency': 'INR',
        }
        retry_response = self.client.post(reverse('CreatePayment', args=[self.order.id]), **self._auth())
        self.assertEqual(retry_response.status_code, 201)

        # The bug: without resetting is_webhook_processed/status on retry,
        # this second webhook would be ignored by the idempotency guard and
        # the order would incorrectly stay FAILED forever.
        captured_webhook = self._webhook('payment.captured', 'order_ATTEMPT2', 'pay_ATTEMPT2')
        self.assertEqual(captured_webhook.status_code, 200)

        self.order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(payment.razorpay_order_id, 'order_ATTEMPT2')
