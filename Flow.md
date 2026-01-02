# Yoghurt Backend - Order Management API

A Flask application for managing orders with a multi-step order creation process and email notifications.

## Features

- Multi-step order creation process (create order → update if needed → upload payment proof)
- **Auto-generated unique order codes and 6-digit payment codes**
- JSON-based REST API for order management
- File upload for proof of payment
- Order status tracking (pending/successful)
- SQLite database storage with relationship between orders and items
- Automatic email notifications to customers and admin (sent after payment proof upload)
- **Payment code system** - customers include code in payment narration for easy identification
- Automatic total calculation
- Order update restrictions (cannot update after payment proof is submitted)
- CORS enabled for all origins

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables:
```bash
cp .env.example .env
```

Edit `.env` with your actual configuration:
- Set your email credentials (for Gmail, use an App Password)
- Set the admin email address
- Optionally configure database URL and upload folder

3. Run the application:
```bash
python app.py
```

The server will start on `http://localhost:9000`

## API Endpoints

### 1. POST /order

Creates a new order with status 'pending' (without proof of payment). Automatically generates a unique order reference code and a 6-digit payment code.

**Content-Type:** `application/json`

**JSON Body:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "street": "123 Main St",
  "city": "New York",
  "state": "NY",
  "country": "USA",
  "items": [
    {
      "name": "Yoghurt 500ml",
      "amount": 5.99,
      "quantity": 2
    },
    {
      "name": "Yoghurt 1L",
      "amount": 9.99,
      "quantity": 1
    }
  ]
}
```

**Response (Success - 201):**
```json
{
  "message": "Order created successfully",
  "order": {
    "id": 1,
    "name": "John Doe",
    "email": "john@example.com",
    "street": "123 Main St",
    "city": "New York",
    "state": "NY",
    "country": "USA",
    "reference_code": "ORD-20240101-A3B9",
    "payment_code": "K7X9M2",
    "order_status": "pending",
    "proof_of_payment": null,
    "items": [
      {
        "id": 1,
        "name": "Yoghurt 500ml",
        "amount": 5.99,
        "quantity": 2
      },
      {
        "id": 2,
        "name": "Yoghurt 1L",
        "amount": 9.99,
        "quantity": 1
      }
    ],
    "created_at": "2024-01-01T12:34:56",
    "updated_at": "2024-01-01T12:34:56"
  }
}
```

**Note:** The `reference_code` and `payment_code` are automatically generated. The payment code should be included by the customer in their payment narration for easy identification.

### 2. PUT /order/{order_id}

Update order information. **Only allowed when order status is 'pending'** (before payment proof is uploaded).

**Content-Type:** `application/json`

**JSON Body (all fields optional):**
```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "street": "456 Oak Ave",
  "city": "Los Angeles",
  "state": "CA",
  "country": "USA",
  "items": [
    {
      "name": "Yoghurt 1L",
      "amount": 9.99,
      "quantity": 3
    }
  ]
}
```

**Response (Success - 200):**
```json
{
  "message": "Order updated successfully",
  "order": {
    "id": 1,
    "name": "Jane Doe",
    "email": "jane@example.com",
    "street": "456 Oak Ave",
    "city": "Los Angeles",
    "state": "CA",
    "country": "USA",
    "reference_code": "ORD-20240101-A3B9",
    "payment_code": "K7X9M2",
    "order_status": "pending",
    "proof_of_payment": null,
    "items": [
      {
        "id": 3,
        "name": "Yoghurt 1L",
        "amount": 9.99,
        "quantity": 3
      }
    ],
    "created_at": "2024-01-01T12:34:56",
    "updated_at": "2024-01-01T12:40:00"
  }
}
```

**Response (Error - 403):**
```json
{
  "error": "Order cannot be updated after proof of payment has been submitted"
}
```

### 3. POST /order/{order_id}/payment

Upload proof of payment for an order. Changes order status to 'successful' and sends email notifications to both customer and admin.

**Content-Type:** `multipart/form-data`

**Form Fields:**
- `proof_of_payment` (required): File upload (PNG, JPG, JPEG, GIF, or PDF)

**Response (Success - 200):**
```json
{
  "message": "Proof of payment uploaded successfully",
  "order": {
    "id": 1,
    "name": "Jane Doe",
    "email": "jane@example.com",
    "street": "456 Oak Ave",
    "city": "Los Angeles",
    "state": "CA",
    "country": "USA",
    "reference_code": "ORD-20240101-A3B9",
    "payment_code": "K7X9M2",
    "order_status": "successful",
    "proof_of_payment": "20240101_124500_receipt.pdf",
    "items": [
      {
        "id": 3,
        "name": "Yoghurt 1L",
        "amount": 9.99,
        "quantity": 3
      }
    ],
    "created_at": "2024-01-01T12:34:56",
    "updated_at": "2024-01-01T12:45:00"
  },
  "emails_sent": {
    "customer": true,
    "admin": true
  }
}
```

**Response (Error - 403):**
```json
{
  "error": "Proof of payment has already been submitted for this order"
}
```

### 4. GET /health

Health check endpoint.

**Response (200):**
```json
{
  "status": "healthy"
}
```

## Order Flow

1. **Create Order** - POST /order
   - Submit order details with items (JSON)
   - System automatically generates unique `reference_code` (e.g., ORD-20240101-A3B9)
   - System automatically generates unique 6-digit `payment_code` (e.g., K7X9M2)
   - Order is created with status 'pending'
   - Returns order with ID, reference_code, and payment_code

2. **Make Payment**
   - Customer makes payment using their preferred method
   - Customer includes the `payment_code` in the payment narration/description
   - This helps admin quickly identify and match payments to orders

3. **Update Order (Optional)** - PUT /order/{order_id}
   - Update any order information if needed
   - Only works while status is 'pending'

4. **Upload Payment Proof** - POST /order/{order_id}/payment
   - Upload proof of payment file (screenshot/receipt)
   - Order status changes to 'successful'
   - Emails are sent to customer and admin
   - **Order becomes locked** - no more updates allowed

## Testing Examples

### Step 1: Create Order
```bash
curl -X POST http://localhost:9000/order \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john@example.com",
    "street": "123 Main St",
    "city": "New York",
    "state": "NY",
    "country": "USA",
    "items": [
      {"name": "Yoghurt 500ml", "amount": 5.99, "quantity": 2},
      {"name": "Yoghurt 1L", "amount": 9.99, "quantity": 1}
    ]
  }'
