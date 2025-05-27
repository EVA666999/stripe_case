from django.shortcuts import render, get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import stripe
from django.conf import settings
from .models import Item, Order, Discount, Tax, OrderItem
from .serializers import OrderCreateSerializer, DiscountSerializer, TaxSerializer
import logging
from typing import cast, Dict, Any, List, Optional
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view
from django.http import JsonResponse

logger = logging.getLogger(__name__)

def item_detail(request, id):
    item = get_object_or_404(Item, id=id)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('accept') == 'application/json':
        # Быстрая покупка через AJAX: создаём заказ и возвращаем ссылку на оплату
        order = Order.objects.create()
        OrderItem.objects.create(order=order, item=item, quantity=1, price=item.price)
        order.total_amount = item.price
        order.final_amount = item.price
        order.save()
        session = StripeService.create_checkout_session(
            order=order,
            success_url=request.build_absolute_uri(f'/orders/{order.pk}/success/'),
            cancel_url=request.build_absolute_uri(f'/orders/{order.pk}/cancel/')
        )
        order.stripe_session_id = session.id
        order.save()
        return JsonResponse({'url': session.url})
    return render(request, 'payments/item_detail.html', {
        'item': item,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY
    })

class StripeService:
    """Сервис для работы со Stripe API"""
    
    @staticmethod
    def get_stripe_client(currency: str) -> stripe:
        """Получает клиент Stripe для указанной валюты"""
        stripe.api_key = settings.STRIPE_KEYS[currency]['secret']
        return stripe

    @staticmethod
    def create_line_items(order: Order) -> List[Dict[str, Any]]:
        """Создает список товаров для Stripe Checkout"""
        # Группируем товары по валюте
        items_by_currency: Dict[str, List[Dict[str, Any]]] = {}
        
        for order_item in order.order_items.all():
            currency = order_item.item.currency
            if currency not in items_by_currency:
                items_by_currency[currency] = []
                
            items_by_currency[currency].append({
                'price_data': {
                    'currency': currency,
                    'product_data': {
                        'name': order_item.item.name,
                        'description': order_item.item.description,
                    },
                    'unit_amount': int(order_item.price * 100),
                },
                'quantity': order_item.quantity,
            })
            
        return items_by_currency

    @staticmethod
    def create_discount_coupon(discount: Discount, currency: str) -> str:
        """Создает купон скидки в Stripe"""
        stripe_client = StripeService.get_stripe_client(currency)
        
        coupon_params: Dict[str, Any] = {
            'duration': 'once',
            'name': str(discount.name),
        }
        
        if discount.type == 'percentage':
            coupon_params['percent_off'] = float(discount.value)
        else:  # fixed
            coupon_params['amount_off'] = int(discount.value * 100)
            coupon_params['currency'] = currency
        
        coupon = stripe_client.Coupon.create(**coupon_params)
        return coupon.id

    @staticmethod
    def create_tax_rate(tax: Tax, currency: str) -> str:
        """Создает налоговую ставку в Stripe"""
        stripe_client = StripeService.get_stripe_client(currency)
        
        tax_rate = stripe_client.TaxRate.create(
            display_name=tax.name,
            percentage=float(tax.rate),
            inclusive=False,
            country='RU',
            description=f'Tax rate for {tax.name}'
        )
        return tax_rate.id

    @staticmethod
    def create_checkout_session(
        order: Order,
        success_url: str,
        cancel_url: str
    ) -> stripe.checkout.Session:
        """Создает сессию Stripe Checkout"""
        # Получаем все валюты из заказа
        currencies = {item.item.currency for item in order.order_items.all()}
        if len(currencies) > 1:
            raise ValueError("All items in order must have the same currency")
            
        currency = currencies.pop()
        stripe_client = StripeService.get_stripe_client(currency)
        
        # Создаем line_items для всех товаров
        line_items = []
        for order_item in order.order_items.all():
            line_items.append({
                'price_data': {
                    'currency': currency,
                    'product_data': {
                        'name': order_item.item.name,
                        'description': order_item.item.description,
                    },
                    'unit_amount': int(order_item.price * 100),
                },
                'quantity': order_item.quantity,
            })

        session_params: Dict[str, Any] = {
            'payment_method_types': ['card'],
            'line_items': line_items,
            'mode': 'payment',
            'success_url': success_url,
            'cancel_url': cancel_url,
        }

        # Добавляем скидку, если она есть
        if order.discount and order.discount.is_active:
            coupon_id = StripeService.create_discount_coupon(order.discount, currency)
            session_params['discounts'] = [{'coupon': coupon_id}]

        # Добавляем налог, если он есть
        if order.tax and order.tax.is_active:
            tax_rate_id = StripeService.create_tax_rate(order.tax, currency)
            for item in line_items:
                item['tax_rates'] = [tax_rate_id]

        return stripe_client.checkout.Session.create(**session_params)

