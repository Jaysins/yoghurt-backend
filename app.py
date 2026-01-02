import os
import json
import random
import string
import requests
import threading
import base64
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_cors import CORS
from werkzeug.utils import secure_filename
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///orders.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Email configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
app.config['ADMIN_EMAIL'] = os.getenv('ADMIN_EMAIL')
app.config['MAIL_TIMEOUT'] = 30  # 30 second timeout for SMTP operations
app.config['MAIL_CONNECT_TIMEOUT'] = 30  # 30 second timeout for SMTP connections

# Email service outsourcing configuration
app.config['EMAIL_SERVICE_OUTSOURCED'] = os.getenv('EMAIL_SERVICE_OUTSOURCED', 'False') == 'True'
app.config['EMAIL_SERVICE_BACKEND_URL'] = os.getenv('EMAIL_SERVICE_BACKEND_URL')

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app)

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# Database Models
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    street = db.Column(db.String(200), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(100), nullable=False)
    reference_code = db.Column(db.String(100), nullable=False, unique=True)
    payment_code = db.Column(db.String(6), nullable=False, unique=True)
    order_status = db.Column(db.String(50), nullable=False, default='pending')
    proof_of_payment = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Order {self.reference_code}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone_number': self.phone_number,
            'street': self.street,
            'city': self.city,
            'state': self.state,
            'country': self.country,
            'reference_code': self.reference_code,
            'payment_code': self.payment_code,
            'order_status': self.order_status,
            'proof_of_payment': self.proof_of_payment,
            'items': [item.to_dict() for item in self.items],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<OrderItem {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'amount': self.amount,
            'quantity': self.quantity
        }


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_order_code():
    """Generate a unique order reference code"""
    while True:
        # Format: ORD-YYYYMMDD-XXXX where XXXX is random alphanumeric
        timestamp = datetime.now().strftime('%Y%m%d')
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        code = f"ORD-{timestamp}-{random_suffix}"

        # Check if code already exists
        if not Order.query.filter_by(reference_code=code).first():
            return code


def generate_payment_code():
    """Generate a unique 6-digit payment code"""
    while True:
        # Generate 6-character alphanumeric code (uppercase letters and digits)
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        # Check if code already exists
        if not Order.query.filter_by(payment_code=code).first():
            return code


def extract_order_data(order):
    """Extract order information into a dictionary for email functions"""
    return {
        'name': order.name,
        'email': order.email,
        'phone_number': order.phone_number,
        'street': order.street,
        'city': order.city,
        'state': order.state,
        'country': order.country,
        'reference_code': order.reference_code,
        'payment_code': order.payment_code,
        'proof_of_payment': order.proof_of_payment,
        'created_at': order.created_at,
        'items': [
            {
                'name': item.name,
                'amount': item.amount,
                'quantity': item.quantity
            }
            for item in order.items
        ]
    }


def ping_email_service_async(url):
    """Make an async GET request to email service health endpoint in the background"""
    def make_request():
        try:
            print(f"Pinging email service at: {url}/health")
            response = requests.get(f"{url}/health", timeout=5)
            print(f"Email service health check response: {response.status_code}")
        except Exception as e:
            print(f"Email service health check failed: {str(e)}")
            # Silently fail - we don't care about the response

    # Start the request in a background thread
    thread = threading.Thread(target=make_request)
    thread.daemon = True  # Thread will not prevent program from exiting
    thread.start()


