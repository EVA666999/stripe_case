from django.urls import path
from . import views

urlpatterns = [
    path('item/<int:id>/', views.item_detail, name='item_detail'),
    path('orders/create/', views.OrderCreateView.as_view(), name='order_create'),
    path('orders/<int:order_id>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:order_id>/success/', views.OrderSuccessView.as_view(), name='order_success'),
    path('orders/<int:order_id>/cancel/', views.OrderCancelView.as_view(), name='order_cancel'),
    path('payment-intent/', views.PaymentIntentCreateView.as_view(), name='payment_intent_create'),
] 