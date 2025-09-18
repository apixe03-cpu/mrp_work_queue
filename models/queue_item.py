from odoo import fields, models

class WorkQueueItem(models.Model):
    _name = "work.queue.item"
    _description = "Work Queue Item"
    _order = "sequence, id"

    # Prioridad dentro de la cola del empleado
    sequence = fields.Integer(default=10)

    # Orden de trabajo (única por item)
    workorder_id = fields.Many2one(
        "mrp.workorder",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # Derivados de la OT
    workcenter_id = fields.Many2one(
        related="workorder_id.workcenter_id",
        store=True,
        index=True,
    )
    production_id = fields.Many2one(
        related="workorder_id.production_id",
        store=True,
    )
    product_id = fields.Many2one(
        related="workorder_id.product_id",
        store=True,
    )
    state = fields.Selection(
        related="workorder_id.state",
        store=True,
    )

    # Asignación (None = backlog del centro)
    employee_id = fields.Many2one("hr.employee", index=True)

    # Campos helper para el tablero por plan
    plan_id = fields.Many2one("work.queue.plan", index=True)               # cola (derecha)
    plan_backlog_helper_id = fields.Many2one("work.queue.plan", index=True) # backlog (izquierda)

    _sql_constraints = [
        ("uniq_workorder", "unique(workorder_id)", "Cada orden de trabajo puede estar en una sola cola."),
    ]
