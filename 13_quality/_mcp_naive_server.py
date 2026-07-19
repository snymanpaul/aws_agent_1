"""
Naive API-to-MCP server — the anti-pattern (L56).

Direct 1:1 mapping of internal API endpoints as MCP tools.
Per ThoughtWorks Hold: "APIs are typically designed for human developers
and often consist of granular, atomic actions that, when chained together
by an AI, can lead to excessive token usage, context pollution, and poor
agent performance."

Run via MCPClient subprocess — not directly.
"""
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("naive-order-api")

# ── Shared fake database ───────────────────────────────────────────────────────

ORDERS = {
    "ORD-1001": {
        "id": "ORD-1001", "customer_id": "C-001",
        "product": "Wireless Headphones", "product_id": "P-001",
        "status": "delayed", "quantity": 1,
        "unit_price": 149.99, "cost_price": 62.50, "margin_pct": 58.3,
        "eta": "2026-03-25", "carrier": "FedEx", "tracking": "798123456789",
        "internal_flags": ["SUPPLIER_DELAY", "ESCALATE_IF_COMPLAINT"],
        "internal_notes": "Supplier stuck in customs. Do NOT proactively contact customer.",
        "created": "2026-03-10", "last_modified": "2026-03-18",
    },
    "ORD-1002": {
        "id": "ORD-1002", "customer_id": "C-002",
        "product": "USB-C Hub", "product_id": "P-002",
        "status": "delivered", "quantity": 2,
        "unit_price": 49.99, "cost_price": 18.00, "margin_pct": 64.0,
        "eta": "2026-03-14", "carrier": "UPS", "tracking": "1Z999AA10123456784",
        "internal_flags": [],
        "internal_notes": "",
        "created": "2026-03-11", "last_modified": "2026-03-14",
    },
    "ORD-1003": {
        "id": "ORD-1003", "customer_id": "C-003",
        "product": "Mechanical Keyboard", "product_id": "P-003",
        "status": "processing", "quantity": 1,
        "unit_price": 219.99, "cost_price": 95.00, "margin_pct": 56.8,
        "eta": "2026-03-22", "carrier": "DHL", "tracking": "pending",
        "internal_flags": ["HIGH_VALUE", "FRAUD_REVIEW"],
        "internal_notes": "Flagged by fraud team. Hold until cleared.",
        "created": "2026-03-17", "last_modified": "2026-03-18",
    },
}

CUSTOMERS = {
    "C-001": {
        "id": "C-001", "name": "Sarah Chen",
        "email": "sarah.chen@example.com", "phone": "+1-415-555-0192",
        "address": "742 Evergreen Terrace, Springfield, CA 94016",
        "payment_method": "Visa ending 4242", "credit_limit": 5000.00,
        "lifetime_value": 1847.50, "risk_score": 0.12,
        "vip_tier": "Silver",
    },
    "C-002": {
        "id": "C-002", "name": "James Okafor",
        "email": "jokafor@techcorp.io", "phone": "+1-212-555-0134",
        "address": "100 Corporate Blvd, New York, NY 10001",
        "payment_method": "Amex ending 1005", "credit_limit": 15000.00,
        "lifetime_value": 9320.00, "risk_score": 0.03,
        "vip_tier": "Gold",
    },
    "C-003": {
        "id": "C-003", "name": "Ana Ruiz",
        "email": "ana.ruiz@gmail.com", "phone": "+1-303-555-0177",
        "address": "56 Mountain View Dr, Denver, CO 80203",
        "payment_method": "Mastercard ending 7788", "credit_limit": 2500.00,
        "lifetime_value": 312.00, "risk_score": 0.67,
        "vip_tier": "None",
    },
}

PRODUCTS = {
    "P-001": {
        "id": "P-001", "name": "Wireless Headphones", "sku": "WH-BT500",
        "price": 149.99, "cost": 62.50, "margin_pct": 58.3,
        "stock": 23, "reorder_point": 10, "supplier": "AudioTech Ltd",
        "supplier_lead_days": 14, "warehouse": "WH-EAST-3",
    },
    "P-002": {
        "id": "P-002", "name": "USB-C Hub", "sku": "HUB-7P-UC",
        "price": 49.99, "cost": 18.00, "margin_pct": 64.0,
        "stock": 142, "reorder_point": 30, "supplier": "ConnectPro",
        "supplier_lead_days": 7, "warehouse": "WH-WEST-1",
    },
    "P-003": {
        "id": "P-003", "name": "Mechanical Keyboard", "sku": "KB-MECH-TKL",
        "price": 219.99, "cost": 95.00, "margin_pct": 56.8,
        "stock": 8, "reorder_point": 15, "supplier": "KeyCraft",
        "supplier_lead_days": 21, "warehouse": "WH-EAST-3",
    },
}

