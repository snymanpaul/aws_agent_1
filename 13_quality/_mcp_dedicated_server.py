"""
Dedicated secure MCP server — the recommended pattern (L56).

Per ThoughtWorks: "architect a dedicated, secure MCP server specifically
tailored for agentic workflows, built on top of your existing APIs."

Four tools for a support agent workflow. Same underlying data as the naive
server — different scope, different safety properties.

Run via MCPClient subprocess — not directly.
"""
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("support-mcp")

# ── Same underlying data (in production: imported from shared service) ─────────

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

RETURN_POLICY_DAYS = 30
ISSUE_LOG: list[dict] = []

# ── Support tool 1: find order by customer email ───────────────────────────────

@mcp.tool()
def find_order_by_email(customer_email: str) -> str:
    """Find a customer's most recent open order by email address.
    Returns: order ID, product name, order status, and estimated delivery date.
    Does NOT return: pricing, margins, PII beyond name, internal notes or flags."""
    customer = next(
        (c for c in CUSTOMERS.values() if c["email"].lower() == customer_email.lower()),
        None,
    )
    if not customer:
        return json.dumps({"found": False, "reason": "No customer with that email"})

    customer_orders = [o for o in ORDERS.values() if o["customer_id"] == customer["id"]]
    if not customer_orders:
        return json.dumps({"found": False, "reason": "No orders for this customer"})

    # Return most recent, only safe fields
    order = sorted(customer_orders, key=lambda o: o["created"], reverse=True)[0]
    return json.dumps({
        "found": True,
        "order_id": order["id"],
        "customer_name": customer["name"],
        "product": order["product"],
        "status": order["status"],
        "eta": order["eta"],
    })


@mcp.tool()
def get_order_status(order_id: str) -> str:
    """Get the current delivery status of an order.
    Returns: status, product, estimated delivery, carrier name.
    Does NOT return: prices, costs, margins, internal flags, PII."""
    order = ORDERS.get(order_id)
    if not order:
        return json.dumps({"error": f"Order {order_id} not found"})

    customer = CUSTOMERS.get(order["customer_id"], {})
    return json.dumps({
        "order_id": order_id,
        "product": order["product"],
        "quantity": order["quantity"],
        "status": order["status"],
        "eta": order["eta"],
        "carrier": order["carrier"],
        "customer_name": customer.get("name", "Unknown"),
    })


@mcp.tool()
def flag_delivery_concern(order_id: str, issue_type: str) -> str:
    """Log a delivery concern for internal follow-up. Does NOT modify order
    status directly — creates an internal action item for the ops team.
    issue_type: one of 'late_delivery', 'missing_item', 'damaged', 'wrong_item'"""
    valid_issues = {"late_delivery", "missing_item", "damaged", "wrong_item"}
    if issue_type not in valid_issues:
        return json.dumps({"error": f"Invalid issue_type. Use one of: {sorted(valid_issues)}"})
    if order_id not in ORDERS:
        return json.dumps({"error": f"Order {order_id} not found"})

    # Log internally — does NOT touch order status
    entry = {"order_id": order_id, "issue_type": issue_type, "logged": True,
             "action": "ops_team_notified"}
    ISSUE_LOG.append(entry)
    return json.dumps({
        "logged": True,
        "order_id": order_id,
        "issue_type": issue_type,
        "next_steps": "Ops team notified. Customer will receive update within 24 hours.",
    })


@mcp.tool()
def check_return_eligibility(order_id: str) -> str:
    """Check whether an order is eligible for return under the standard policy.
    Returns: eligible (bool), reason, and next steps if eligible.
    Does NOT initiate a return — only checks eligibility."""
    from datetime import date, datetime

    order = ORDERS.get(order_id)
    if not order:
        return json.dumps({"error": f"Order {order_id} not found"})

    if order["status"] not in ("delivered",):
        return json.dumps({
            "eligible": False,
            "order_id": order_id,
            "reason": f"Order status is '{order['status']}' — only delivered orders can be returned.",
        })

    created = datetime.strptime(order["created"], "%Y-%m-%d").date()
    days_since = (date.today() - created).days
    eligible = days_since <= RETURN_POLICY_DAYS

    return json.dumps({
        "eligible": eligible,
        "order_id": order_id,
        "product": order["product"],
        "days_since_order": days_since,
        "return_window_days": RETURN_POLICY_DAYS,
        "reason": "Within return window." if eligible else f"Return window expired ({days_since} days > {RETURN_POLICY_DAYS} days).",
        "next_steps": "Direct customer to returns portal at returns.example.com" if eligible else "Ineligible — offer exchange or store credit as goodwill gesture.",
    })


if __name__ == "__main__":
    mcp.run()
