from odoo import fields, models

class WorkQueueItem(models.Model):
    _name = "work.queue.item"
    _description = "Work Queue Item"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)

    workorder_id = fields.Many2one(
        "mrp.workorder", required=True, ondelete="cascade", index=True
    )

    # De la OT
    workcenter_id = fields.Many2one(
        related="workorder_id.workcenter_id",
        store=True,        # ESTE sí lo dejamos almacenado porque lo usamos en dominio
        index=True,
    )
    production_id = fields.Many2one(
        related="workorder_id.production_id",
        store=False,       # <— CAMBIO
    )
    product_id = fields.Many2one(
        related="workorder_id.product_id",
        store=False,       # <— CAMBIO
    )
    state = fields.Selection(
        related="workorder_id.state",
        store=False,       # <— CAMBIO
    )

    employee_id = fields.Many2one("hr.employee", index=True)

    plan_id = fields.Many2one("work.queue.plan", index=True)
    plan_backlog_helper_id = fields.Many2one("work.queue.plan", index=True)

    _sql_constraints = [
        ("uniq_workorder", "unique(workorder_id)", "Cada orden de trabajo puede estar en una sola cola."),
    ]
