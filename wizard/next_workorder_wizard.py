from odoo import api, fields, models

AVAILABLE_STATES = ("ready", "pending", "progress")

class NextWorkorderWizard(models.TransientModel):
    _name = "next.workorder.wizard"
    _description = "Siguiente orden para operario"

    employee_id = fields.Many2one("hr.employee", required=True)
    workcenter_id = fields.Many2one("mrp.workcenter", required=True)
    next_item_id = fields.Many2one("work.queue.item", readonly=True)

    @api.onchange("employee_id", "workcenter_id")
    def _onchange_pick_next(self):
        self.next_item_id = False
        if self.employee_id and self.workcenter_id:
            item = self.env["work.queue.item"].search([
                ("employee_id", "=", self.employee_id.id),
                ("workcenter_id", "=", self.workcenter_id.id),
                ("workorder_id.state", "in", AVAILABLE_STATES),
            ], order="sequence, id", limit=1)
            self.next_item_id = item.id if item else False

    def action_take_next(self):
        self.ensure_one()
        if self.next_item_id:
            # Abrimos la vista de la workorder asignada
            wo = self.next_item_id.workorder_id
            return {
                "type": "ir.actions.act_window",
                "name": "Orden de trabajo",
                "res_model": "mrp.workorder",
                "view_mode": "form",
                "res_id": wo.id,
                "target": "current",
            }
        return {"type": "ir.actions.act_window_close"}
