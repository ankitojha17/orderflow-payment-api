from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from services.models import Product


class AuthTests(APITestCase):
    def test_register_creates_user(self):
        response = self.client.post(reverse('Register'), {
            'username': 'ankit', 'email': 'ankit@example.com', 'password': 'strongpass123',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username='ankit').exists())

    def test_register_rejects_duplicate_username(self):
        User.objects.create_user(username='ankit', password='strongpass123')
        response = self.client.post(reverse('Register'), {
            'username': 'ankit', 'password': 'anotherpass123',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_returns_token_for_valid_credentials(self):
        User.objects.create_user(username='ankit', password='strongpass123')
        response = self.client.post(reverse('Login'), {
            'username': 'ankit', 'password': 'strongpass123',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data['data'])

    def test_login_rejects_wrong_password(self):
        User.objects.create_user(username='ankit', password='strongpass123')
        response = self.client.post(reverse('Login'), {
            'username': 'ankit', 'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProductListTests(APITestCase):
    def test_list_returns_only_active_products(self):
        Product.objects.create(name="Active", price=100, stock_quantity=5, is_active=True)
        Product.objects.create(name="Inactive", price=100, stock_quantity=5, is_active=False)
        response = self.client.get(reverse('ProductList'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)

    def test_search_filters_by_name(self):
        Product.objects.create(name="Wireless Mouse", price=500, stock_quantity=5)
        Product.objects.create(name="Keyboard", price=800, stock_quantity=5)
        response = self.client.get(reverse('ProductList'), {'search': 'mouse'})
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['name'], "Wireless Mouse")

    def test_response_includes_pagination_meta(self):
        Product.objects.create(name="Item", price=100, stock_quantity=5)
        response = self.client.get(reverse('ProductList'))
        self.assertIn('meta', response.data)
        self.assertIn('total_pages', response.data['meta'])
