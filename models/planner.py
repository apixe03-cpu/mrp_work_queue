# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

AVAILABLE_STATES = ("ready", "pending", "progress")

class WorkQueuePlan(models.Model):
    _name = "work.queue.plan"
    _description = "Planificador por empleado"
    _order = "workcenter_id, employee_id, id"

    workcenter_id = fields.Many2one("mrp.workcenter", required=True, string="Workcenter")
    employee_id   = fields.Many2one("hr.employee", required=True, string="Employee")
    company_id    = fields.Many2one("res.company", default=lambda s: s.env.company, string="Company")

    # Derecha: cola del empleado
    line_ids = fields.One2many("work.queue.item", "plan_id", string="")

    # Izquierda: backlog calculado/cargado para este plan
    backlog_item_ids = fields.One2many("work.queue.item", "plan_backlog_helper_id", string="")

    # --------- Extras para el listado ---------
    line_count = fields.Integer(string="En cola", compute="_compute_line_count", compute_sudo=True)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for plan in self:
            plan.line_count = len(plan.line_ids)

    def name_get(self):
        """Mostrar como 'Centro - Empleado' en el listado/Many2one."""
        res = []
        for rec in self:
            wc = rec.workcenter_id.display_name or ""
            emp = rec.employee_id.name or ""
            name = f"{wc} - {emp}".strip(" - ")
            res.append((rec.id, name))
        return res

    # --------- Lógica existente ---------
    def _clean_backlog(self):
        for plan in self:
            plan.backlog_item_ids.unlink()

    def action_load_available(self):
        """Carga/actualiza la columna de 'Operaciones disponibles' del centro."""
        for plan in self:
            if not plan.workcenter_id:
                raise UserError(_("Seleccione un Centro de trabajo."))
            # Limpio backlog actual de este plan
            plan._clean_backlog()

            QueueItem = self.env["work.queue.item"]
            Workorder = self.env["mrp.workorder"]

            # Workorders del centro en estados disponibles
            wo_domain = [
                ("workcenter_id", "=", plan.workcenter_id.id),
                ("state", "in", AVAILABLE_STATES),
            ]
            workorders = Workorder.search(wo_domain)

            # Items existentes para esas workorders
            existing_items = QueueItem.search([("workorder_id", "in", workorders.ids)])
            by_wo = {it.workorder_id.id: it for it in existing_items}

            for wo in workorders:
                item = by_wo.get(wo.id)
                if item:
                    # sólo muestro en izquierda si NO está asignado
                    if not item.employee_id:
                        item.write({"plan_backlog_helper_id": plan.id})
                    continue
                # crear item "nuevo" disponible (sin empleado), ligado a este plan por helper
                QueueItem.create({
                    "workorder_id": wo.id,
                    "plan_backlog_helper_id": plan.id,
                })
        return True
