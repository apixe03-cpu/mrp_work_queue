
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

AVAILABLE_STATES = ('ready', 'pending', 'progress')

class WorkQueueItem(models.Model):
    _name = "work.queue.item"
    _description = "Item de cola por empleado"
    _order = "employee_id, sequence, id"

    employee_id = fields.Many2one("hr.employee", required=True, string="Empleado", index=True)
    workcenter_id = fields.Many2one("mrp.workcenter", required=True, string="Centro de trabajo", index=True)
    workorder_id = fields.Many2one("mrp.workorder", required=True, string="Orden de trabajo", ondelete="cascade", index=True)
    sequence = fields.Integer(string="Prioridad", default=10)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, index=True)
    state = fields.Selection(related="workorder_id.state", string="Estado", store=False)
    product_id = fields.Many2one(related="workorder_id.product_id", string="Producto", store=False)
    production_id = fields.Many2one(related="workorder_id.production_id", string="OF", store=False)
    is_available = fields.Boolean(compute="_compute_is_available", string="Disponible", store=False)

    _sql_constraints = [
        ("uniq_workorder","unique(workorder_id)", "Esta orden de trabajo ya está asignada en alguna cola.")
    ]

    @api.depends("workorder_id.state")
    def _compute_is_available(self):
        for rec in self:
            rec.is_available = bool(rec.workorder_id and rec.workorder_id.state in AVAILABLE_STATES)

    @api.constrains("workorder_id", "workcenter_id")
    def _check_workcenter_match(self):
        for rec in self:
            if rec.workorder_id and rec.workcenter_id and rec.workorder_id.workcenter_id.id != rec.workcenter_id.id:
                raise ValidationError(_("El workcenter de la orden no coincide con el del item de cola."))