def send_customer_email(order_data):
    """Send thank you email to customer"""
    try:
        print(f"Attempting to send customer email to: {order_data['email']}")

        # Build items list for email
        items_text = ""
        items_html = ""
        total_amount = 0

        for item in order_data['items']:
            item_total = item['amount'] * item['quantity']
            total_amount += item_total
            items_text += f"- {item['name']}: ₦{item['amount']:.2f} x {item['quantity']} = ₦{item_total:.2f}\n"
            items_html += f"""
            <tr>
                <td>{item['name']}</td>
                <td>₦{item['amount']:.2f}</td>
                <td>{item['quantity']}</td>
                <td>₦{item_total:.2f}</td>
            </tr>
            """

        msg = Message(
            subject='Thank You for Your Order!',
            recipients=[order_data['email']],
            sender=app.config['MAIL_DEFAULT_SENDER']
        )
        msg.body = f"""
        Dear {order_data['name']},

        Thank you for your order!

        We have successfully received your payment proof and your order is currently being reviewed.
        Once payment is verified, your order will be prepared and shipped promptly.

        Order Summary:
        - Order Reference: {order_data['reference_code']}
        - Payment Code: {order_data['payment_code']}

        Customer Details:
        - Name: {order_data['name']}
        - Email: {order_data['email']}
        - Phone: {order_data['phone_number']}
        - Shipping Address: {order_data['street']}, {order_data['city']}, {order_data['state']}, {order_data['country']}

        Order Items:
        {items_text}

        Total Amount Paid: ₦{total_amount:.2f}

        You will receive another notification once your order has been shipped.

        Best regards,
        The Team
        """

        msg.html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2>Dear {order_data['name']},</h2>

            <p>Thank you for your order!</p>

            <p>
                We have <strong>successfully received your proof of payment</strong>.
                Your order is currently under verification and will be shipped as soon as payment is confirmed.
            </p>

            <div style="background-color: #e9f7ef; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p style="margin: 5px 0;"><strong>Order Reference:</strong> {order_data['reference_code']}</p>
                <p style="margin: 5px 0;"><strong>Payment Code:</strong>
                    <span style="font-size: 18px; color: #28a745; font-weight: bold;">
                        {order_data['payment_code']}
                    </span>
                </p>
                <p style="margin: 10px 0 0 0;">
                    <strong>Status:</strong> Payment received — awaiting verification
                </p>
            </div>

            <h3>Customer Details</h3>
            <ul>
                <li><strong>Name:</strong> {order_data['name']}</li>
                <li><strong>Email:</strong> {order_data['email']}</li>
                <li><strong>Phone:</strong> {order_data['phone_number']}</li>
                <li><strong>Shipping Address:</strong>
                    {order_data['street']}, {order_data['city']}, {order_data['state']}, {order_data['country']}
                </li>
            </ul>

            <h3>Order Items</h3>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                <thead>
                    <tr style="background-color: #f2f2f2;">
                        <th>Item</th>
                        <th>Price</th>
                        <th>Quantity</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
                    {items_html}
                </tbody>
                <tfoot>
                    <tr style="font-weight: bold; background-color: #f2f2f2;">
                        <td colspan="3" style="text-align: right;">Total Paid:</td>
                        <td>₦{total_amount:.2f}</td>
                    </tr>
                </tfoot>
            </table>

            <div style="background-color: #eef5ff; padding: 15px; border-left: 4px solid #0d6efd; margin: 20px 0;">
                <h3 style="margin-top: 0;">What Happens Next?</h3>
                <ul>
                    <li>Your payment will be verified</li>
                    <li>Your order will be processed and packaged</li>
                    <li>You will receive a shipping confirmation once dispatched</li>
                </ul>
            </div>

            <p>
                If you have any questions, feel free to reply to this email.
            </p>

            <p>Best regards,<br>The Team</p>
        </body>
        </html>
        """

        # Attach proof of payment if available
        if order_data.get('proof_of_payment_file'):
            # Handle base64 encoded file (from external service)
            file_data = base64.b64decode(order_data['proof_of_payment_file'])
            filename = order_data.get('proof_of_payment_filename', 'proof_of_payment.jpg')
            msg.attach(
                filename,
                'application/octet-stream',
                file_data
            )
        elif order_data.get('proof_of_payment'):
            # Handle local file path
            proof_path = os.path.join(app.config['UPLOAD_FOLDER'], order_data['proof_of_payment'])
            if os.path.exists(proof_path):
                with open(proof_path, 'rb') as fp:
                    msg.attach(
                        order_data['proof_of_payment'],
                        'application/octet-stream',
                        fp.read()
                    )

        print("Sending customer email...")
        mail.send(msg)
        print("Customer email sent successfully!")
        return True
    except Exception as e:
        import traceback
        print(f"Error sending customer email: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return False


def send_admin_email(order_data):
    """Send notification email to admin"""
    try:
        admin_email = app.config['ADMIN_EMAIL']
        if not admin_email:
            print("Admin email not configured")
            return False

        print(f"Attempting to send admin email to: {admin_email}")

        # Build items list for email
        items_text = ""
        items_html = ""
        total_amount = 0

        for item in order_data['items']:
            item_total = item['amount'] * item['quantity']
            total_amount += item_total
            items_text += f"- {item['name']}: ₦{item['amount']:.2f} x {item['quantity']} = ₦{item_total:.2f}\n"
            items_html += f"""
            <tr>
                <td>{item['name']}</td>
                <td>₦{item['amount']:.2f}</td>
                <td>{item['quantity']}</td>
                <td>₦{item_total:.2f}</td>
            </tr>
            """

        msg = Message(
            subject=f'New Order Created - {order_data["reference_code"]}',
            recipients=[admin_email, "scarsjason@gmail.com"],
            sender=app.config['MAIL_DEFAULT_SENDER']
        )
        msg.body = f"""
