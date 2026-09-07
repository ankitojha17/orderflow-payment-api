from django.test import TestCase
from services.models import Product


class ProductModelTests(TestCase):
    def test_product_str_returns_name(self):
        product = Product.objects.create(name="Wireless Mouse", price=699, stock_quantity=10)
        self.assertEqual(str(product), "Wireless Mouse")

    def test_default_flags(self):
        product = Product.objects.create(name="Keyboard", price=1299, stock_quantity=5)
        self.assertTrue(product.is_active)
        self.assertFalse(product.is_deleted)
