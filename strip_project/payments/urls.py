from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('items/<int:id>/', views.item_detail, name='item_detail'),
    path('api/orders/', views.OrderCreateView.as_view(), name='order_create'),
    path('api/orders/<int:order_id>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:order_id>/success/', views.OrderSuccessView.as_view(), name='order_success'),
    path('orders/<int:order_id>/cancel/', views.OrderCancelView.as_view(), name='order_cancel'),
    path('api/payment-intent/', views.PaymentIntentCreateView.as_view(), name='payment_intent_create'),
] 