class OrderCreateView(APIView):
    """Представление для создания заказа"""
    
    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        if serializer.is_valid():
            order = cast(Order, serializer.save())
            
            try:
                # Создаем сессию Stripe
                session = StripeService.create_checkout_session(
                    order=order,
                    success_url=request.build_absolute_uri(f'/orders/{order.pk}/success/'),
                    cancel_url=request.build_absolute_uri(f'/orders/{order.pk}/cancel/')
                )
                
                order.stripe_session_id = session.id
                order.save()
                
                return Response({
                    'order_id': order.pk,
                    'session_id': session.id,
                    'checkout_url': session.url
                })
                
            except ValueError as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Exception as e:
                logger.error(f"Stripe error: {str(e)}")
                return Response(
                    {'error': 'Ошибка при создании платежной сессии'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class OrderDetailView(APIView):
    """Представление для получения деталей заказа"""
    
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        serializer = OrderCreateSerializer(order)
        return Response(serializer.data)

class OrderSuccessView(APIView):
    """Представление для обработки успешной оплаты"""
    
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        if order.stripe_session_id:
            try:
                # Получаем валюту из первого товара
                currency = order.order_items.first().item.currency
                stripe_client = StripeService.get_stripe_client(currency)
                
                session = stripe_client.checkout.Session.retrieve(order.stripe_session_id)
                if session.payment_status == 'paid':
                    order.status = 'paid'
                    order.save()
                    return Response({'status': 'success', 'message': 'Заказ успешно оплачен'})
            except Exception as e:
                logger.error(f"Stripe error: {str(e)}")
                
        return Response({'status': 'error', 'message': 'Ошибка при проверке статуса оплаты'})

class OrderCancelView(APIView):
    """Представление для обработки отмены заказа"""
    
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        order.status = 'cancelled'
        order.save()
        return Response({'status': 'cancelled', 'message': 'Заказ отменен'})

class PaymentIntentCreateView(APIView):
    """Создание Stripe PaymentIntent для оплаты заказа"""
    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        if serializer.is_valid():
            order = cast(Order, serializer.save())
            try:
                # Получаем валюту заказа
                currencies = {item.item.currency for item in order.order_items.all()}
                if len(currencies) > 1:
                    return Response({'error': 'Все товары в заказе должны быть в одной валюте.'}, status=400)
                currency = currencies.pop()
                stripe.api_key = settings.STRIPE_KEYS[currency]['secret']
                # Сумма в копейках/центах
                amount = int(order.final_amount * 100)
                intent = stripe.PaymentIntent.create(
                    amount=amount,
                    currency=currency,
                    metadata={
                        'order_id': order.pk
                    }
                )
                order.stripe_session_id = intent.id
                order.save()
                return Response({
                    'order_id': order.pk,
                    'payment_intent_id': intent.id,
                    'client_secret': intent.client_secret
                })
            except Exception as e:
                logger.error(f"Stripe error: {str(e)}")
                return Response({'error': 'Ошибка при создании PaymentIntent'}, status=500)
        return Response(serializer.errors, status=400)