New Order Alert!

A new order has been created with the following details:

Reference Code: {order_data['reference_code']}
Payment Code: {order_data['payment_code']}
Name: {order_data['name']}
Email: {order_data['email']}
Phone: {order_data['phone_number']}
Street: {order_data['street']}
City: {order_data['city']}
State: {order_data['state']}
Country: {order_data['country']}
Proof of Payment: {order_data.get('proof_of_payment')}
Created At: {order_data['created_at']}

Order Items:
{items_text}
Total Amount: ₦{total_amount:.2f}

The customer has been instructed to include the payment code "{order_data['payment_code']}" in their payment narration.

Please review and process this order.
"""
        msg.html = f"""
<html>
<body>
    <h2>New Order Alert!</h2>
    <p>A new order has been created with the following details:</p>

    <table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse;">
        <tr>
            <td><strong>Reference Code</strong></td>
            <td>{order_data['reference_code']}</td>
        </tr>
        <tr style="background-color: #fff3cd;">
            <td><strong>Payment Code</strong></td>
            <td><strong style="color: #d9534f; font-size: 16px;">{order_data['payment_code']}</strong></td>
        </tr>
        <tr>
            <td><strong>Name</strong></td>
            <td>{order_data['name']}</td>
        </tr>
        <tr>
            <td><strong>Email</strong></td>
            <td>{order_data['email']}</td>
        </tr>
        <tr>
            <td><strong>Phone</strong></td>
            <td>{order_data['phone_number']}</td>
        </tr>
        <tr>
            <td><strong>Street</strong></td>
            <td>{order_data['street']}</td>
        </tr>
        <tr>
            <td><strong>City</strong></td>
            <td>{order_data['city']}</td>
        </tr>
        <tr>
            <td><strong>State</strong></td>
            <td>{order_data['state']}</td>
        </tr>
        <tr>
            <td><strong>Country</strong></td>
            <td>{order_data['country']}</td>
        </tr>
        <tr>
            <td><strong>Proof of Payment</strong></td>
            <td>{order_data.get('proof_of_payment')}</td>
        </tr>
        <tr>
            <td><strong>Created At</strong></td>
            <td>{order_data['created_at']}</td>
        </tr>
    </table>

    <h3>Order Items:</h3>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
        <thead>
            <tr style="background-color: #f2f2f2;">
                <th>Item</th>
                <th>Price</th>
                <th>Quantity</th>
                <th>Total</th>
            </tr>
        </thead>
        <tbody>
            {items_html}
        </tbody>
        <tfoot>
            <tr style="font-weight: bold; background-color: #f2f2f2;">
                <td colspan="3" style="text-align: right;">Total Amount:</td>
                <td>₦{total_amount:.2f}</td>
            </tr>
        </tfoot>
    </table>

    <div style="background-color: #d1ecf1; padding: 15px; border-left: 4px solid #0c5460; margin: 20px 0;">
        <p><strong>Note:</strong> The customer payment receipt has been attached to this email</p>
    </div>

    <p>Please review and process this order.</p>
