from django.urls import path
from services.views import *

urlpatterns = [
    # Auth
    path('auth/register/', RegisterView.as_view(), name='Register'),
    path('auth/login/', LoginView.as_view(), name='Login'),

    # Products
    path('products/', ProductListView.as_view(), name='ProductList'),

    # Orders
    path('orders/', CreateOrderView.as_view(), name='CreateOrder'),
    path('orders/list/', OrderListView.as_view(), name='OrderList'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='OrderDetail'),

    # Payments
    path('orders/<int:order_id>/pay/', CreatePaymentView.as_view(), name='CreatePayment'),
    path('webhook/razorpay/', RazorpayWebhookView.as_view(), name='RazorpayWebhook'),
]
