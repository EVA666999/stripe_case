from django.contrib import admin
from .models import Item, Order, OrderItem, Discount, Tax

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'description')
    search_fields = ('name', 'description')
    list_filter = ('price',)

@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'value', 'is_active', 'created_at')
    list_filter = ('type', 'is_active', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('created_at',)

@admin.register(Tax)
class TaxAdmin(admin.ModelAdmin):
    list_display = ('name', 'rate', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('created_at',)

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('price',)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'total_amount', 'discount_amount', 'tax_amount', 'final_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'stripe_session_id')
    readonly_fields = ('total_amount', 'discount_amount', 'tax_amount', 'final_amount', 'created_at', 'stripe_session_id')
    inlines = [OrderItemInline]

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'item', 'quantity', 'price')
    list_filter = ('order__status',)
    search_fields = ('item__name',)
