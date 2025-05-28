from django.shortcuts import render, get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import stripe
from .models import Item, Order, Discount, Tax, OrderItem
from .serializers import OrderCreateSerializer, DiscountSerializer, TaxSerializer
import logging
from typing import cast, Dict, Any, List, Optional, Tuple
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view
from django.http import JsonResponse
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

logger = logging.getLogger(__name__)

# Получаем ключи из переменных окружения
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')

# Проверяем наличие ключей
if not STRIPE_SECRET_KEY or not STRIPE_PUBLIC_KEY:
    raise ValueError("Stripe keys not found in environment variables")

# Создаем словарь с ключами для всех поддерживаемых валют
SUPPORTED_CURRENCIES = ['usd', 'rub', 'eur']
STRIPE_KEYS = {currency: {'secret': STRIPE_SECRET_KEY} for currency in SUPPORTED_CURRENCIES}

def get_currency_symbol(currency: str) -> str:
    """Возвращает символ валюты"""
    return {
        'rub': '₽',
        'usd': '$',
        'eur': '€'
    }.get(currency.lower(), '')

def handle_stripe_error(error: Exception, message: str) -> None:
    """Обработка ошибок Stripe"""
    logger.error(f"{message}: {str(error)}")
    raise ValueError(f"{message}: {str(error)}")

