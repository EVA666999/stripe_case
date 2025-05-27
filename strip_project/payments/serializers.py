from rest_framework import serializers
from decimal import Decimal
from typing import Dict, Any, List, Optional
from .models import Item, Order, OrderItem, Discount, Tax

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ['id', 'name', 'description', 'price', 'currency']

def calculate_discount_amount(discount: Optional[Discount], total_amount: Decimal) -> Decimal:
    """
    Рассчитывает сумму скидки для указанной суммы.
    
    Args:
        discount: Объект скидки или None
        total_amount: Общая сумма заказа
        
    Returns:
        Decimal: Сумма скидки
    """
    if not discount or not discount.is_active:
        return Decimal('0')
        
    if discount.type == 'percentage':
        return (total_amount * discount.value) / Decimal('100')
    return discount.value

def calculate_tax_amount(tax: Optional[Tax], total_amount: Decimal) -> Decimal:
    """
    Рассчитывает сумму налога для указанной суммы.
    
    Args:
        tax: Объект налога или None
        total_amount: Общая сумма заказа
        
    Returns:
        Decimal: Сумма налога
    """
    if not tax or not tax.is_active:
        return Decimal('0')
        
    return (total_amount * tax.rate) / Decimal('100')

class DiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = ['id', 'name', 'type', 'value', 'is_active']

class TaxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tax
        fields = ['id', 'name', 'rate', 'is_active']

class OrderItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['item', 'quantity', 'price']

class OrderItemCreateSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)

class OrderCreateSerializer(serializers.ModelSerializer):
    items = serializers.ListField(
        child=serializers.DictField(
            child=serializers.IntegerField()
        ),
        write_only=True
    )
    discount_id = serializers.IntegerField(required=False, allow_null=True)
    tax_id = serializers.IntegerField(required=False, allow_null=True)
    
    order_items = OrderItemSerializer(many=True, read_only=True)
    discount = DiscountSerializer(read_only=True)
    tax = TaxSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'items', 'order_items', 'status', 'created_at',
            'stripe_session_id', 'discount_id', 'tax_id',
            'discount', 'tax'
        ]
        read_only_fields = ['status', 'created_at', 'stripe_session_id']

    def calculate_amounts(self, order: Order) -> None:
        """
        Рассчитывает все суммы для заказа.
        
        Args:
            order: Заказ для расчета сумм
        """
        # Базовая сумма заказа
        total = Decimal('0')
        for item in order.order_items.all():
            total += item.price * item.quantity
        order.total_amount = total
        
        # Применяем скидку
        order.discount_amount = calculate_discount_amount(order.discount, order.total_amount)
        
        # Применяем налог
        taxable_amount = order.total_amount - order.discount_amount
        order.tax_amount = calculate_tax_amount(order.tax, taxable_amount)
        
        # Рассчитываем итоговую сумму
        order.final_amount = order.total_amount - order.discount_amount + order.tax_amount

    def validate(self, attrs):
        items_data = self.initial_data.get('items', []) # type: ignore
        currencies = set()
        for item_data in items_data:
            item = Item.objects.get(id=item_data['item_id'])
            currencies.add(item.currency)
        if len(currencies) > 1:
            raise serializers.ValidationError("Все товары в заказе должны быть в одной валюте.")
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> Order:
        """
        Создает новый заказ с расчетом всех сумм.
        
        Args:
            validated_data: Валидированные данные для создания заказа
            
        Returns:
            Order: Созданный заказ
        """
        items_data = validated_data.pop('items')
        discount_id = validated_data.pop('discount_id', None)
        tax_id = validated_data.pop('tax_id', None)

        order = Order.objects.create(
            total_amount=Decimal('0'),
            discount_id=discount_id,
            tax_id=tax_id
        )
        
        total_amount = Decimal('0')
        for item_data in items_data:
            item = Item.objects.get(id=item_data['item_id'])
            quantity = item_data.get('quantity', 1)
            price = item.price  # Только за одну штуку!
            total_amount += price * quantity
            
            OrderItem.objects.create(
                order=order,
                item=item,
                quantity=quantity,
                price=price  # Только за одну штуку!
            )
        
        order.total_amount = total_amount
        self.calculate_amounts(order)
        order.save()
        return order 