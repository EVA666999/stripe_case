from django.db import models
from django.db.models.manager import Manager
from typing import TYPE_CHECKING
from decimal import Decimal

if TYPE_CHECKING:
    from .models import OrderItem

# Create your models here.

class Item(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название")
    description = models.TextField(verbose_name="Описание")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    currency = models.CharField(
        max_length=3,
        choices=[
            ('rub', 'Рубль'),
            ('usd', 'Доллар'),
        ],
        default='rub'
    )

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

    def __str__(self) -> str:
        return self.name

class Discount(models.Model):
    TYPE_CHOICES = [
        ('percentage', 'Процент'),
        ('fixed', 'Фиксированная сумма'),
    ]

    name = models.CharField(max_length=255, verbose_name="Название скидки")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="Тип скидки")
    value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Значение скидки")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Скидка"
        verbose_name_plural = "Скидки"

    def __str__(self) -> str:
        return f"{self.name})"

class Tax(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название налога")
    rate = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Ставка налога (%)")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Налог"
        verbose_name_plural = "Налоги"

    def __str__(self) -> str:
        return f"{self.name} ({self.rate}%)"

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Ожидает оплаты'),
        ('paid', 'Оплачен'),
        ('cancelled', 'Отменен'),
    ]

    items = models.ManyToManyField(Item, through='OrderItem', verbose_name="Товары")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'), verbose_name="Общая стоимость")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID сессии Stripe")
    
    discount = models.ForeignKey(
        Discount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Скидка",
        related_name='orders'
    )
    tax = models.ForeignKey(
        Tax,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Налог",
        related_name='orders'
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Сумма скидки"
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Сумма налога"
    )
    final_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Итоговая сумма"
    )

    order_items: Manager['OrderItem']

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"Заказ #{self.pk} - {self.final_amount}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, verbose_name="Заказ", related_name='order_items')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, verbose_name="Товар")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")

    class Meta:
        verbose_name = "Товар в заказе"
        verbose_name_plural = "Товары в заказе"

    def __str__(self) -> str:
        return f"{self.item.name} x {self.quantity}"
