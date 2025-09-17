
from odoo import api, fields, models, _
from odoo.exceptions import UserError

AVAILABLE_STATES = ('ready', 'pending', 'progress')

class NextWorkorderWizard(models.TransientModel):
    _name = "next.workorder.wizard"
    _description = "Tomar siguiente orden para el empleado"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Empleado",
        required=True,
        default=lambda self: self.env.user.employee_id,
    )
    workcenter_id = fields.Many2one("mrp.workcenter", string="Centro de trabajo (opcional)")

    def _domain_items(self, employee):
        dom = [("employee_id", "=", employee.id)]
        if self.workcenter_id:
            dom.append(("workcenter_id", "=", self.workcenter_id.id))
        return dom

    def action_take_next(self):
        self.ensure_one()
        employee = self.employee_id or self.env.user.employee_id
        if not employee:
            raise UserError(_("El usuario no está vinculado a un empleado (hr.employee)."))

        Item = self.env["work.queue.item"]
        dom = self._domain_items(employee)
        items = Item.search(dom, order="sequence asc, id asc")
        next_item = False
        for it in items:
            if it.workorder_id.state in AVAILABLE_STATES:
                next_item = it
                break

        if not next_item:
            raise UserError(_("No hay tareas en cola para usted. Avisar al supervisor."))

        wo = next_item.workorder_id
        if hasattr(wo, "assigned_employee_id") and not wo.assigned_employee_id:
            try:
                wo.assigned_employee_id = employee.id
            except Exception:
                pass

        if wo.state in ("ready", "pending"):
            try:
                wo.button_start()
            except Exception:
                pass

        action = self.env.ref("mrp.mrp_workorder_action_modal").read()[0]
        action.update({"res_id": wo.id})
        return action
