# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

# === Helper de módulo: reanudar limpio una WO ===
def force_resume_wo(wo):
    # 1) Forzar pausa si está "progress" para evitar estado a medias
    try:
        if getattr(wo, 'state', None) == 'progress':
            if hasattr(wo, 'button_pending'):
                wo.button_pending()
            elif hasattr(wo, 'action_pending'):
                wo.action_pending()
            elif hasattr(wo, 'button_pause'):
                wo.button_pause()
            elif hasattr(wo, 'action_pause'):
                wo.action_pause()
    except Exception:
        pass
    # 2) Arrancar siempre
    try:
        if hasattr(wo, 'button_start'):
            wo.button_start()
        elif hasattr(wo, 'action_start'):
            wo.action_start()
        else:
            wo.state = 'progress'
    except Exception:
        pass

class WorkQueueItem(models.Model):
    _name = "work.queue.item"
    _description = "Work Queue Item"
    _order = "sequence, id"

    sequence = fields.Integer(default=10, string="Sequence")

    workorder_id = fields.Many2one("mrp.workorder", required=True, ondelete="cascade", index=True, string="Workorder")
    workcenter_id = fields.Many2one(related="workorder_id.workcenter_id", store=True, index=True, readonly=True)
    production_id = fields.Many2one(related="workorder_id.production_id", store=False, readonly=True)
    product_id = fields.Many2one(related="workorder_id.product_id", store=False, readonly=True)
    state = fields.Selection(related="workorder_id.state", store=True, readonly=True)

    employee_id = fields.Many2one("hr.employee", index=True, string="Employee")
    plan_id = fields.Many2one("work.queue.plan", index=True, string="Plan")
    plan_backlog_helper_id = fields.Many2one("work.queue.plan", index=True, string="Plan Backlog Helper")

    # Nueva: Prioridad visible 1..N (no almacenada)
    priority_index = fields.Integer(string="Prioridad", compute="_compute_priority_index", store=False)

    _sql_constraints = [
        ("uniq_workorder", "unique(workorder_id)", "Cada orden de trabajo puede estar en una sola cola."),
    ]

    # ---- Prioridad 1..N
    @api.depends('sequence', 'plan_id.line_ids.sequence')
    def _compute_priority_index(self):
        for rec in self:
            if rec.plan_id:
                ordered = rec.plan_id.line_ids.sorted(lambda x: x.sequence)
                # índice 1-based
                rec.priority_index = 1 + next((i for i, it in enumerate(ordered) if it.id == rec.id), 0)
            else:
                rec.priority_index = 0

    # ---- Acciones
    def action_assign_to_employee(self):
        """ →: asigna al plan activo y APPENDEA (último) """
        plan = self.env["work.queue.plan"].browse(self.env.context.get("active_id"))
        if not plan:
            return
        for rec in self:
            if rec.employee_id and rec.employee_id.id != plan.employee_id.id:
                raise UserError(_("La orden ya está asignada."))

            # APPEND: tomar max sequence actual y sumar 10
            last_seq = max(plan.line_ids.mapped('sequence') or [0])
            rec.write({
                "employee_id": plan.employee_id.id,
                "plan_id": plan.id,
                "plan_backlog_helper_id": False,
                "sequence": last_seq + 10,
            })

        plan._sync_workorder_states()
        return True

    def action_unassign(self):
        """ ←: devolver a backlog """
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
        # Si reordenan (cambia sequence) o mueven entre planes, resync
        plans_before = self.mapped('plan_id')
        res = super().write(vals)
        plans_after = (self.mapped('plan_id') | plans_before)
        for plan in plans_after:
            plan._sync_workorder_states()
        return res

    def action_print_wo_80mm(self):
        self.ensure_one()
        wo = self.workorder_id
        if not wo:
            raise UserError(_("No hay una Orden de trabajo asociada para imprimir."))

        plan = self.plan_id
        if not plan:
            raise UserError(_("Esta orden no está asignada a ninguna cola de trabajo."))

        first_item = plan.line_ids.sorted(lambda x: x.sequence)[:1]
        if not first_item or first_item[0].id != self.id:
            raise UserError(_("Solo se puede imprimir la primera orden en la cola del empleado."))

        # **aquí** forzamos el resume limpio por si estaba “progress + pausada”
        force_resume_wo(wo)

        # asignar responsable si no tenía
        if plan.employee_id and not wo.production_id.user_id and plan.employee_id.user_id:
            wo.production_id.write({'user_id': plan.employee_id.user_id.id})

        report_action = self.env.ref('mrp_work_queue.action_report_mrp_workorder_80mm', raise_if_not_found=False) \
                        or self.env['ir.actions.report']._get_report_from_name('mrp_work_queue.report_workorder_80mm')
        if not report_action:
            raise UserError(_("No se encontró el reporte de OT 80mm."))

        return report_action.report_action(wo)