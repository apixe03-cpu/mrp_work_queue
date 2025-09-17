
from odoo import api, fields, models, _

AVAILABLE_STATES = ('ready', 'pending', 'progress')

class WorkQueuePlan(models.Model):
    _name = "work.queue.plan"
    _description = "Planificación de cola por empleado"
    _rec_name = "name"

    name = fields.Char(compute="_compute_name", store=False)
    workcenter_id = fields.Many2one("mrp.workcenter", required=True, string="Centro de trabajo", index=True)
    employee_id = fields.Many2one("hr.employee", required=True, string="Empleado", index=True)
    line_ids = fields.One2many("work.queue.plan.line", "plan_id", string="Cola (arrastre para ordenar)")

    @api.depends("workcenter_id", "employee_id")
    def _compute_name(self):
        for rec in self:
            if rec.workcenter_id and rec.employee_id:
                rec.name = "%s / %s" % (rec.workcenter_id.display_name, rec.employee_id.display_name)
            else:
                rec.name = "Plan de cola"

    def action_load_available(self):
        self.ensure_one()
        Workorder = self.env["mrp.workorder"]
        QueueItem = self.env["work.queue.item"]
        domain = [
            ("workcenter_id", "=", self.workcenter_id.id),
            ("state", "in", AVAILABLE_STATES),
        ]
        wos = Workorder.search(domain)
        assigned_wo_ids = set(QueueItem.search([]).mapped("workorder_id").ids)
        candidates = [wo for wo in wos if wo.id not in assigned_wo_ids]
        seq = 10
        for wo in candidates:
            item = QueueItem.create({
                "employee_id": self.employee_id.id,
                "workcenter_id": self.workcenter_id.id,
                "workorder_id": wo.id,
                "sequence": seq,
            })
            self.env["work.queue.plan.line"].create({
                "plan_id": self.id,
                "item_id": item.id,
                "sequence": seq,
            })
            seq += 10
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Cargado"), "message": _("Se cargaron %s tareas" % len(candidates)), "sticky": False}
        }

class WorkQueuePlanLine(models.Model):
    _name = "work.queue.plan.line"
    _description = "Línea de plan de cola"
    _order = "sequence, id"

    plan_id = fields.Many2one("work.queue.plan", required=True, ondelete="cascade")
    item_id = fields.Many2one("work.queue.item", required=True, string="Item de cola", ondelete="cascade")
    workorder_id = fields.Many2one(related="item_id.workorder_id", string="Orden de trabajo", store=False)
    sequence = fields.Integer(string="Posición", default=10)

    @api.onchange("sequence")
    def _onchange_sequence(self):
        for line in self:
            if line.item_id:
                line.item_id.sequence = line.sequence