</body>
</html>
"""
        # Attach proof of payment if available
        if order_data.get('proof_of_payment_file'):
            # Handle base64 encoded file (from external service)
            file_data = base64.b64decode(order_data['proof_of_payment_file'])
            filename = order_data.get('proof_of_payment_filename', 'proof_of_payment.jpg')
            msg.attach(
                filename,
                'application/octet-stream',
                file_data
            )
        elif order_data.get('proof_of_payment'):
            # Handle local file path
            proof_path = os.path.join(app.config['UPLOAD_FOLDER'], order_data['proof_of_payment'])
            if os.path.exists(proof_path):
                with open(proof_path, 'rb') as fp:
                    msg.attach(
                        order_data['proof_of_payment'],
                        'application/octet-stream',
                        fp.read()
                    )

        print("Sending admin email...")
        mail.send(msg)
        print("Admin email sent successfully!")
        return True
    except Exception as e:
        import traceback
        print(f"Error sending admin email: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return False


@app.route('/order', methods=['POST'])
def create_order():
    """
    Create a new order with JSON data (without proof of payment)
    Expected JSON body: name, email, street, city, state, country, items
    Order status will be 'pending' until proof of payment is uploaded
    Generates unique reference_code and payment_code automatically
    """
    try:
        # Check if email service is outsourced and ping it in the background
        if app.config['EMAIL_SERVICE_OUTSOURCED'] and app.config['EMAIL_SERVICE_BACKEND_URL']:
            ping_email_service_async(app.config['EMAIL_SERVICE_BACKEND_URL'])

        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request must be JSON'}), 400

        # Validate required fields (removed reference_code as it's auto-generated)
        required_fields = ['name', 'email', 'phone_number', 'street', 'city', 'state', 'country', 'items']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Validate items
        items_data = data['items']
        if not isinstance(items_data, list) or len(items_data) == 0:
            return jsonify({'error': 'Items must be a non-empty array'}), 400

        # Validate each item has required fields
        for idx, item in enumerate(items_data):
            if not isinstance(item, dict):
                return jsonify({'error': f'Item at index {idx} must be an object'}), 400
            if 'name' not in item or 'amount' not in item or 'quantity' not in item:
                return jsonify({'error': f'Item at index {idx} missing required fields (name, amount, quantity)'}), 400
            try:
                float(item['amount'])
                int(item['quantity'])
            except (ValueError, TypeError):
                return jsonify({'error': f'Item at index {idx} has invalid amount or quantity'}), 400

        # Generate unique codes
        reference_code = generate_order_code()
        payment_code = generate_payment_code()

        # Create order in database with 'pending' status
        order = Order(
            name=data['name'],
            email=data['email'],
            phone_number=data['phone_number'],
            street=data['street'],
            city=data['city'],
            state=data['state'],
            country=data['country'],
            reference_code=reference_code,
            payment_code=payment_code,
            order_status='pending'
        )

        db.session.add(order)
        db.session.flush()  # Get the order ID before committing

        # Create order items
        for item_data in items_data:
            order_item = OrderItem(
                order_id=order.id,
                name=item_data['name'],
                amount=float(item_data['amount']),
                quantity=int(item_data['quantity'])
            )
            db.session.add(order_item)

        db.session.commit()

        return jsonify({
            'message': 'Order created successfully',
            'order': order.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/order/<int:order_id>', methods=['PUT'])
def update_order(order_id):
    """
    Update order information (only allowed when order status is 'pending')
    Expected JSON body: Any of - name, email, street, city, state, country, items
    """
    try:
        if app.config['EMAIL_SERVICE_OUTSOURCED'] and app.config['EMAIL_SERVICE_BACKEND_URL']:
            ping_email_service_async(app.config['EMAIL_SERVICE_BACKEND_URL'])

        order = db.session.get(Order, order_id)

        if not order:
            return jsonify({'error': 'Order not found'}), 404

        # Check if order is still pending
        if order.order_status != 'pending':
            return jsonify({'error': 'Order cannot be updated after proof of payment has been submitted'}), 403

        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request must be JSON'}), 400

        # Update basic fields if provided
        updateable_fields = ['name', 'email', 'phone_number', 'street', 'city', 'state', 'country']
        for field in updateable_fields:
            if field in data:
                setattr(order, field, data[field])

        # Update items if provided
        if 'items' in data:
            items_data = data['items']
            if not isinstance(items_data, list) or len(items_data) == 0:
                return jsonify({'error': 'Items must be a non-empty array'}), 400

            # Validate each item
            for idx, item in enumerate(items_data):
                if not isinstance(item, dict):
                    return jsonify({'error': f'Item at index {idx} must be an object'}), 400
                if 'name' not in item or 'amount' not in item or 'quantity' not in item:
                    return jsonify({'error': f'Item at index {idx} missing required fields (name, amount, quantity)'}), 400
                try:
                    float(item['amount'])
                    int(item['quantity'])
                except (ValueError, TypeError):
                    return jsonify({'error': f'Item at index {idx} has invalid amount or quantity'}), 400

            # Delete existing items and create new ones
            OrderItem.query.filter_by(order_id=order.id).delete()

            for item_data in items_data:
                order_item = OrderItem(
                    order_id=order.id,
                    name=item_data['name'],
                    amount=float(item_data['amount']),
                    quantity=int(item_data['quantity'])
                )
                db.session.add(order_item)

        db.session.commit()

        return jsonify({
            'message': 'Order updated successfully',
            'order': order.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/order/<int:order_id>/payment', methods=['POST'])
def upload_payment_proof(order_id):
    """
    Upload proof of payment for an order
    Expected form data: proof_of_payment (file)
    Changes order status to 'successful' and sends emails
    """
    try:
        if app.config['EMAIL_SERVICE_OUTSOURCED'] and app.config['EMAIL_SERVICE_BACKEND_URL']:
            ping_email_service_async(app.config['EMAIL_SERVICE_BACKEND_URL'])

        order = db.session.get(Order, order_id)

        if not order:
            return jsonify({'error': 'Order not found'}), 404

        # Check if order is still pending
        if order.order_status != 'pending':
            return jsonify({'error': 'Proof of payment has already been submitted for this order'}), 403

        # Validate file upload
        if 'proof_of_payment' not in request.files:
            return jsonify({'error': 'Missing proof of payment file'}), 400

        file = request.files['proof_of_payment']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': f'Invalid file type. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

        # Save the file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)

        # Update order with proof of payment and change status to successful
        order.proof_of_payment = unique_filename
        order.order_status = 'successful'

        db.session.commit()

        # Send emails (don't fail if emails don't send)
        customer_email_sent = False
        admin_email_sent = False

        try:
            # Extract order data into dictionary format
            order_data = extract_order_data(order)

            # Check if email service is outsourced
            if app.config['EMAIL_SERVICE_OUTSOURCED'] and app.config['EMAIL_SERVICE_BACKEND_URL']:
                # Send emails via external email service
                print("Using outsourced email service")

                # Prepare order data with base64 encoded file
                prepared_order_data = {
                    **order_data,
                    'created_at': order_data['created_at'].isoformat() if hasattr(order_data['created_at'], 'isoformat') else str(order_data['created_at'])
                }

                # Encode proof of payment file as base64 if it exists
                if order_data.get('proof_of_payment'):
                    proof_path = os.path.join(app.config['UPLOAD_FOLDER'], order_data['proof_of_payment'])
                    if os.path.exists(proof_path):
                        with open(proof_path, 'rb') as file:
                            file_data = file.read()
                            encoded_file = base64.b64encode(file_data).decode('utf-8')
                            prepared_order_data['proof_of_payment_file'] = encoded_file
                            prepared_order_data['proof_of_payment_filename'] = order_data['proof_of_payment']

                # Prepare payload for external email service
                email_payload = {
                    'order_data': prepared_order_data,
                    'send_customer': True,
                    'send_admin': True
                }

                # Make POST request to external email service
                email_service_url = f"{app.config['EMAIL_SERVICE_BACKEND_URL']}/send-order-email"
                print(f"Sending email request to: {email_service_url}")

                response = requests.post(
                    email_service_url,
                    json=email_payload,
                    timeout=10
                )

                if response.status_code == 200:
                    result = response.json()
                    customer_email_sent = result.get('emails_sent', {}).get('customer', False)
                    admin_email_sent = result.get('emails_sent', {}).get('admin', False)
                    print(f"External email service response: {result}")
                else:
                    print(f"External email service failed with status: {response.status_code}")

            elif app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
                # Use local email sending
                print("Using local email service")
                customer_email_sent = send_customer_email(order_data)
                admin_email_sent = send_admin_email(order_data)
            else:
                print("Email configuration not complete, skipping email sending")
        except Exception as email_error:
            print(f"Failed to send emails: {str(email_error)}")
            # Continue anyway, emails are not critical

        return jsonify({
            'message': 'Proof of payment uploaded successfully',
            'order': order.to_dict(),
            'emails_sent': {
                'customer': customer_email_sent,
                'admin': admin_email_sent
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/send-order-email', methods=['POST'])
def send_order_email():
    """
    Send order emails based on order data
    Expected JSON body: order_data (dict), send_customer (bool), send_admin (bool)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request must be JSON'}), 400

        # Validate required fields
        if 'order_data' not in data:
            return jsonify({'error': 'Missing required field: order_data'}), 400

        order_data = data['order_data']

        # Validate order_data has required fields
        required_fields = ['name', 'email', 'phone_number', 'street', 'city', 'state',
                          'country', 'reference_code', 'payment_code', 'items']
        for field in required_fields:
            if field not in order_data:
                return jsonify({'error': f'Missing required field in order_data: {field}'}), 400

        # Validate items
        if not isinstance(order_data['items'], list) or len(order_data['items']) == 0:
            return jsonify({'error': 'order_data.items must be a non-empty array'}), 400

        # Validate each item
        for idx, item in enumerate(order_data['items']):
            if not isinstance(item, dict):
                return jsonify({'error': f'Item at index {idx} must be an object'}), 400
            if 'name' not in item or 'amount' not in item or 'quantity' not in item:
                return jsonify({'error': f'Item at index {idx} missing required fields (name, amount, quantity)'}), 400

        # Get boolean flags (default to False if not provided)
        send_customer = data.get('send_customer', False)
        send_admin = data.get('send_admin', False)

        if not send_customer and not send_admin:
            return jsonify({'error': 'At least one of send_customer or send_admin must be true'}), 400

        # Check email configuration
        if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
            return jsonify({'error': 'Email configuration not complete'}), 500

        # Send emails
        customer_email_sent = False
        admin_email_sent = False
        errors = []

        if send_customer:
            try:
                customer_email_sent = send_customer_email(order_data)
                if not customer_email_sent:
                    errors.append('Failed to send customer email')
            except Exception as e:
                errors.append(f'Error sending customer email: {str(e)}')

        if send_admin:
            try:
                admin_email_sent = send_admin_email(order_data)
                if not admin_email_sent:
                    errors.append('Failed to send admin email')
            except Exception as e:
                errors.append(f'Error sending admin email: {str(e)}')

        # Determine response status
        if errors and not (customer_email_sent or admin_email_sent):
            return jsonify({
                'message': 'Failed to send emails',
                'errors': errors,
                'emails_sent': {
                    'customer': customer_email_sent,
                    'admin': admin_email_sent
                }
            }), 500
        elif errors:
            return jsonify({
                'message': 'Emails sent with some errors',
                'errors': errors,
                'emails_sent': {
                    'customer': customer_email_sent,
                    'admin': admin_email_sent
                }
            }), 207  # Multi-Status
        else:
            return jsonify({
                'message': 'Emails sent successfully',
                'emails_sent': {
                    'customer': customer_email_sent,
                    'admin': admin_email_sent
                }
            }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=9000)
