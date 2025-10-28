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
    plan_backlog_helper_id = fields.Many2one("work.queue.plan", index=True, string="Plan Backlog Helper")

    _sql_constraints = [
        ("uniq_workorder", "unique(workorder_id)", "Cada orden de trabajo puede estar en una sola cola."),
    ]

    # ---------- Acciones ----------
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
        plan._sync_workorder_states()
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
        if plan:
            plan._sync_workorder_states()
        return True

    def unlink(self):
        plans = self.mapped('plan_id')
        res = super().unlink()
        for plan in plans:
            plan._sync_workorder_states()
        return res

    def write(self, vals):
        # Detectar reordenamiento que afecte prioridad
        plans = self.mapped('plan_id')
        res = super().write(vals)
        if 'sequence' in vals and plans:
            for plan in plans:
                plan._sync_workorder_states()
        return res

    def action_print_wo_80mm(self):
        """Imprime (y si hace falta, activa) la primera WO de la cola del empleado."""
        self.ensure_one()
        wo = self.workorder_id
        if not wo:
            raise UserError(_("No hay una Orden de trabajo asociada para imprimir."))

        # 1) Validar que esta WO sea la primera de la cola
        plan = self.plan_id
        if not plan:
            raise UserError(_("Esta orden no está asignada a ninguna cola de trabajo."))

        first_item = plan.line_ids.sorted(lambda x: x.sequence)[0] if plan.line_ids else False
        if not first_item or first_item.id != self.id:
            raise UserError(_("Solo se puede imprimir la primera orden en la cola del empleado."))

        # 2) Si está disponible, pasarla a 'en progreso'
        if wo.state not in ('progress', 'done'):
            if hasattr(wo, 'button_start'):
                wo.button_start()
            elif hasattr(wo, 'action_start'):
                wo.action_start()
            else:
                wo.state = 'progress'

        # 3) Asignar responsable a la MO si no lo tiene
        if plan.employee_id and not wo.production_id.user_id and plan.employee_id.user_id:
            wo.production_id.write({'user_id': plan.employee_id.user_id.id})

        # 4) Buscar y ejecutar el reporte
        report_action = self.env.ref('mrp_work_queue.action_report_mrp_workorder_80mm', raise_if_not_found=False)
        if not report_action:
            report_action = self.env['ir.actions.report']._get_report_from_name('mrp_work_queue.report_workorder_80mm')
        if not report_action:
            raise UserError(_("No se encontró el reporte de OT 80mm."))

        return report_action.report_action(wo)