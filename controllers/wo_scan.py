# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class WoScanController(http.Controller):

    def _wo_from_token(self, token):
        return request.env["mrp.workorder"].sudo().search([("qr_token", "=", token)], limit=1)

    @http.route("/wo/scan/<string:token>", type="http", auth="public", website=True, csrf=False)
    def wo_scan_form(self, token, **kw):
        wo = self._wo_from_token(token)
        if not wo:
            return request.not_found()
        return request.render("mrp_work_queue.wo_scan_template", {"wo": wo})

    @http.route("/wo/scan/submit", type="http", auth="public", methods=["POST"], csrf=False)
    def wo_scan_submit(self, **post):
        token = post.get("token")
        done = float(post.get("qty_done") or 0)
        scrap = float(post.get("qty_scrap") or 0)

        wo = self._wo_from_token(token)
        if not wo:
            return request.not_found()

        # Registrar cantidades mínimas (simple). Ajustalo si usás lotes/tiempos.
        try:
            # Si hace falta iniciar antes de terminar
            if hasattr(wo, "button_start"):
                try:
                    wo.sudo().button_start()
                except Exception:
                    pass

            # Registra producción si tenés método; si no, escribe y termina.
            if hasattr(wo, "record_production"):
                wo.sudo().record_production(qty=done)  # puede variar por versión
            else:
                if wo._fields.get("qty_produced"):
                    wo.sudo().write({"qty_produced": (wo.qty_produced or 0) + done})

            # Scrap (opcional, simplificado)
            if scrap and hasattr(wo, "create_scrap_move"):
                try:
                    wo.sudo().create_scrap_move(qty=scrap)
                except Exception:
                    pass

            # Terminar OT
            if hasattr(wo, "button_finish"):
                wo.sudo().button_finish()
            else:
                wo.sudo().write({"state": "done"})
        except Exception:
            # En caso de cualquier edge-case, al menos marcamos done
            wo.sudo().write({"state": "done"})

        # Imprimir la siguiente de la cola (centro/empleado)
        self._print_next_in_queue(wo)

        # Gracias + autocierre (opcional)
        return request.render("mrp_work_queue.wo_scan_done", {"wo": wo})

    def _print_next_in_queue(self, wo):
        """Busca la próxima OT de la misma cola (centro/empleado) y dispara impresión 80mm."""
        # Ajustalo a tu lógica real. Aquí un ejemplo simple:
        domain = [("state", "not in", ["done", "cancel"])]
        if wo.workcenter_id:
            domain.append(("workcenter_id", "=", wo.workcenter_id.id))
        # Si tenés relación a empleado vía tu planificador, agregala:
        # domain.append(("employee_id", "=", X))

        next_wo = request.env["mrp.workorder"].sudo().search(domain, order="id", limit=1)
        if not next_wo:
            return

        action = request.env.ref("mrp_work_queue.action_report_mrp_workorder_80mm", raise_if_not_found=False)
        if action:
            # Lanza el reporte en backend; en muchos despliegues se usa CUPS/IPP o cola del SO.
            action.sudo().report_action(next_wo)
