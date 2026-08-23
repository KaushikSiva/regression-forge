from __future__ import annotations

from .models import StepType, WorkflowStep, WorkflowVersion


DEFAULT_OUTCOME = (
    "A customer can purchase a product, the order is saved, a confirmation email is sent, "
    "and fulfillment is notified."
)


def purchase_workflow(workflow_id: str, outcome: str = DEFAULT_OUTCOME, version: int = 1) -> WorkflowVersion:
    return WorkflowVersion(
        workflow_id=workflow_id,
        version=version,
        outcome=outcome,
        steps=[
            WorkflowStep(
                id="open-store",
                type=StepType.NAVIGATE,
                name="Open ForgeCart",
                config={"path": "/"},
            ),
            WorkflowStep(
                id="add-product",
                type=StepType.CLICK,
                name="Add Kinetic Driver to bag",
                config={"selector": "[data-testid='add-to-cart']"},
            ),
            WorkflowStep(
                id="cart-updated",
                type=StepType.ASSERT_TEXT,
                name="Bag contains one item",
                config={"selector": "[data-testid='cart-count']", "contains": "Bag 01"},
            ),
            WorkflowStep(
                id="customer-name",
                type=StepType.FILL,
                name="Enter customer name",
                config={"selector": "[data-testid='customer-name']", "value": "Avery Stone"},
            ),
            WorkflowStep(
                id="customer-email",
                type=StepType.FILL,
                name="Enter customer email",
                config={"selector": "[data-testid='customer-email']", "value": "avery@example.com"},
            ),
            WorkflowStep(
                id="submit-checkout",
                type=StepType.CLICK,
                name="Submit checkout",
                config={
                    "selector": "[data-testid='place-order']",
                    "capture_response": "/api/checkout",
                    "expect_status": 200,
                },
            ),
            WorkflowStep(
                id="order-confirmed",
                type=StepType.ASSERT_VISIBLE,
                name="Order confirmation is visible",
                config={"selector": "[data-testid='confirmation-screen']"},
                visual_checkpoint=True,
            ),
            WorkflowStep(
                id="order-api",
                type=StepType.ASSERT_HTTP,
                name="Order is persisted through the public API",
                config={"path": "/api/orders", "minimum_items": 1},
            ),
            WorkflowStep(
                id="confirmation-email",
                type=StepType.ASSERT_EMAIL,
                name="Confirmation email reached Mailpit",
                config={"recipient": "avery@example.com", "subject_contains": "confirmed"},
            ),
            WorkflowStep(
                id="fulfillment-webhook",
                type=StepType.ASSERT_WEBHOOK,
                name="Fulfillment webhook was received",
                config={"event": "order.ready_for_fulfillment"},
            ),
            WorkflowStep(
                id="signoz-errors",
                type=StepType.ASSERT_SIGNOZ_LOGS,
                name="No correlated error logs appeared",
                config={"service": "forgecart-api", "maximum_errors": 0},
            ),
        ],
    )
