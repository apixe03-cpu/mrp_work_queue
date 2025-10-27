# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class WorkQueueItem(models.Model):
    _name = "work.queue.item"
    _description = "Work Queue Item"
    _order = "sequence, id"

    sequence = fields.Integer(default=10, string="Sequence")

    workorder_id = fields.Many2one(
        "mrp.workorder",
        required=True,
        ondelete="cascade",
        index=True,
        string="Workorder",
    )
    workcenter_id = fields.Many2one(
        related="workorder_id.workcenter_id",
        store=True,
        index=True,
        readonly=True,
        string="Work Center",
    )
    production_id = fields.Many2one(
        related="workorder_id.production_id",
        store=False,
        readonly=True,
        string="Manufacturing Order",
    )
    product_id = fields.Many2one(
        related="workorder_id.product_id",
        store=False,
        readonly=True,
        string="Product",
    )
    state = fields.Selection(
        related="workorder_id.state",
        store=True,
        readonly=True,
        string="Status",
    )

    # Asignación
    employee_id = fields.Many2one("hr.employee", index=True, string="Employee")
    plan_id = fields.Many2one("work.queue.plan", index=True, string="Plan")
    # Helper para listar disponibles en el plan actual
    plan_backlog_helper_id = fields.Many2one("work.queue.plan", index=True, string="Plan Backlog Helper")

    _sql_constraints = [
        ("uniq_workorder", "unique(workorder_id)", "Cada orden de trabajo puede estar en una sola cola."),
    ]

    # ---------- Acciones desde la vista ----------
    def action_assign_to_employee(self):
        """ Botón →: asigna este ítem al empleado del plan activo. """
        plan = self.env["work.queue.plan"].browse(self.env.context.get("active_id"))
        if not plan:
            return
        for rec in self:
            # si ya estaba asignada, bloquear
            if rec.employee_id and rec.employee_id.id != plan.employee_id.id:
                raise UserError(_("La orden ya está asignada."))
            rec.write({
                "employee_id": plan.employee_id.id,
                "plan_id": plan.id,
                "plan_backlog_helper_id": False,  # ya no está en backlog
            })
        return True

    def action_unassign(self):
        """ Botón ←: devuelve a backlog del plan activo (sin empleado). """
        plan = self.env["work.queue.plan"].browse(self.env.context.get("active_id"))
        for rec in self:
            rec.write({
                "employee_id": False,
                "plan_id": False,
                "plan_backlog_helper_id": plan.id if plan else False,
            })
        return True
    
    def action_print_wo_80mm(self):
        """Imprime el reporte térmico 80mm de la workorder de esta fila."""
        self.ensure_one()
        if not self.workorder_id:
            raise UserError(_("No hay una Orden de trabajo asociada para imprimir."))

        # ID del action de reporte que definiste para el 80mm
        # (lo tienes como "action_report_mrp_workorder_80mm" en tu módulo)
        report_action = self.env.ref(
            'report_workorder_80mm', raise_if_not_found=False
        )
        if not report_action:
            raise UserError(_("No se encontró el reporte de OT 80mm."))

        # Devolvemos la acción estándar de report para la(s) workorder(s)
        return report_action.report_action(self.workorder_id)