FINANCIALS = {
    "q1_2026_revenue": 284750.00,
    "q1_2026_cogs": 118430.00,
    "q1_2026_gross_margin_pct": 58.4,
    "monthly_churn_rate": 0.034,
    "avg_order_value": 147.22,
    "top_customer_concentration": 0.23,
    "pending_chargebacks": 3,
    "fraud_losses_ytd": 1820.00,
}

# ── Naive tool 1: list all orders ─────────────────────────────────────────────

@mcp.tool()
def list_all_orders() -> str:
    """List all orders in the system with full details including pricing,
    internal notes, internal flags, cost prices, and margins."""
    return json.dumps(list(ORDERS.values()), indent=2)


@mcp.tool()
def get_order(order_id: str) -> str:
    """Get full order details by order ID. Returns all fields including
    cost price, margin, internal flags, internal notes, and carrier tracking."""
    o = ORDERS.get(order_id)
    if not o:
        return json.dumps({"error": f"Order {order_id} not found"})
    return json.dumps(o, indent=2)


@mcp.tool()
def update_order_status(order_id: str, new_status: str) -> str:
    """Update the status of an order. Valid statuses: processing, shipped,
    delayed, delivered, cancelled, refunded. Directly mutates order state."""
    if order_id not in ORDERS:
        return json.dumps({"error": f"Order {order_id} not found"})
    old = ORDERS[order_id]["status"]
    ORDERS[order_id]["status"] = new_status
    return json.dumps({"order_id": order_id, "old_status": old, "new_status": new_status})


@mcp.tool()
def cancel_order(order_id: str) -> str:
    """Cancel an order permanently. This cannot be undone. Sets status to
    cancelled and triggers refund processing."""
    if order_id not in ORDERS:
        return json.dumps({"error": f"Order {order_id} not found"})
    ORDERS[order_id]["status"] = "cancelled"
    return json.dumps({"order_id": order_id, "status": "cancelled", "refund_initiated": True})


@mcp.tool()
def list_all_customers() -> str:
    """List all customers with full PII including email, phone, address,
    payment method, credit limit, lifetime value, and risk score."""
    return json.dumps(list(CUSTOMERS.values()), indent=2)


@mcp.tool()
def get_customer(customer_id: str) -> str:
    """Get full customer record by ID. Returns all PII fields: email, phone,
    address, payment method details, credit limit, risk score."""
    c = CUSTOMERS.get(customer_id)
    if not c:
        return json.dumps({"error": f"Customer {customer_id} not found"})
    return json.dumps(c, indent=2)


@mcp.tool()
def update_customer(customer_id: str, email: str = "", phone: str = "",
                    address: str = "") -> str:
    """Update customer contact details. Mutates PII fields directly."""
    if customer_id not in CUSTOMERS:
        return json.dumps({"error": f"Customer {customer_id} not found"})
    if email:
        CUSTOMERS[customer_id]["email"] = email
    if phone:
        CUSTOMERS[customer_id]["phone"] = phone
    if address:
        CUSTOMERS[customer_id]["address"] = address
    return json.dumps({"updated": customer_id, "fields": {"email": email, "phone": phone}})


@mcp.tool()
def list_products() -> str:
    """List all products with full details including cost prices, margins,
    supplier names, lead times, and warehouse locations."""
    return json.dumps(list(PRODUCTS.values()), indent=2)


@mcp.tool()
def apply_discount(product_id: str, discount_pct: float) -> str:
    """Apply a percentage discount to a product's price. Directly mutates
    the product price. discount_pct should be between 0 and 100."""
    if product_id not in PRODUCTS:
        return json.dumps({"error": f"Product {product_id} not found"})
    old_price = PRODUCTS[product_id]["price"]
    new_price = round(old_price * (1 - discount_pct / 100), 2)
    PRODUCTS[product_id]["price"] = new_price
    return json.dumps({"product_id": product_id, "old_price": old_price,
                        "new_price": new_price, "discount_pct": discount_pct})


@mcp.tool()
def get_financials() -> str:
    """Get current financial metrics including revenue, COGS, gross margin,
    churn rate, fraud losses, and pending chargebacks."""
    return json.dumps(FINANCIALS, indent=2)


if __name__ == "__main__":
    mcp.run()
