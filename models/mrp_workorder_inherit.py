# -*- coding: utf-8 -*-
import logging
import time
from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def button_finish(self):
        """Extiende el cierre de la orden de trabajo para imprimir la siguiente en cola."""
        res = super().button_finish()

        for wo in self:
            try:
                # Buscar si esta WO está en una cola
                queue_item = wo.env["work.queue.item"].search(
                    [("workorder_id", "=", wo.id)], limit=1
                )
                if not queue_item or not queue_item.plan_id:
                    continue

                plan = queue_item.plan_id
                lineas = plan.line_ids.sorted(lambda x: x.sequence)

                # Buscar siguiente OT en cola
                siguientes = [i for i in lineas if i.sequence > queue_item.sequence]
                if not siguientes:
                    continue

                siguiente_item = siguientes[0]
                siguiente_wo = siguiente_item.workorder_id

                # Si la siguiente no está terminada ni cancelada
                if not siguiente_wo or siguiente_wo.state in ("done", "cancel"):
                    continue

                # Reanudar limpio
                from .queue_item import force_resume_wo
                force_resume_wo(siguiente_wo)

                # Pausa para asegurar que el estado se actualizó antes del reporte
                time.sleep(1.0)

                # Imprimir automáticamente
                report_action = wo.env.ref(
                    "mrp_work_queue.action_report_mrp_workorder_80mm",
                    raise_if_not_found=False,
                ) or wo.env["ir.actions.report"]._get_report_from_name(
                    "mrp_work_queue.report_workorder_80mm"
                )

                if report_action:
                    _logger.info(
                        "Imprimiendo automáticamente la siguiente WO %s (%s)",
                        siguiente_wo.name,
                        siguiente_wo.id,
                    )
                    report_action.report_action(siguiente_wo)
                else:
                    _logger.warning("No se encontró la acción de reporte 80mm.")

            except Exception as e:
                _logger.exception("Error al intentar imprimir siguiente OT: %s", e)

        return res

    def action_done(self):
        """Algunas vistas usan action_done en lugar de button_finish."""
        res = super().action_done()
        # Ejecutamos la misma lógica que button_finish
        self.button_finish()
        return res