def item_detail(request, id):
    """Представление для детальной страницы товара"""
    item = get_object_or_404(Item, id=id)
    logger.info(f"Просмотр товара: {item.name}")
    
    # Проверяем, является ли запрос AJAX или JSON
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    is_json = request.headers.get('accept') == 'application/json'
    
    if is_ajax or is_json:
        try:
            order = create_order(item)
            session = StripeService.create_checkout_session(
                order=order,
                success_url=request.build_absolute_uri(f'/orders/{order.pk}/success/'),
                cancel_url=request.build_absolute_uri(f'/orders/{order.pk}/cancel/')
            )
            order.stripe_session_id = session.id
            order.save()
            logger.info(f"Создан заказ: {order.pk}")
            return JsonResponse({'url': session.url})
        except Exception as e:
            logger.error(f"Ошибка при создании заказа: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)
        
    return render(request, 'payments/item_detail.html', {
        'item': item,
        'stripe_public_key': STRIPE_PUBLIC_KEY
    })

def create_order(item: Item) -> Order:
    """Создает новый заказ с одним товаром"""
    order = Order.objects.create()
    OrderItem.objects.create(order=order, item=item, quantity=1, price=item.price)
    order.total_amount = item.price
    order.final_amount = item.price
    order.save()
    return order

class StripeService:
    """Сервис для работы со Stripe API"""
    
    @staticmethod
    def get_stripe_client(currency: str) -> Any:
        """Получает клиент Stripe для указанной валюты"""
        currency = currency.lower()
        if currency not in STRIPE_KEYS:
            raise ValueError(f"Неподдерживаемая валюта: {currency}")
            
        stripe.api_key = STRIPE_KEYS[currency]['secret']
        if not stripe.api_key:
            raise ValueError("Не удалось установить ключ API Stripe")
            
        return stripe

    @staticmethod
    def create_line_items(order: Order) -> List[Dict[str, Any]]:
        """Создает список товаров для Stripe Checkout"""
        return [{
            'price_data': {
                'currency': item.item.currency.lower(),
                'product_data': {
                    'name': item.item.name,
                    'description': item.item.description,
                },
                'unit_amount': int(item.price * 100),
            },
            'quantity': item.quantity,
        } for item in order.order_items.all()]

    @staticmethod
    def create_discount_coupon(discount: Discount, currency: str) -> str:
        """Создает купон скидки в Stripe"""
        stripe_client = StripeService.get_stripe_client(currency)
        
        coupon_params = {
            'duration': 'once',
            'name': str(discount.name),
        }
        
        if discount.type == 'percentage':
            coupon_params['percent_off'] = float(discount.value)
        else:
            coupon_params['amount_off'] = int(discount.value * 100)
            coupon_params['currency'] = currency
        
        return stripe_client.Coupon.create(**coupon_params).id

    @staticmethod
    def create_tax_rate(tax: Tax, currency: str) -> str:
        """Создает налоговую ставку в Stripe"""
        stripe_client = StripeService.get_stripe_client(currency)
        
        return stripe_client.TaxRate.create(
            display_name=tax.name,
            percentage=float(tax.rate),
            inclusive=False,
            country='RU',
            description=f'Tax rate for {tax.name}'
        ).id

    @staticmethod
    def create_checkout_session(
        order: Order,
        success_url: str,
        cancel_url: str
    ) -> stripe.checkout.Session:
        """Создает сессию Stripe Checkout"""
        try:
            # Получаем валюту из заказа
            currency = order.order_items.first().item.currency.lower()
            stripe_client = StripeService.get_stripe_client(currency)
            
            # Создаем параметры сессии
            session_params = {
                'payment_method_types': ['card'],
                'line_items': StripeService.create_line_items(order),
                'mode': 'payment',
                'success_url': success_url,
                'cancel_url': cancel_url,
                'currency': currency,
            }

            # Добавляем скидку и налог если есть
            StripeService._add_discount_and_tax(order, session_params)
            
            return stripe_client.checkout.Session.create(**session_params)
        except Exception as e:
            handle_stripe_error(e, "Не удалось создать платежную сессию")

    @staticmethod
    def _add_discount_and_tax(order: Order, session_params: Dict[str, Any]) -> None:
        """Добавляет скидку и налог к параметрам сессии"""
        currency = order.order_items.first().item.currency.lower()
        
        if order.discount and order.discount.is_active:
            try:
                coupon_id = StripeService.create_discount_coupon(order.discount, currency)
                session_params['discounts'] = [{'coupon': coupon_id}]
            except Exception as e:
                logger.error(f"Ошибка при создании купона скидки: {str(e)}")

        if order.tax and order.tax.is_active:
            try:
                tax_rate_id = StripeService.create_tax_rate(order.tax, currency)
                for item in session_params['line_items']:
                    item['tax_rates'] = [tax_rate_id]
            except Exception as e:
                logger.error(f"Ошибка при создании налоговой ставки: {str(e)}")

class OrderCreateView(APIView):
    """Представление для создания заказа"""
    
    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        order = serializer.save()
        session = StripeService.create_checkout_session(
            order=order,
            success_url=request.build_absolute_uri(f'/orders/{order.pk}/success/'),
            cancel_url=request.build_absolute_uri(f'/orders/{order.pk}/cancel/')
        )
        
        order.stripe_session_id = session.id
        order.save()
        logger.info(f"Создан заказ через API: {order.pk}")
        
        return Response({
            'order_id': order.pk,
            'session_id': session.id,
            'checkout_url': session.url
        })

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
        if not order.stripe_session_id:
            return Response({'status': 'error', 'message': 'Сессия не найдена'})
            
        currency = order.order_items.first().item.currency
        stripe_client = StripeService.get_stripe_client(currency)
        session = stripe_client.checkout.Session.retrieve(order.stripe_session_id)
        
        if session.payment_status == 'paid':
            order.status = 'paid'
            order.save()
            logger.info(f"Заказ оплачен: {order.pk}")
            return Response({'status': 'success', 'message': 'Заказ успешно оплачен'})
            
        return Response({'status': 'error', 'message': 'Ошибка при проверке статуса оплаты'})

class OrderCancelView(APIView):
    """Представление для обработки отмены заказа"""
    
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        order.status = 'cancelled'
        order.save()
        logger.info(f"Заказ отменен: {order.pk}")
        return Response({'status': 'cancelled', 'message': 'Заказ отменен'})

class PaymentIntentCreateView(APIView):
    """Создание Stripe PaymentIntent для оплаты заказа"""
    
    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
            
        try:
            order = cast(Order, serializer.save())
            currency = order.order_items.first().item.currency
            
            stripe.api_key = STRIPE_SECRET_KEY
            intent = stripe.PaymentIntent.create(
                amount=int(order.final_amount * 100),
                currency=currency,
                metadata={'order_id': order.pk}
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
