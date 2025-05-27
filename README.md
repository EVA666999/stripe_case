# Stripe Payment Integration

Проект представляет собой API для создания заказов и их оплаты через Stripe.

## Функциональность

- Создание заказов с несколькими товарами
- Автоматический расчет стоимости
- Интеграция с платежной системой Stripe
- Отслеживание статуса заказа

## API Endpoints

### Создание заказа
```http
POST /api/orders/create/
```

Тело запроса:
```json
{
    "items": [
        {
            "item_id": 1,
            "quantity": 2
        },
        {
            "item_id": 2,
            "quantity": 3
        }
    ]
}
```

Ответ:
```json
{
    "order_id": 1,
    "session_id": "cs_test_...",
    "checkout_url": "https://checkout.stripe.com/..."
}
```

### Получение информации о заказе
```http
GET /api/orders/{order_id}/
```

Ответ:
```json
{
    "id": 1,
    "order_items": [
        {
            "item": {
                "id": 1,
                "name": "Товар 1",
                "description": "Описание 1",
                "price": "100.00"
            },
            "quantity": 2,
            "price": "200.00"
        }
    ],
    "total_amount": "200.00",
    "status": "pending",
    "created_at": "2024-05-27T13:03:23Z",
    "stripe_session_id": "cs_test_..."
}
```

### Статусы заказа
- `pending` - ожидает оплаты
- `paid` - оплачен
- `cancelled` - отменен

## Stripe Checkout Session vs PaymentIntent

В проекте поддерживаются два способа оплаты через Stripe:

- **Checkout Session** — стандартная Stripe-страница оплаты (быстрый старт, минимум кода на фронте).
- **PaymentIntent** — низкоуровневый способ, позволяющий реализовать полностью кастомную форму оплаты на вашем сайте через Stripe.js/Elements.

### Когда использовать что?
- **Checkout Session** — если устраивает внешний вид Stripe и не нужен кастомный UX.
- **PaymentIntent** — если нужен свой дизайн, поддержка Apple Pay/Google Pay, сохранение карт и т.д.

---

## Создание PaymentIntent (кастомная оплата)

```http
POST /api/payment-intent/
```

Тело запроса:
```json
{
    "items": [
        {"item_id": 1, "quantity": 2},
        {"item_id": 2, "quantity": 1}
    ],
    "discount_id": 2,  // опционально
    "tax_id": 1        // опционально
}
```

Ответ:
```json
{
    "order_id": 1,
    "payment_intent_id": "pi_...",
    "client_secret": "pi_..._secret_..."
}
```

- Используйте `client_secret` на фронте через Stripe.js/Elements для отображения формы оплаты и подтверждения платежа.
- Все расчёты (скидки, налоги) применяются автоматически.

---

## Пример интеграции Stripe.js/Elements (фронт)

1. Получите `client_secret` через POST /api/payment-intent/
2. Используйте Stripe.js для отображения формы оплаты:

```js
const stripe = Stripe('YOUR_PUBLIC_KEY');
const elements = stripe.elements();
const card = elements.create('card');
card.mount('#card-element');

// Подтверждение платежа
const {error, paymentIntent} = await stripe.confirmCardPayment(clientSecret, {
  payment_method: {
    card: card,
    billing_details: {name: 'Имя'}
  }
});
```

---

## Установка и запуск

1. Клонируйте репозиторий
2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Примените миграции:
```bash
python manage.py migrate
```

5. Создайте файл `.env` с настройками:
```
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
```

6. Запустите сервер:
```bash
python manage.py runserver
```

## Модели данных

### Item (Товар)
- `name` - название товара
- `description` - описание
- `price` - цена

### Order (Заказ)
- `items` - связь с товарами через OrderItem
- `total_amount` - общая стоимость
- `status` - статус заказа
- `created_at` - дата создания
- `stripe_session_id` - ID сессии Stripe

### OrderItem (Товар в заказе)
- `order` - связь с заказом
- `item` - связь с товаром
- `quantity` - количество
- `price` - цена на момент заказа

## Технологии

- Django
- Django REST Framework
- Stripe API
- SQLite (для разработки)

## Безопасность

- Все платежи обрабатываются через Stripe
- Цены товаров хранятся в базе данных
- Проверка статуса оплаты через Stripe API
- Логирование ошибок 