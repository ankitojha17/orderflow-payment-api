import json
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from services.models import Product
from services.utils.authentication import generate_jwt


class CreateOrderTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ankit', password='strongpass123')
        self.token = generate_jwt(self.user)
        self.product = Product.objects.create(name="Mouse", price=500, stock_quantity=3)

    def _auth_headers(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}

    def test_create_order_succeeds_and_reduces_stock(self):
        response = self.client.post(
            reverse('CreateOrder'),
            data=json.dumps({'items': [{'product_id': self.product.id, 'quantity': 2}]}),
            content_type='application/json',
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 1)

    def test_create_order_rejects_insufficient_stock(self):
        response = self.client.post(
            reverse('CreateOrder'),
            data=json.dumps({'items': [{'product_id': self.product.id, 'quantity': 10}]}),
            content_type='application/json',
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_order_rejects_duplicate_product_in_same_request(self):
        response = self.client.post(
            reverse('CreateOrder'),
            data=json.dumps({'items': [
                {'product_id': self.product.id, 'quantity': 1},
                {'product_id': self.product.id, 'quantity': 1},
            ]}),
            content_type='application/json',
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_order_requires_authentication(self):
        response = self.client.post(
            reverse('CreateOrder'),
            data=json.dumps({'items': [{'product_id': self.product.id, 'quantity': 1}]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_create_order_rejects_malformed_auth_header(self):
        response = self.client.post(
            reverse('CreateOrder'),
            data=json.dumps({'items': [{'product_id': self.product.id, 'quantity': 1}]}),
            content_type='application/json',
            HTTP_AUTHORIZATION=self.token,  # missing "Bearer " prefix
        )
        self.assertEqual(response.status_code, 401)


class OrderListFilterTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ankit', password='strongpass123')
        self.token = generate_jwt(self.user)
        self.product = Product.objects.create(name="Mouse", price=500, stock_quantity=10)

    def _auth_headers(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}

    def test_order_list_scoped_to_logged_in_user(self):
        other_user = User.objects.create_user(username='other', password='strongpass123')
        self.client.post(
            reverse('CreateOrder'),
            data=json.dumps({'items': [{'product_id': self.product.id, 'quantity': 1}]}),
            content_type='application/json',
            **self._auth_headers(),
        )

        other_token = generate_jwt(other_user)
        response = self.client.get(reverse('OrderList'), HTTP_AUTHORIZATION=f'Bearer {other_token}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 0)

    def test_staff_user_sees_orders_from_all_users(self):
        other_user = User.objects.create_user(username='other', password='strongpass123')
        self.client.post(
            reverse('CreateOrder'),
            data=json.dumps({'items': [{'product_id': self.product.id, 'quantity': 1}]}),
            content_type='application/json',
            **self._auth_headers(),
        )

        staff_user = User.objects.create_user(username='staff', password='strongpass123', is_staff=True)
        staff_token = generate_jwt(staff_user)
        response = self.client.get(reverse('OrderList'), HTTP_AUTHORIZATION=f'Bearer {staff_token}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Staff sees the order created by self.user above, even though it's
        # not their own — that's the whole point of the is_staff scoping.
        self.assertEqual(len(response.data['data']), 1)