```

The response will include auto-generated `reference_code` and `payment_code`. Save these for later use.

### Step 2: Update Order (Optional)
```bash
curl -X PUT http://localhost:9000/order/1 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jane Doe",
    "items": [
      {"name": "Yoghurt 1L", "amount": 9.99, "quantity": 3}
    ]
  }'
```

### Step 3: Upload Payment Proof
```bash
curl -X POST http://localhost:9000/order/1/payment \
  -F "proof_of_payment=@/path/to/receipt.pdf"
```

## Email Configuration

For Gmail:
1. Enable 2-factor authentication
2. Generate an App Password at https://myaccount.google.com/apppasswords
3. Use the App Password in the `MAIL_PASSWORD` field in `.env`

## Email Notifications

Emails are sent automatically when proof of payment is uploaded:

- **Customer Email**: Thank you message with:
  - Order reference code and payment code (highlighted)
  - Payment instructions to include the payment code in payment narration
  - Itemized list of ordered items with totals
  - Shipping address details

- **Admin Email**: Order notification with:
  - Order reference code and payment code (highlighted)
  - Note that customer was instructed to use payment code in narration
  - Complete customer and order information
  - Itemized list with totals

## File Uploads

- Maximum file size: 16MB
- Allowed formats: PNG, JPG, JPEG, GIF, PDF
- Files are stored in the `uploads/` folder with timestamps

## Database

The application uses SQLite by default. The database file `orders.db` will be created automatically when you first run the app.

To use a different database, update the `DATABASE_URL` in your `.env` file.

## Order Status Values

- **pending**: Order created but payment proof not yet uploaded (can be updated)
- **successful**: Payment proof uploaded, emails sent (locked from updates)

## Code Generation

### Order Reference Code
- **Format**: `ORD-YYYYMMDD-XXXX`
- **Example**: `ORD-20240101-A3B9`
- Auto-generated using current date and random 4-character alphanumeric suffix
- Unique across all orders

### Payment Code
- **Format**: 6-digit alphanumeric code (uppercase letters and digits)
- **Example**: `K7X9M2`
- Auto-generated and unique across all orders
- Customers include this code in their payment narration/description
- Helps admin quickly identify and match payments to orders
