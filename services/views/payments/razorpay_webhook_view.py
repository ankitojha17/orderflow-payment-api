import hmac
import hashlib
import json

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from services.models import Payment, Order
from services.constants import messages
from services.utils.logger import logger
from services.tasks import send_order_confirmation_email_task


@method_decorator(csrf_exempt, name='dispatch')
class RazorpayWebhookView(View):
    """
    Called by Razorpay's servers, not a browser session — csrf_exempt is
    required here, since Django's CsrfViewMiddleware has no session/cookie
    to validate against for a server-to-server call. Authenticity instead
    comes from verifying the HMAC signature below.

    No JWT here either, for the same reason: Razorpay isn't a logged-in user.
    """

    EVENT_CAPTURED = 'payment.captured'
    EVENT_FAILED = 'payment.failed'

    def post(self, request, *args, **kwargs):
        signature = request.headers.get('X-Razorpay-Signature', '')

        # Negative case first: reject anything that isn't genuinely from Razorpay.
        if not self._verify_signature(request.body, signature):
            logger.warning("Razorpay webhook rejected: invalid signature")
            return JsonResponse({'success': False, 'message': messages.INVALID_SIGNATURE}, status=400)

        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning("Razorpay webhook rejected: malformed JSON body")
            return JsonResponse({'success': False, 'message': messages.INVALID_WEBHOOK_PAYLOAD}, status=400)

        event = payload.get('event', '')
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        razorpay_order_id = payment_entity.get('order_id')
        razorpay_payment_id = payment_entity.get('id')

        # Negative case: well-formed JSON, but not shaped like a real
        # Razorpay payment event (missing the fields we depend on below).
        if not razorpay_order_id or not razorpay_payment_id:
            logger.warning("Razorpay webhook rejected: missing order_id/payment_id in payload")
            return JsonResponse({'success': False, 'message': messages.INVALID_WEBHOOK_PAYLOAD}, status=400)

        # We only act on the two events that actually determine payment
        # outcome. Anything else (e.g. payment.authorized, refund events)
        # is acknowledged but ignored for now rather than guessed at.
        if event not in (self.EVENT_CAPTURED, self.EVENT_FAILED):
            logger.info(f"Razorpay webhook ignored: unhandled event '{event}'")
            return JsonResponse({'success': True, 'message': messages.WEBHOOK_EVENT_IGNORED}, status=200)

        new_status = Payment.Status.SUCCESS if event == self.EVENT_CAPTURED else Payment.Status.FAILED

        with transaction.atomic():
            # select_for_update locks the Payment row for the duration of this
            # transaction, so two near-simultaneous deliveries of the same
            # webhook (Razorpay retries on timeout) can't both pass the
            # is_webhook_processed check before either has committed.
            payment = (
                Payment.objects.select_for_update()
                .select_related('order__user')
                .filter(razorpay_order_id=razorpay_order_id)
                .first()
            )

            # Negative case: webhook for an order_id we don't recognize.
            if not payment:
                return JsonResponse({'success': False, 'message': messages.ORDER_NOT_FOUND}, status=404)

            # Idempotency guard: Razorpay may deliver the same event more than once.
            if payment.is_webhook_processed:
                return JsonResponse({'success': True, 'message': messages.PAYMENT_ALREADY_PROCESSED}, status=200)

            # Amount/currency sanity check: don't take Razorpay's word for a
            # successful capture without confirming it matches what we asked
            # for. A captured payment for the wrong amount is downgraded to
            # FAILED rather than silently marking the order paid.
            if new_status == Payment.Status.SUCCESS and not self._amount_matches(payment_entity, payment.order):
                logger.error(
                    "Razorpay webhook amount mismatch for Order #%s: payment_entity=%s",
                    payment.order_id, payment_entity,
                )
                new_status = Payment.Status.FAILED

            payment.razorpay_payment_id = razorpay_payment_id
            payment.status = new_status
            payment.is_webhook_processed = True
            payment.save()

            payment.order.status = Order.Status.PAID if new_status == Payment.Status.SUCCESS else Order.Status.FAILED
            payment.order.save(update_fields=['status'])

            # Only queue the confirmation email for a genuinely successful
            # capture — a failed payment shouldn't tell the customer it worked.
            if new_status == Payment.Status.SUCCESS:
                # Queued on Celery via Redis — the webhook response returns
                # immediately instead of waiting on email I/O. The task fires
                # after the transaction block exits (i.e. after commit),
                # since on_commit is used below.
                transaction.on_commit(
                    lambda: send_order_confirmation_email_task.delay(payment.order.user.email, payment.order.id)
                )

        return JsonResponse({'success': True, 'message': messages.WEBHOOK_PROCESSED}, status=200)

    @staticmethod
    def _verify_signature(payload_body: bytes, received_signature: str) -> bool:
        expected = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, received_signature)

    @staticmethod
    def _amount_matches(payment_entity: dict, order) -> bool:
        """
        Confirms the captured Razorpay payment's amount/currency actually
        match what we charged for, rather than trusting event type alone.
        Razorpay amounts are in paise; order.total_amount is in rupees.
        """
        expected_paise = int(order.total_amount * 100)
        return (
            payment_entity.get('amount') == expected_paise
            and payment_entity.get('currency') == 'INR'
        )
