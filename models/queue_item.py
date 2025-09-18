from odoo import fields, models

class WorkQueueItem(models.Model):
    _name = "work.queue.item"
    _description = "Work Queue Item"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)

    workorder_id = fields.Many2one(
        "mrp.workorder",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # Derivados de la OT
    workcenter_id = fields.Many2one(
        related="workorder_id.workcenter_id",
        store=True,      # lo usamos para dominios por centro
        index=True,
        readonly=True,
    )
    production_id = fields.Many2one(
        related="workorder_id.production_id",
        store=False,
        readonly=True,
    )
    product_id = fields.Many2one(
        related="workorder_id.product_id",
        store=False,
        readonly=True,
    )
    state = fields.Selection(
        related="workorder_id.state",
        store=False,
        readonly=True,
    )

    # Asignación (None = backlog del centro)
    employee_id = fields.Many2one("hr.employee", index=True)

    # Tablero por plan
    plan_id = fields.Many2one("work.queue.plan", index=True)                # cola (derecha)
    plan_backlog_helper_id = fields.Many2one("work.queue.plan", index=True) # backlog (izquierda)

    _sql_constraints = [
        ("uniq_workorder", "unique(workorder_id)", "Cada orden de trabajo puede estar en una sola cola."),
    ]
